package runplane

import (
	"context"
	"errors"
	"io"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestWorkerClaimRequiresMode0600AndMatchingJob(t *testing.T) {
	state := t.TempDir()
	claim := WorkerClaim{
		Version: workerProtocolVersion, JobID: "job-1", Nonce: "01234567890123456789012345678901",
		Socket: filepath.Join(state, "worker.sock"), Command: CommandSpec{Name: "/bin/true"},
	}
	path, err := WriteWorkerClaim(state, claim)
	if err != nil {
		t.Fatal(err)
	}
	if info, err := os.Stat(path); err != nil || info.Mode().Perm() != 0o600 {
		t.Fatalf("claim mode = %v, err = %v", info.Mode(), err)
	}
	if _, err := LoadWorkerClaim(state, "job-other"); err == nil {
		t.Fatal("claim was accepted for the wrong job ID")
	}
	if err := os.Chmod(path, 0o640); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadWorkerClaim(state, claim.JobID); err == nil {
		t.Fatal("non-0600 worker claim was accepted")
	}
}

func TestWorkerTransportAuthenticatesAndRejectsOutOfOrderFrames(t *testing.T) {
	left, right := net.Pipe()
	client, err := NewWorkerTransport(left, "job-1", "01234567890123456789012345678901")
	if err != nil {
		t.Fatal(err)
	}
	server, err := NewWorkerTransport(right, "job-1", "01234567890123456789012345678901")
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	defer server.Close()
	accepted := make(chan error, 1)
	go func() { accepted <- server.AcceptHello() }()
	if err := client.AuthenticateClient(); err != nil {
		t.Fatal(err)
	}
	if err := <-accepted; err != nil {
		t.Fatal(err)
	}
	sent := make(chan error, 1)
	go func() { _, err := client.Send(WorkerFrame{Type: "heartbeat"}); sent <- err }()
	if _, err := server.Receive(); err != nil {
		t.Fatal(err)
	}
	if err := <-sent; err != nil {
		t.Fatal(err)
	}
	// A peer may not repeat the last sequence number after a reconnect.
	written := make(chan error, 1)
	go func() {
		_, err := client.conn.Write([]byte(`{"version":"anvil.run-plane.worker/v1","type":"heartbeat","jobId":"job-1","seq":2}` + "\n"))
		written <- err
	}()
	if _, err := server.Receive(); err == nil {
		t.Fatal("duplicate sequence was accepted")
	}
	if err := <-written; err != nil {
		t.Fatal(err)
	}
}

func TestRunWorkerForwardsExactStreamsAndWaitsForLifecycleAcks(t *testing.T) {
	state := t.TempDir()
	socket := filepath.Join(state, "worker.sock")
	listener, err := ListenWorker(socket)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	claim := WorkerClaim{
		Version: workerProtocolVersion, JobID: "job-1", Nonce: "01234567890123456789012345678901", Socket: socket,
		Command:      CommandSpec{Name: "/bin/sh", Args: []string{"-c", "cat >/dev/null; printf out; printf err >&2"}, InputMode: InputPlain},
		InitialInput: []byte("private input stays in claim\n"),
	}
	if _, err := WriteWorkerClaim(state, claim); err != nil {
		t.Fatal(err)
	}
	serverDone := make(chan struct {
		stdout, stderr string
		err            error
	}, 1)
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		transport, acceptErr := listener.Accept(ctx, claim.JobID, claim.Nonce)
		if acceptErr != nil {
			serverDone <- struct {
				stdout, stderr string
				err            error
			}{err: acceptErr}
			return
		}
		defer transport.Close()
		var stdout, stderr string
		for {
			frame, receiveErr := transport.Receive()
			if receiveErr != nil {
				serverDone <- struct {
					stdout, stderr string
					err            error
				}{stdout, stderr, receiveErr}
				return
			}
			switch frame.Type {
			case "stream":
				if frame.Stream == "stdout" {
					stdout += string(frame.Data)
				} else if frame.Stream == "stderr" {
					stderr += string(frame.Data)
				}
			case "start", "provider-started", "exit":
				if ackErr := transport.Acknowledge(frame.Seq); ackErr != nil {
					serverDone <- struct {
						stdout, stderr string
						err            error
					}{stdout, stderr, ackErr}
					return
				}
				if frame.Type == "exit" {
					if err := transport.conn.SetReadDeadline(time.Now().Add(5 * time.Second)); err != nil {
						serverDone <- struct {
							stdout, stderr string
							err            error
						}{stdout, stderr, err}
						return
					}
					if _, closeErr := transport.Receive(); !errors.Is(closeErr, io.EOF) {
						if closeErr == nil {
							closeErr = errors.New("worker transport remained readable after exit acknowledgement")
						}
						serverDone <- struct {
							stdout, stderr string
							err            error
						}{stdout, stderr, closeErr}
						return
					}
					serverDone <- struct {
						stdout, stderr string
						err            error
					}{stdout, stderr, nil}
					return
				}
			}
		}
	}()
	if err := RunWorker(context.Background(), state, claim.JobID); err != nil {
		t.Fatal(err)
	}
	result := <-serverDone
	if result.err != nil {
		t.Fatal(result.err)
	}
	if result.stdout != "out" || result.stderr != "err" {
		t.Fatalf("streams = stdout %q stderr %q", result.stdout, result.stderr)
	}
}

func TestWorkerSubcommandRejectsExtraArguments(t *testing.T) {
	if _, err := WorkerClaimPath("relative", "job-1"); err == nil {
		t.Fatal("relative state directory accepted")
	}
	if _, err := WorkerClaimPath(t.TempDir(), "bad/job"); err == nil {
		t.Fatal("unbounded job ID accepted")
	}
}

func TestWorkerReconnectReplayIsBoundedAndAcknowledgedExactlyOnce(t *testing.T) {
	var window WorkerReplayWindow
	for sequence := uint64(1); sequence <= maxWorkerReplayFrames; sequence++ {
		if err := window.Add(WorkerFrame{Seq: sequence, Type: "stream", Data: []byte("event")}); err != nil {
			t.Fatal(err)
		}
	}
	if err := window.Add(WorkerFrame{Seq: maxWorkerReplayFrames + 1, Type: "stream", Data: []byte("overflow")}); err == nil {
		t.Fatal("reconnect replay accepted more than 256 frames")
	}
	window.Acknowledge(128)
	replayed := window.Replay(128)
	if len(replayed) != 128 || replayed[0].Seq != 129 || replayed[len(replayed)-1].Seq != 256 {
		t.Fatalf("replayed frames = %#v", replayed)
	}
	window.Acknowledge(256)
	if remaining := window.Replay(0); len(remaining) != 0 {
		t.Fatalf("acknowledged events replayed twice: %#v", remaining)
	}

	var bytesWindow WorkerReplayWindow
	if err := bytesWindow.Add(WorkerFrame{Seq: 1, Type: "stream", Data: make([]byte, maxWorkerReplayBytes)}); err != nil {
		t.Fatal(err)
	}
	if err := bytesWindow.Add(WorkerFrame{Seq: 2, Type: "stream", Data: []byte{1}}); err == nil {
		t.Fatal("reconnect replay accepted more than 2 MiB")
	}
}
