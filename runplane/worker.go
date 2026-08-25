package runplane

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"os/exec"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

const workerHeartbeatInterval = 10 * time.Second
const workerReconnectTimeout = 5 * time.Second

// RunWorker is the worker subcommand implementation.  All sensitive process
// configuration comes from the protected claim file; the job ID is the only
// per-job value accepted on argv.
func RunWorker(ctx context.Context, stateDir, jobID string) error {
	claim, err := LoadWorkerClaim(stateDir, jobID)
	if err != nil {
		return err
	}
	dialer := net.Dialer{}
	conn, err := dialer.DialContext(ctx, "unix", claim.Socket)
	if err != nil {
		return fmt.Errorf("connect worker channel: %w", err)
	}
	transport, err := NewWorkerTransport(conn, jobID, claim.Nonce)
	if err != nil {
		conn.Close()
		return err
	}
	defer transport.Close()
	if err := transport.AuthenticateClient(); err != nil {
		return err
	}
	if err := workerSendAccepted(transport, WorkerFrame{Type: "start"}); err != nil {
		return err
	}

	command := exec.Command(claim.Command.Name, claim.Command.Args...)
	command.Dir = claim.Command.Directory
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	stdin, err := command.StdinPipe()
	if err != nil {
		return fmt.Errorf("create provider stdin: %w", err)
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		stdin.Close()
		return fmt.Errorf("create provider stdout: %w", err)
	}
	stderr, err := command.StderrPipe()
	if err != nil {
		stdin.Close()
		return fmt.Errorf("create provider stderr: %w", err)
	}
	if err := command.Start(); err != nil {
		stdin.Close()
		return fmt.Errorf("start provider: %w", err)
	}
	if err := workerSendAccepted(transport, WorkerFrame{Type: "provider-started"}); err != nil {
		workerStop(command, stdin)
		_ = command.Wait()
		return err
	}
	if len(claim.InitialInput) != 0 {
		if _, err := stdin.Write(claim.InitialInput); err != nil {
			workerStop(command, stdin)
			_ = command.Wait()
			return fmt.Errorf("write provider initial input: %w", err)
		}
	}
	if claim.Command.InputMode == InputPlain {
		if err := stdin.Close(); err != nil {
			workerStop(command, stdin)
			_ = command.Wait()
			return fmt.Errorf("close provider plain input: %w", err)
		}
	}

	return workerRunProvider(ctx, claim, transport, command, stdin, stdout, stderr)
}

func workerSendAccepted(transport *WorkerTransport, frame WorkerFrame) error {
	sent, err := transport.Send(frame)
	if err != nil {
		return err
	}
	ack, err := transport.Receive()
	if err != nil {
		return fmt.Errorf("read durable acceptance: %w", err)
	}
	if ack.Type != "ack" || ack.Ack != sent.Seq {
		return errors.New("worker event was not durably accepted")
	}
	return nil
}

func workerRunProvider(ctx context.Context, claim WorkerClaim, transport *WorkerTransport, command *exec.Cmd, stdin io.WriteCloser, stdout, stderr io.Reader) error {
	output := make(chan WorkerFrame, maxWorkerReplayFrames)
	transportFailure := make(chan error, 1)
	cancelled := make(chan struct{})
	var cancelledFlag atomic.Bool
	var queuedBytes atomic.Int64
	var cancelOnce sync.Once
	var replay WorkerReplayWindow
	var reconnectMu sync.Mutex
	cancel := func() {
		cancelOnce.Do(func() {
			cancelledFlag.Store(true)
			close(cancelled)
			workerStop(command, stdin)
		})
	}

	var streams sync.WaitGroup
	for _, item := range []struct {
		name string
		read io.Reader
	}{{"stdout", stdout}, {"stderr", stderr}} {
		streams.Add(1)
		go func(name string, reader io.Reader) {
			defer streams.Done()
			buffer := make([]byte, 32<<10)
			for {
				n, err := reader.Read(buffer)
				if n > 0 {
					frame := WorkerFrame{Type: "stream", Stream: name, Data: append([]byte(nil), buffer[:n]...)}
					if queuedBytes.Add(int64(n)) > maxWorkerReplayBytes {
						queuedBytes.Add(-int64(n))
						select {
						case transportFailure <- errors.New("worker stream replay byte bound exceeded"):
						default:
						}
						cancel()
						return
					}
					select {
					case output <- frame:
					case <-cancelled:
						queuedBytes.Add(-int64(n))
						return
					default:
						queuedBytes.Add(-int64(n))
						select {
						case transportFailure <- errors.New("worker stream replay buffer overflow"):
						default:
						}
						cancel()
						return
					}
				}
				if err != nil {
					if !errors.Is(err, io.EOF) {
						select {
						case transportFailure <- fmt.Errorf("read provider %s: %w", name, err):
						default:
						}
					}
					return
				}
			}
		}(item.name, item.read)
	}

	acknowledgements := make(chan uint64, 8)
	inputs := make(chan []byte, 8)
	go func() {
		var lastControlAccepted uint64
		for {
			generation := transport.ConnectionGeneration()
			frame, err := transport.Receive()
			if err != nil {
				if reconnectErr := reconnectWorker(ctx, claim, transport, &replay, &reconnectMu, generation); reconnectErr == nil {
					continue
				} else {
					select {
					case transportFailure <- fmt.Errorf("read worker control: %w; reconnect: %v", err, reconnectErr):
					default:
					}
					cancel()
					return
				}
			}
			logicalSequence := originalSequence(frame)
			if frame.ReplayOf != 0 && logicalSequence <= lastControlAccepted {
				if err := transport.Acknowledge(logicalSequence); err != nil {
					select {
					case transportFailure <- err:
					default:
					}
				}
				continue
			}
			switch frame.Type {
			case "ack":
				replay.Acknowledge(frame.Ack)
				select {
				case acknowledgements <- frame.Ack:
				default:
				}
			case "cancel":
				// The supervisor only transmits cancel after durable persistence.
				if err := transport.Acknowledge(logicalSequence); err != nil {
					select {
					case transportFailure <- err:
					default:
					}
				}
				lastControlAccepted = logicalSequence
				cancel()
			case "input":
				select {
				case inputs <- append([]byte(nil), frame.Data...):
					if err := transport.Acknowledge(logicalSequence); err != nil {
						select {
						case transportFailure <- err:
						default:
						}
					}
					lastControlAccepted = logicalSequence
				default:
					select {
					case transportFailure <- errors.New("worker input buffer overflow"):
					default:
					}
					cancel()
				}
			default:
				select {
				case transportFailure <- fmt.Errorf("unexpected worker control frame %q", frame.Type):
				default:
				}
				cancel()
			}
		}
	}()

	workerDone := make(chan error, 1)
	go func() { workerDone <- command.Wait() }()
	heartbeat := time.NewTicker(workerHeartbeatInterval)
	defer heartbeat.Stop()
	for workerDone != nil {
		select {
		case frame := <-output:
			queuedBytes.Add(-int64(len(frame.Data)))
			if err := sendWorkerTracked(ctx, claim, transport, &replay, &reconnectMu, frame); err != nil {
				select {
				case transportFailure <- err:
				default:
				}
				cancel()
			}
		case input := <-inputs:
			if _, err := stdin.Write(input); err != nil {
				select {
				case transportFailure <- fmt.Errorf("write provider input: %w", err):
				default:
				}
				cancel()
			}
		case <-heartbeat.C:
			if err := sendWorkerTracked(ctx, claim, transport, &replay, &reconnectMu, WorkerFrame{Type: "heartbeat"}); err != nil {
				select {
				case transportFailure <- err:
				default:
				}
				cancel()
			}
		case <-ctx.Done():
			cancel()
		case <-transportFailure:
			cancel()
		case err := <-workerDone:
			workerDone = nil
			streams.Wait()
			close(output)
			for frame := range output {
				queuedBytes.Add(-int64(len(frame.Data)))
				if sendErr := sendWorkerTracked(ctx, claim, transport, &replay, &reconnectMu, frame); sendErr != nil {
					return sendErr
				}
			}
			code := 0
			if exitError, ok := err.(*exec.ExitError); ok {
				code = exitError.ExitCode()
			} else if err != nil {
				return fmt.Errorf("wait provider: %w", err)
			}
			if cancelledFlag.Load() {
				code = -1
			}
			return workerSendAcceptedAfterReceiver(ctx, claim, transport, &replay, &reconnectMu, acknowledgements, WorkerFrame{Type: "exit", Payload: workerExitPayload(code)})
		}
	}
	return nil
}

func workerExitPayload(code int) []byte { return []byte(fmt.Sprintf(`{"code":%d}`, code)) }

func workerSendAcceptedAfterReceiver(ctx context.Context, claim WorkerClaim, transport *WorkerTransport, replay *WorkerReplayWindow, reconnectMu *sync.Mutex, acknowledgements <-chan uint64, frame WorkerFrame) error {
	sent, err := sendWorkerTrackedFrame(ctx, claim, transport, replay, reconnectMu, frame)
	if err != nil {
		return err
	}
	timer := time.NewTimer(5 * time.Second)
	defer timer.Stop()
	for {
		select {
		case ack := <-acknowledgements:
			if ack == sent.Seq {
				return nil
			}
		case <-timer.C:
			return errors.New("worker exit was not durably accepted")
		}
	}
}

func sendWorkerTracked(ctx context.Context, claim WorkerClaim, transport *WorkerTransport, replay *WorkerReplayWindow, reconnectMu *sync.Mutex, frame WorkerFrame) error {
	_, err := sendWorkerTrackedFrame(ctx, claim, transport, replay, reconnectMu, frame)
	return err
}

func sendWorkerTrackedFrame(ctx context.Context, claim WorkerClaim, transport *WorkerTransport, replay *WorkerReplayWindow, reconnectMu *sync.Mutex, frame WorkerFrame) (WorkerFrame, error) {
	generation := transport.ConnectionGeneration()
	sent, err := transport.Send(frame)
	if sent.Seq != 0 {
		if addErr := replay.Add(sent); addErr != nil {
			return sent, addErr
		}
	}
	if err == nil {
		return sent, nil
	}
	if reconnectErr := reconnectWorker(ctx, claim, transport, replay, reconnectMu, generation); reconnectErr != nil {
		return sent, errors.Join(err, reconnectErr)
	}
	return sent, nil
}

func reconnectWorker(parent context.Context, claim WorkerClaim, transport *WorkerTransport, replay *WorkerReplayWindow, reconnectMu *sync.Mutex, failedGeneration uint64) error {
	reconnectMu.Lock()
	defer reconnectMu.Unlock()
	if transport.ConnectionGeneration() != failedGeneration {
		return nil
	}
	ctx, cancel := context.WithTimeout(parent, workerReconnectTimeout)
	defer cancel()
	dialer := net.Dialer{}
	var lastErr error
	for ctx.Err() == nil {
		conn, err := dialer.DialContext(ctx, "unix", claim.Socket)
		if err != nil {
			lastErr = err
			time.Sleep(20 * time.Millisecond)
			continue
		}
		if err := transport.ReplaceConnection(conn); err != nil {
			_ = conn.Close()
			return err
		}
		if err := transport.AuthenticateClient(); err != nil {
			lastErr = err
			continue
		}
		lastErr = nil
		for _, original := range replay.Replay(0) {
			if _, err := transport.SendReplay(original); err != nil {
				lastErr = err
				break
			}
		}
		if lastErr == nil {
			return nil
		}
	}
	return fmt.Errorf("worker reconnect timed out: %w", errors.Join(lastErr, ctx.Err()))
}

func workerStop(command *exec.Cmd, stdin io.Closer) {
	_ = stdin.Close()
	if command == nil || command.Process == nil {
		return
	}
	pgid, err := syscall.Getpgid(command.Process.Pid)
	if err != nil || pgid <= 0 {
		return
	}
	// The provider receives its own process group; never address a terminal or
	// Herdr pane shell by PID.
	_ = syscall.Kill(-pgid, syscall.SIGTERM)
	go func() {
		timer := time.NewTimer(2 * time.Second)
		defer timer.Stop()
		<-timer.C
		if err := command.Process.Signal(syscall.Signal(0)); err == nil {
			_ = syscall.Kill(-pgid, syscall.SIGKILL)
		}
	}()
}
