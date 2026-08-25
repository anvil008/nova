package runplane

// This file contains the local, per-job wire protocol used between the
// supervisor and its worker process.  It is deliberately separate from the
// HTTP API: the worker never receives the loopback bearer token and its argv
// is limited to "swarm-runplane worker <job-id>".

import (
	"bufio"
	"bytes"
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"sync"
)

const (
	workerProtocolVersion = "anvil.run-plane.worker/v1"
	maxWorkerFrameBytes   = 128 << 10
	maxWorkerReplayFrames = 256
	maxWorkerReplayBytes  = 2 << 20
)

var workerFrameKinds = map[string]bool{
	"hello": true, "start": true, "provider-started": true, "stream": true,
	"input": true, "cancel": true, "heartbeat": true, "exit": true,
	"ack": true, "error": true,
}

var workerIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)

// WorkerFrame is one newline-delimited JSON message.  Sequence numbers are
// directional and strictly increasing, avoiding any ambiguity after a local
// socket reconnect.  Data is base64 encoded by encoding/json.
type WorkerFrame struct {
	Version  string          `json:"version"`
	Type     string          `json:"type"`
	JobID    string          `json:"jobId"`
	Seq      uint64          `json:"seq"`
	Ack      uint64          `json:"ack,omitempty"`
	ReplayOf uint64          `json:"replayOf,omitempty"`
	Nonce    string          `json:"nonce,omitempty"`
	Stream   string          `json:"stream,omitempty"`
	Data     []byte          `json:"data,omitempty"`
	Payload  json.RawMessage `json:"payload,omitempty"`
}

// WorkerClaim is intentionally stored outside argv in a mode-0600 file.
// Provider arguments and input may contain credentials or user material and
// must therefore never be reflected in worker events or errors.
type WorkerClaim struct {
	Version      string      `json:"version"`
	JobID        string      `json:"jobId"`
	Nonce        string      `json:"nonce"`
	Socket       string      `json:"socket"`
	Command      CommandSpec `json:"command"`
	InitialInput []byte      `json:"initialInput"`
}

// WorkerReplayWindow retains only frames that have not yet been durably
// acknowledged. It is connection-independent so a reconnect can replay the
// same global sequence without duplicating accepted input or events.
type WorkerReplayWindow struct {
	mu     sync.Mutex
	frames []WorkerFrame
	bytes  int
}

func (w *WorkerReplayWindow) Add(frame WorkerFrame) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if frame.Seq == 0 || len(w.frames) != 0 && frame.Seq <= w.frames[len(w.frames)-1].Seq {
		return errors.New("worker replay frame sequence must increase")
	}
	size := len(frame.Data) + len(frame.Payload)
	if len(w.frames) >= maxWorkerReplayFrames || w.bytes+size > maxWorkerReplayBytes {
		return errors.New("worker reconnect replay bound exceeded")
	}
	frame.Data = append([]byte(nil), frame.Data...)
	frame.Payload = append(json.RawMessage(nil), frame.Payload...)
	w.frames = append(w.frames, frame)
	w.bytes += size
	return nil
}

func (w *WorkerReplayWindow) Acknowledge(sequence uint64) {
	w.mu.Lock()
	defer w.mu.Unlock()
	cut := 0
	for cut < len(w.frames) && w.frames[cut].Seq <= sequence {
		w.bytes -= len(w.frames[cut].Data) + len(w.frames[cut].Payload)
		cut++
	}
	if cut != 0 {
		copy(w.frames, w.frames[cut:])
		w.frames = w.frames[:len(w.frames)-cut]
	}
}

func (w *WorkerReplayWindow) Replay(after uint64) []WorkerFrame {
	w.mu.Lock()
	defer w.mu.Unlock()
	result := make([]WorkerFrame, 0, len(w.frames))
	for _, frame := range w.frames {
		if frame.Seq > after {
			copy := frame
			copy.Data = append([]byte(nil), frame.Data...)
			copy.Payload = append(json.RawMessage(nil), frame.Payload...)
			result = append(result, copy)
		}
	}
	return result
}

func WorkerClaimPath(stateDir, jobID string) (string, error) {
	if !filepath.IsAbs(stateDir) || !workerIDPattern.MatchString(jobID) {
		return "", errors.New("worker claim requires an absolute state directory and bounded job ID")
	}
	return filepath.Join(filepath.Clean(stateDir), "workers", jobID+".claim.json"), nil
}

func WriteWorkerClaim(stateDir string, claim WorkerClaim) (string, error) {
	if err := validateWorkerClaim(claim); err != nil {
		return "", err
	}
	path, err := WorkerClaimPath(stateDir, claim.JobID)
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return "", fmt.Errorf("create worker claim directory: %w", err)
	}
	data, err := json.Marshal(claim)
	if err != nil {
		return "", fmt.Errorf("encode worker claim: %w", err)
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return "", fmt.Errorf("create worker claim: %w", err)
	}
	if _, err = file.Write(append(data, '\n')); err == nil {
		err = file.Sync()
	}
	if closeErr := file.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return "", fmt.Errorf("write worker claim: %w", err)
	}
	return path, nil
}

func LoadWorkerClaim(stateDir, jobID string) (WorkerClaim, error) {
	path, err := WorkerClaimPath(stateDir, jobID)
	if err != nil {
		return WorkerClaim{}, err
	}
	info, err := os.Stat(path)
	if err != nil {
		return WorkerClaim{}, fmt.Errorf("stat worker claim: %w", err)
	}
	if !info.Mode().IsRegular() || info.Mode().Perm() != 0o600 {
		return WorkerClaim{}, errors.New("worker claim must be a regular mode-0600 file")
	}
	file, err := os.Open(path)
	if err != nil {
		return WorkerClaim{}, fmt.Errorf("open worker claim: %w", err)
	}
	defer file.Close()
	if info.Size() > maxWorkerFrameBytes {
		return WorkerClaim{}, errors.New("worker claim exceeds bound")
	}
	decoder := json.NewDecoder(bufio.NewReader(file))
	decoder.DisallowUnknownFields()
	var claim WorkerClaim
	if err := decoder.Decode(&claim); err != nil {
		return WorkerClaim{}, fmt.Errorf("decode worker claim: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return WorkerClaim{}, errors.New("worker claim has trailing JSON")
	}
	if claim.JobID != jobID {
		return WorkerClaim{}, errors.New("worker claim job ID does not match worker argv")
	}
	if err := validateWorkerClaim(claim); err != nil {
		return WorkerClaim{}, err
	}
	return claim, nil
}

func validateWorkerClaim(claim WorkerClaim) error {
	if claim.Version != workerProtocolVersion || !workerIDPattern.MatchString(claim.JobID) || len(claim.Nonce) < 32 || !filepath.IsAbs(claim.Socket) || claim.Command.Name == "" {
		return errors.New("worker claim is malformed")
	}
	if len(claim.InitialInput) > maxBriefBytes {
		return errors.New("worker claim input exceeds bound")
	}
	return nil
}

// WorkerTransport is a single authenticated connection.  Its caller owns
// connection replacement; sequence state is retained so replayed frames can
// be identified by the receiver.
type WorkerTransport struct {
	conn       net.Conn
	jobID      string
	nonce      string
	reader     *bufio.Reader
	stateMu    sync.RWMutex
	writeMu    sync.Mutex
	readMu     sync.Mutex
	nextSeq    uint64
	received   uint64
	closed     bool
	generation uint64
}

func NewWorkerTransport(conn net.Conn, jobID, nonce string) (*WorkerTransport, error) {
	if conn == nil || !workerIDPattern.MatchString(jobID) || len(nonce) < 32 {
		return nil, errors.New("worker transport requires connection, bounded job ID, and nonce")
	}
	return &WorkerTransport{conn: conn, jobID: jobID, nonce: nonce, reader: bufio.NewReaderSize(conn, maxWorkerFrameBytes), generation: 1}, nil
}

func (t *WorkerTransport) Send(frame WorkerFrame) (WorkerFrame, error) {
	t.writeMu.Lock()
	defer t.writeMu.Unlock()
	t.stateMu.RLock()
	conn, closed := t.conn, t.closed
	t.stateMu.RUnlock()
	if closed || conn == nil {
		return WorkerFrame{}, net.ErrClosed
	}
	if !workerFrameKinds[frame.Type] || frame.JobID != "" && frame.JobID != t.jobID {
		return WorkerFrame{}, errors.New("invalid worker frame")
	}
	t.nextSeq++
	frame.Version, frame.JobID, frame.Seq = workerProtocolVersion, t.jobID, t.nextSeq
	data, err := json.Marshal(frame)
	if err != nil {
		return WorkerFrame{}, fmt.Errorf("encode worker frame: %w", err)
	}
	if len(data)+1 > maxWorkerFrameBytes {
		return WorkerFrame{}, errors.New("worker frame exceeds bound")
	}
	if _, err := conn.Write(append(data, '\n')); err != nil {
		return frame, fmt.Errorf("write worker frame: %w", err)
	}
	return frame, nil
}

// SendReplay retransmits an unacknowledged logical frame using a fresh outer
// sequence. ReplayOf lets the receiver acknowledge the original durable
// sequence without accepting provider input or events twice.
func (t *WorkerTransport) SendReplay(original WorkerFrame) (WorkerFrame, error) {
	sequence := originalSequence(original)
	original.Seq = 0
	original.Ack = 0
	original.Nonce = ""
	original.ReplayOf = sequence
	return t.Send(original)
}

func originalSequence(frame WorkerFrame) uint64 {
	if frame.ReplayOf != 0 {
		return frame.ReplayOf
	}
	return frame.Seq
}

// ReplaceConnection keeps global directional sequences while swapping only
// the failed local Unix connection.
func (t *WorkerTransport) ReplaceConnection(conn net.Conn) error {
	if conn == nil {
		return errors.New("replacement worker connection is required")
	}
	t.writeMu.Lock()
	t.stateMu.Lock()
	if t.closed {
		t.stateMu.Unlock()
		t.writeMu.Unlock()
		return net.ErrClosed
	}
	old := t.conn
	t.conn = conn
	t.reader = bufio.NewReaderSize(conn, maxWorkerFrameBytes)
	t.generation++
	t.stateMu.Unlock()
	t.writeMu.Unlock()
	if old != nil {
		_ = old.Close()
	}
	return nil
}

func (t *WorkerTransport) ConnectionGeneration() uint64 {
	t.stateMu.RLock()
	defer t.stateMu.RUnlock()
	return t.generation
}

func (t *WorkerTransport) Receive() (WorkerFrame, error) {
	t.readMu.Lock()
	defer t.readMu.Unlock()
	t.stateMu.RLock()
	reader, closed := t.reader, t.closed
	t.stateMu.RUnlock()
	if closed || reader == nil {
		return WorkerFrame{}, net.ErrClosed
	}
	line, err := reader.ReadSlice('\n')
	if err != nil {
		if errors.Is(err, bufio.ErrBufferFull) {
			return WorkerFrame{}, errors.New("worker frame exceeds bound")
		}
		return WorkerFrame{}, err
	}
	if len(line) > maxWorkerFrameBytes {
		return WorkerFrame{}, errors.New("worker frame exceeds bound")
	}
	var frame WorkerFrame
	decoder := json.NewDecoder(bytes.NewReader(line))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&frame); err != nil {
		return WorkerFrame{}, fmt.Errorf("decode worker frame: %w", err)
	}
	if frame.Version != workerProtocolVersion || !workerFrameKinds[frame.Type] || frame.JobID != t.jobID || frame.Seq == 0 || frame.Seq <= t.received {
		return WorkerFrame{}, errors.New("invalid or out-of-order worker frame")
	}
	t.received = frame.Seq
	return frame, nil
}

func (t *WorkerTransport) AuthenticateClient() error {
	hello, err := t.Send(WorkerFrame{Type: "hello", Nonce: t.nonce})
	if err != nil {
		return err
	}
	ack, err := t.Receive()
	if err != nil {
		return fmt.Errorf("read worker hello acceptance: %w", err)
	}
	if ack.Type != "ack" || ack.Ack != hello.Seq {
		return errors.New("worker hello was not accepted")
	}
	return nil
}

func (t *WorkerTransport) AcceptHello() error {
	hello, err := t.Receive()
	if err != nil {
		return err
	}
	if hello.Type != "hello" || subtle.ConstantTimeCompare([]byte(hello.Nonce), []byte(t.nonce)) != 1 {
		return errors.New("worker hello authentication failed")
	}
	_, err = t.Send(WorkerFrame{Type: "ack", Ack: hello.Seq})
	return err
}

func (t *WorkerTransport) Acknowledge(sequence uint64) error {
	_, err := t.Send(WorkerFrame{Type: "ack", Ack: sequence})
	return err
}

func (t *WorkerTransport) Close() error {
	t.writeMu.Lock()
	t.stateMu.Lock()
	if t.closed {
		t.stateMu.Unlock()
		t.writeMu.Unlock()
		return nil
	}
	t.closed = true
	conn := t.conn
	t.conn = nil
	t.reader = nil
	t.stateMu.Unlock()
	t.writeMu.Unlock()
	if conn == nil {
		return nil
	}
	return conn.Close()
}

// WorkerListener owns a mode-0700 Unix socket directory and accepts one
// authenticated connection at a time.  The supervisor persists its state
// before acknowledging start/provider-started/exit frames.
type WorkerListener struct {
	listener *net.UnixListener
	path     string
}

func ListenWorker(socketPath string) (*WorkerListener, error) {
	if !filepath.IsAbs(socketPath) {
		return nil, errors.New("worker socket path must be absolute")
	}
	if err := os.MkdirAll(filepath.Dir(socketPath), 0o700); err != nil {
		return nil, fmt.Errorf("create worker socket directory: %w", err)
	}
	_ = os.Remove(socketPath)
	address, err := net.ResolveUnixAddr("unix", socketPath)
	if err != nil {
		return nil, err
	}
	listener, err := net.ListenUnix("unix", address)
	if err != nil {
		return nil, fmt.Errorf("listen worker socket: %w", err)
	}
	if err := os.Chmod(socketPath, 0o600); err != nil {
		listener.Close()
		return nil, err
	}
	return &WorkerListener{listener: listener, path: socketPath}, nil
}

func (l *WorkerListener) Accept(ctx context.Context, jobID, nonce string) (*WorkerTransport, error) {
	conn, err := l.acceptConnection(ctx)
	if err != nil {
		return nil, err
	}
	transport, err := NewWorkerTransport(conn, jobID, nonce)
	if err != nil {
		conn.Close()
		return nil, err
	}
	if err := transport.AcceptHello(); err != nil {
		transport.Close()
		return nil, err
	}
	return transport, nil
}

func (l *WorkerListener) acceptConnection(ctx context.Context) (net.Conn, error) {
	type accepted struct {
		conn net.Conn
		err  error
	}
	result := make(chan accepted, 1)
	go func() { conn, err := l.listener.Accept(); result <- accepted{conn, err} }()
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case item := <-result:
		if item.err != nil {
			return nil, item.err
		}
		return item.conn, nil
	}
}

func (l *WorkerListener) Reaccept(ctx context.Context, transport *WorkerTransport) error {
	conn, err := l.acceptConnection(ctx)
	if err != nil {
		return err
	}
	if err := transport.ReplaceConnection(conn); err != nil {
		conn.Close()
		return err
	}
	return transport.AcceptHello()
}

func (l *WorkerListener) Close() error {
	err := l.listener.Close()
	if removeErr := os.Remove(l.path); err == nil && removeErr != nil && !os.IsNotExist(removeErr) {
		err = removeErr
	}
	return err
}
