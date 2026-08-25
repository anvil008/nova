package runplane

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"github.com/anvil008/swarm-coder/herdrbridge"
)

const workerAttachTimeout = 10 * time.Second

// Transport is the supervisor-owned control seam. Direct jobs retain their
// existing pipes; visible jobs use an authenticated WorkerTransport.
type Transport interface {
	Send(WorkerFrame) (WorkerFrame, error)
	Close() error
}

type visibleSetup struct {
	listener  *WorkerListener
	transport *WorkerTransport
	locator   herdrbridge.Locator
	claimPath string
	nonce     string
}

func (s *Supervisor) tryStartVisible(ctx context.Context, job *Job, admitted admittedRoute, spec CommandSpec, input []byte) (bool, error) {
	if !s.visibility.eligible(admitted.Route) {
		return false, nil
	}
	if admitted.Presentation == nil {
		err := errors.New("eligible visible job requires an explicit presentation")
		return s.visibilitySetupFailure(job.ID, err)
	}
	if err := s.visibility.probe(ctx); err != nil {
		return s.visibilitySetupFailure(job.ID, fmt.Errorf("herdr readiness: %w", err))
	}
	setup, err := s.prepareVisibleSetup(ctx, job, spec, input)
	if err != nil {
		return s.visibilitySetupFailure(job.ID, err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = setup.transport.Close()
			_ = setup.listener.Close()
			_ = os.Remove(setup.claimPath)
		}
	}()

	frame, err := setup.transport.Receive()
	if err != nil || frame.Type != "start" {
		if err == nil {
			err = fmt.Errorf("worker sent %q before start", frame.Type)
		}
		return s.visibilitySetupFailure(job.ID, fmt.Errorf("attach worker before provider launch: %w", err))
	}

	runtime := &jobRuntime{worker: setup.transport, listener: setup.listener, inputMode: spec.InputMode, workerMode: true, ack: make(chan uint64, 64), done: make(chan struct{})}
	s.mu.Lock()
	job.Worker = &WorkerState{LastReceived: frame.Seq}
	job.UpdatedAt = time.Now().UTC()
	stateErr := s.persistJob(*job)
	eventErr := s.appendEventLocked(job.ID, "transport.worker_attached", map[string]any{"transport": "herdr-worker"})
	if stateErr == nil && eventErr == nil {
		s.runtimes[job.ID] = runtime
	}
	s.mu.Unlock()
	if stateErr != nil || eventErr != nil {
		return true, errors.Join(stateErr, eventErr)
	}
	if err := setup.transport.Acknowledge(frame.Seq); err != nil {
		s.failWorkerTransport(job.ID, fmt.Errorf("accept worker start: %w", err))
		return true, err
	}
	committed = true // provider may start after this acknowledgement; never fall back.

	frame, err = setup.transport.Receive()
	if err != nil || frame.Type != "provider-started" {
		if err == nil {
			err = fmt.Errorf("worker sent %q before provider-started", frame.Type)
		}
		s.failWorkerTransport(job.ID, fmt.Errorf("provider worker transport: %w", err))
		return true, err
	}
	s.mu.Lock()
	job.Worker.LastReceived = frame.Seq
	job.Status = StatusRunning
	job.UpdatedAt = time.Now().UTC()
	stateErr = s.persistJob(*job)
	eventErr = s.appendEventLocked(job.ID, "process.started", map[string]any{"transport": "herdr-worker", "definition": admitted.Definition})
	s.mu.Unlock()
	if stateErr != nil || eventErr != nil {
		s.failWorkerTransport(job.ID, errors.Join(stateErr, eventErr))
		return true, errors.Join(stateErr, eventErr)
	}
	if err := setup.transport.Acknowledge(frame.Seq); err != nil {
		s.failWorkerTransport(job.ID, fmt.Errorf("accept provider start: %w", err))
		return true, err
	}
	s.visibility.setLocator(job.ID, setup.locator)
	go s.receiveWorker(job.ID, runtime)
	go s.refreshVisibility(job.ID, runtime.done)
	s.publishVisibility(job.ID, false)
	return true, nil
}

func (s *Supervisor) prepareVisibleSetup(parent context.Context, job *Job, spec CommandSpec, input []byte) (visibleSetup, error) {
	ctx, cancel := context.WithTimeout(parent, workerAttachTimeout)
	defer cancel()
	socket := workerSocketPath(s.store.root, job.ID)
	listener, err := ListenWorker(socket)
	if err != nil {
		return visibleSetup{}, fmt.Errorf("listen worker channel: %w", err)
	}
	nonce, err := randomID()
	if err != nil {
		listener.Close()
		return visibleSetup{}, err
	}
	claim := WorkerClaim{Version: workerProtocolVersion, JobID: job.ID, Nonce: nonce, Socket: socket, Command: spec, InitialInput: append([]byte(nil), input...)}
	claimPath, err := WriteWorkerClaim(s.store.root, claim)
	if err != nil {
		listener.Close()
		return visibleSetup{}, err
	}
	label := "swarm-job-" + job.ID
	locator, err := s.visibility.client.ApplyLayout(ctx, herdrbridge.LayoutSpec{
		TabLabel: label, CWD: spec.Directory,
		Command: []string{s.visibility.config.WorkerBinary, "worker", job.ID},
		Env:     map[string]string{"SWARM_RUNPLANE_STATE": s.store.root, "HERDR_SESSION": s.visibility.config.SessionID},
	})
	if err != nil {
		listener.Close()
		_ = os.Remove(claimPath)
		return visibleSetup{}, fmt.Errorf("create non-focused worker pane: %w", err)
	}
	transport, err := listener.Accept(ctx, job.ID, nonce)
	if err != nil {
		listener.Close()
		_ = os.Remove(claimPath)
		return visibleSetup{}, fmt.Errorf("accept authenticated worker: %w", err)
	}
	return visibleSetup{listener: listener, transport: transport, locator: locator, claimPath: claimPath, nonce: nonce}, nil
}

func (s *Supervisor) visibilitySetupFailure(jobID string, cause error) (bool, error) {
	s.mu.Lock()
	job := s.jobs[jobID]
	if job != nil && job.Visibility != nil {
		job.Visibility.LastError = safeVisibilityError(cause)
		job.UpdatedAt = time.Now().UTC()
		_ = s.persistJob(*job)
		_ = s.appendEventLocked(jobID, "visibility.fallback", map[string]any{"error": safeVisibilityError(cause), "mode": job.Visibility.Mode})
	}
	mode := s.visibility.config.Mode
	s.mu.Unlock()
	if mode == VisibilityRequired {
		return true, errors.Join(cause, s.failStart(jobID, cause))
	}
	return false, nil
}

func (s *Supervisor) receiveWorker(jobID string, runtime *jobRuntime) {
	buffers := map[string]*bytes.Buffer{"stdout": {}, "stderr": {}}
	defer func() {
		for stream, buffer := range buffers {
			if buffer.Len() != 0 {
				s.recordProviderLine(jobID, stream, append([]byte(nil), buffer.Bytes()...))
			}
		}
	}()
	for {
		frame, err := runtime.worker.Receive()
		if err != nil {
			ctx, cancel := context.WithTimeout(context.Background(), workerReconnectTimeout)
			reconnectErr := runtime.listener.Reaccept(ctx, runtime.worker)
			cancel()
			if reconnectErr == nil {
				continue
			}
			s.failWorkerTransport(jobID, fmt.Errorf("worker/provider transport lost: %w; reconnect: %v", err, reconnectErr))
			return
		}
		logicalSequence := originalSequence(frame)
		if frame.ReplayOf != 0 && s.workerSequenceAccepted(jobID, logicalSequence) {
			if err := runtime.worker.Acknowledge(logicalSequence); err != nil {
				s.failWorkerTransport(jobID, err)
				return
			}
			continue
		}
		switch frame.Type {
		case "stream":
			if frame.Stream != "stdout" && frame.Stream != "stderr" {
				s.failWorkerTransport(jobID, fmt.Errorf("worker sent invalid stream %q", frame.Stream))
				return
			}
			consumeWorkerBytes(jobID, frame.Stream, buffers[frame.Stream], frame.Data, s.recordProviderLine)
			if err := s.acceptWorkerFrame(jobID, runtime, logicalSequence); err != nil {
				s.failWorkerTransport(jobID, err)
				return
			}
		case "heartbeat":
			if err := s.acceptWorkerFrame(jobID, runtime, logicalSequence); err != nil {
				s.failWorkerTransport(jobID, err)
				return
			}
		case "ack":
			select {
			case runtime.ack <- frame.Ack:
			default:
			}
		case "exit":
			var payload struct {
				Code int `json:"code"`
			}
			if err := json.Unmarshal(frame.Payload, &payload); err != nil {
				s.failWorkerTransport(jobID, fmt.Errorf("decode worker exit: %w", err))
				return
			}
			for stream, buffer := range buffers {
				if buffer.Len() != 0 {
					s.recordProviderLine(jobID, stream, append([]byte(nil), buffer.Bytes()...))
					buffer.Reset()
				}
			}
			s.finishWorker(jobID, runtime, payload.Code, nil)
			_ = runtime.worker.Acknowledge(logicalSequence)
			_ = runtime.worker.Close()
			_ = runtime.listener.Close()
			return
		case "error":
			s.failWorkerTransport(jobID, errors.New("worker reported transport failure"))
			return
		default:
			s.failWorkerTransport(jobID, fmt.Errorf("unexpected worker frame %q", frame.Type))
			return
		}
	}
}

func (s *Supervisor) workerSequenceAccepted(jobID string, sequence uint64) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[jobID]
	return job != nil && job.Worker != nil && sequence <= job.Worker.LastReceived
}

func consumeWorkerBytes(jobID, stream string, buffer *bytes.Buffer, data []byte, record func(string, string, []byte)) {
	_, _ = buffer.Write(data)
	for {
		line, err := buffer.ReadBytes('\n')
		if errors.Is(err, io.EOF) {
			_, _ = buffer.Write(line)
			return
		}
		record(jobID, stream, bytes.TrimSuffix(line, []byte{'\n'}))
	}
}

func (s *Supervisor) acceptWorkerFrame(jobID string, runtime *jobRuntime, sequence uint64) error {
	s.mu.Lock()
	job := s.jobs[jobID]
	if job == nil || job.Worker == nil {
		s.mu.Unlock()
		return errors.New("worker job state disappeared")
	}
	job.Worker.LastReceived = sequence
	job.UpdatedAt = time.Now().UTC()
	err := s.persistJob(*job)
	s.mu.Unlock()
	if err != nil {
		return fmt.Errorf("persist worker sequence: %w", err)
	}
	return runtime.worker.Acknowledge(sequence)
}

func (s *Supervisor) sendWorkerFrame(runtime *jobRuntime, frame WorkerFrame) error {
	runtime.writeMu.Lock()
	defer runtime.writeMu.Unlock()
	generation := runtime.worker.ConnectionGeneration()
	sent, err := runtime.worker.Send(frame)
	if err != nil {
		if sent.Seq == 0 || !waitWorkerReconnect(runtime, generation, workerReconnectTimeout) {
			return err
		}
		if _, replayErr := runtime.worker.SendReplay(sent); replayErr != nil {
			return errors.Join(err, replayErr)
		}
	}
	timer := time.NewTimer(5 * time.Second)
	defer timer.Stop()
	replayed := err != nil
	for {
		select {
		case ack := <-runtime.ack:
			if ack == sent.Seq {
				return nil
			}
		case <-timer.C:
			if !replayed && runtime.worker.ConnectionGeneration() != generation {
				if _, replayErr := runtime.worker.SendReplay(sent); replayErr != nil {
					return replayErr
				}
				replayed = true
				timer.Reset(5 * time.Second)
				continue
			}
			return errors.New("worker command was not acknowledged")
		case <-runtime.done:
			return errors.New("worker transport closed")
		}
	}
}

func waitWorkerReconnect(runtime *jobRuntime, generation uint64, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if runtime.worker.ConnectionGeneration() != generation {
			return true
		}
		select {
		case <-runtime.done:
			return false
		case <-time.After(10 * time.Millisecond):
		}
	}
	return false
}

func (s *Supervisor) failWorkerTransport(jobID string, cause error) {
	s.mu.Lock()
	runtime := s.runtimes[jobID]
	s.mu.Unlock()
	if runtime == nil {
		return
	}
	s.finishWorker(jobID, runtime, -1, cause)
	_ = runtime.worker.Close()
	_ = runtime.listener.Close()
}

func closeRuntimeDone(runtime *jobRuntime) {
	if runtime == nil || runtime.done == nil {
		return
	}
	select {
	case <-runtime.done:
	default:
		close(runtime.done)
	}
}

func workerSocketPath(stateRoot, jobID string) string {
	digest := sha256.Sum256([]byte(filepath.Clean(stateRoot)))
	return filepath.Join(os.TempDir(), fmt.Sprintf("swrp-%x", digest[:6]), jobID[:16]+".sock")
}
