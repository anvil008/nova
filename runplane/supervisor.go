package runplane

import (
	"bufio"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
)

// DefaultMaxConcurrent is the supervised run-plane's hard global admission
// cap when the operator does not provide an explicit override. Provider and
// harness limits may still impose a lower effective ceiling.
const DefaultMaxConcurrent = 25

type Options struct {
	StateDir      string
	MaxEvents     int
	MaxConcurrent int
	Discoverer    Discoverer
	// AllowLegacyAdmission exists only for compatibility tests and controlled
	// migration. Production accepts the small handoff boundary but still
	// requires a valid terminal handoff before reporting success.
	AllowLegacyAdmission bool
	RepositorySnapshot   func(string) (string, error)
	Visibility           VisibilityConfig
	VisibilityFactory    VisibilityClientFactory
}

type Supervisor struct {
	mu                   sync.Mutex
	store                stateStore
	discoverer           Discoverer
	maxConcurrent        int
	allowLegacyAdmission bool
	repositorySnapshot   func(string) (string, error)
	jobs                 map[string]*Job
	runtimes             map[string]*jobRuntime
	sequence             map[string]uint64
	authToken            string
	resuming             map[string]bool
	persistJob           func(Job) error
	persistEvent         func(Event) error
	ownerLock            *os.File
	visibility           *VisibilityController
}

type jobRuntime struct {
	command    *exec.Cmd
	stdin      io.WriteCloser
	inputMode  InputMode
	worker     *WorkerTransport
	listener   *WorkerListener
	workerSeq  uint64
	ack        chan uint64
	done       chan struct{}
	workerMode bool
	writeMu    sync.Mutex
	canceled   bool
	closed     bool
	streams    sync.WaitGroup
}

func NewSupervisor(options Options) (*Supervisor, error) {
	store, err := newStateStore(options.StateDir, options.MaxEvents)
	if err != nil {
		return nil, err
	}
	ownerLock, err := acquireStateOwnerLock(store.root)
	if err != nil {
		return nil, err
	}
	accepted := false
	defer func() {
		if !accepted {
			releaseStateOwnerLock(ownerLock)
		}
	}()
	jobs, err := store.loadJobs()
	if err != nil {
		return nil, err
	}
	discoverer := options.Discoverer
	if discoverer.Runner == nil {
		discoverer = NewDiscoverer()
	}
	maximum := options.MaxConcurrent
	if maximum <= 0 {
		maximum = DefaultMaxConcurrent
	}
	token, err := loadOrCreateAuthToken(store.root)
	if err != nil {
		return nil, err
	}
	snapshotter := options.RepositorySnapshot
	if snapshotter == nil {
		snapshotter = snapshotRepository
	}
	visibility := newVisibilityController(options.Visibility, options.VisibilityFactory)
	supervisor := &Supervisor{store: store, discoverer: discoverer, maxConcurrent: maximum, allowLegacyAdmission: options.AllowLegacyAdmission, repositorySnapshot: snapshotter, jobs: jobs, runtimes: map[string]*jobRuntime{}, sequence: map[string]uint64{}, authToken: token, resuming: map[string]bool{}, persistJob: store.saveJob, persistEvent: store.appendEvent, ownerLock: ownerLock, visibility: visibility}
	if err := supervisor.reconcile(); err != nil {
		return nil, err
	}
	accepted = true
	return supervisor, nil
}

func acquireStateOwnerLock(root string) (*os.File, error) {
	path := filepath.Join(root, "supervisor.lock")
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, fmt.Errorf("open run-plane state owner lock: %w", err)
	}
	if err := syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		file.Close()
		if errors.Is(err, syscall.EWOULDBLOCK) || errors.Is(err, syscall.EAGAIN) {
			return nil, fmt.Errorf("run-plane state directory %q already has a live supervisor owner", root)
		}
		return nil, fmt.Errorf("lock run-plane state directory: %w", err)
	}
	// The kernel lock is authoritative. Metadata is diagnostic only, so a lock
	// file left by a crashed owner is safely reused after the kernel releases it.
	if err := file.Truncate(0); err == nil {
		_, err = file.Seek(0, io.SeekStart)
	}
	if err == nil {
		_, err = fmt.Fprintf(file, "pid=%d\nacquired=%s\n", os.Getpid(), time.Now().UTC().Format(time.RFC3339Nano))
	}
	if err == nil {
		err = file.Sync()
	}
	if err != nil {
		releaseStateOwnerLock(file)
		return nil, fmt.Errorf("write run-plane state owner metadata: %w", err)
	}
	return file, nil
}

func releaseStateOwnerLock(file *os.File) {
	if file == nil {
		return
	}
	_ = syscall.Flock(int(file.Fd()), syscall.LOCK_UN)
	_ = file.Close()
}

func (s *Supervisor) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.runtimes) != 0 {
		return fmt.Errorf("cannot release state owner lock while %d jobs are running", len(s.runtimes))
	}
	releaseStateOwnerLock(s.ownerLock)
	s.ownerLock = nil
	return nil
}

func (s *Supervisor) Authenticate(token string) bool {
	return subtle.ConstantTimeCompare([]byte(token), []byte(s.authToken)) == 1
}

func loadOrCreateAuthToken(root string) (string, error) {
	path := filepath.Join(root, "auth.token")
	if data, err := os.ReadFile(path); err == nil {
		token := strings.TrimSpace(string(data))
		if len(token) < 32 {
			return "", fmt.Errorf("run-plane auth token is malformed")
		}
		return token, nil
	} else if !os.IsNotExist(err) {
		return "", err
	}
	data := make([]byte, 32)
	if _, err := rand.Read(data); err != nil {
		return "", err
	}
	token := hex.EncodeToString(data)
	if err := atomicWrite(path, []byte(token+"\n")); err != nil {
		return "", err
	}
	return token, nil
}

func (s *Supervisor) Capabilities(ctx context.Context) []Capability { return s.discoverer.All(ctx) }

func (s *Supervisor) Start(ctx context.Context, request StartRequest) (Job, error) {
	if request.Resume != "" {
		return Job{}, fmt.Errorf("start cannot accept an arbitrary resume session; use Resume with an existing job ID")
	}
	return s.start(ctx, request, "", "")
}

func (s *Supervisor) start(ctx context.Context, request StartRequest, resumeOf, expectedRoleDigest string) (Job, error) {
	if request.Route.SourceHarness != HarnessCodex && request.Route.SourceHarness != HarnessClaude && request.Route.SourceHarness != HarnessAGY {
		return Job{}, fmt.Errorf("unsupported source harness %q", request.Route.SourceHarness)
	}
	if request.Route.TargetHarness != HarnessCodex && request.Route.TargetHarness != HarnessClaude && request.Route.TargetHarness != HarnessAGY {
		return Job{}, fmt.Errorf("unsupported target harness %q", request.Route.TargetHarness)
	}
	id, err := randomID()
	if err != nil {
		return Job{}, err
	}
	if request.Route.DispatchID == "" {
		request.Route.DispatchID = id
	}
	if request.Route.Limits == (codingfleet.AgentHandoffLimits{}) {
		request.Route.Limits = codingfleet.AgentHandoffLimits{MaxMessages: 100, MaxDurationSeconds: 3600, MaxChildren: 4}
	}
	capability := s.discoverer.One(ctx, request.Route.TargetHarness)
	admitted, err := admitRoute(request, capability, s.discoverer.Roots)
	if err != nil {
		return Job{}, err
	}
	if expectedRoleDigest != "" && admitted.RoleDigest != expectedRoleDigest {
		return Job{}, fmt.Errorf("resume role definition digest changed from stored lineage")
	}
	spec, err := buildCommand(admitted, request.Resume)
	if err != nil {
		return Job{}, err
	}
	input, err := encodeInput(spec.InputMode, admitted.Prompt)
	if err != nil {
		return Job{}, err
	}

	s.mu.Lock()
	if err := s.checkConcurrencyLocked(admitted.Route, request.ControlPlane); err != nil {
		s.mu.Unlock()
		return Job{}, err
	}
	now := time.Now().UTC()
	job := &Job{APIVersion: APIVersion, ID: id, Route: admitted.Route, NativeRole: admitted.Binding.NativeName, RoleDigest: admitted.RoleDigest,
		ControlPlane: request.ControlPlane, WorkflowDisposition: controlplane.DispositionUncertain,
		Status: StatusStarting, SessionID: request.Resume, PromptDigest: admitted.PromptDigest, StartedAt: now, UpdatedAt: now, ResumeOf: resumeOf}
	if s.visibility.eligible(admitted.Route) {
		job.Visibility = &PresentationState{Mode: s.visibility.config.Mode, Source: TaskDisplaySource, TTLMillis: ActiveVisibilityTTL.Milliseconds()}
		if admitted.Presentation != nil {
			job.Visibility.Presentation = *admitted.Presentation
		}
	}
	s.jobs[id] = job
	if err := s.persistJob(*job); err != nil {
		delete(s.jobs, id)
		s.mu.Unlock()
		return Job{}, err
	}
	if err := s.appendEventLocked(id, "admission.accepted", map[string]any{"harness": admitted.Route.TargetHarness, "model": admitted.Route.ExactModel, "role": admitted.Binding.NativeName, "roleDigest": admitted.RoleDigest}); err != nil {
		job.Status = StatusFailed
		job.Failure = err.Error()
		job.FinishedAt = &now
		job.UpdatedAt = now
		persistErr := s.persistJob(*job)
		s.mu.Unlock()
		return Job{}, errors.Join(err, persistErr)
	}
	s.mu.Unlock()

	if handled, err := s.tryStartVisible(ctx, job, admitted, spec, input); handled {
		if err != nil {
			return Job{}, err
		}
		return s.Status(id)
	}

	command := exec.Command(spec.Name, spec.Args...)
	command.Dir = spec.Directory
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	stdin, err := command.StdinPipe()
	if err != nil {
		return Job{}, errors.Join(err, s.failStart(id, err))
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		return Job{}, errors.Join(err, s.failStart(id, err))
	}
	stderr, err := command.StderrPipe()
	if err != nil {
		return Job{}, errors.Join(err, s.failStart(id, err))
	}
	if err := command.Start(); err != nil {
		startErr := fmt.Errorf("start %s job: %w", admitted.Route.TargetHarness, err)
		return Job{}, errors.Join(startErr, s.failStart(id, startErr))
	}
	runtime := &jobRuntime{command: command, stdin: stdin, inputMode: spec.InputMode}
	startIdentity, err := readProcessStart(command.Process.Pid)
	if err != nil {
		return Job{}, s.rollbackStartedProcess(id, runtime, stdout, stderr, command.Process.Pid, fmt.Errorf("read process start identity: %w", err))
	}
	pgid, err := syscall.Getpgid(command.Process.Pid)
	if err != nil {
		return Job{}, s.rollbackStartedProcess(id, runtime, stdout, stderr, command.Process.Pid, fmt.Errorf("read process group: %w", err))
	}
	s.mu.Lock()
	job.PID = command.Process.Pid
	job.PGID = pgid
	job.ProcessStart = startIdentity
	job.Status = StatusRunning
	job.UpdatedAt = time.Now().UTC()
	if err := s.persistJob(*job); err != nil {
		s.mu.Unlock()
		return Job{}, s.rollbackStartedProcess(id, runtime, stdout, stderr, pgid, fmt.Errorf("persist running process identity: %w", err))
	}
	if err := s.appendEventLocked(id, "process.started", map[string]any{"pid": job.PID, "argv": append([]string{spec.Name}, spec.Args...), "definition": admitted.Definition}); err != nil {
		s.mu.Unlock()
		return Job{}, s.rollbackStartedProcess(id, runtime, stdout, stderr, pgid, err)
	}
	s.runtimes[id] = runtime
	s.mu.Unlock()

	runtime.streams.Add(2)
	go func() {
		defer runtime.streams.Done()
		s.readStream(id, "stdout", stdout)
	}()
	go func() {
		defer runtime.streams.Done()
		s.readStream(id, "stderr", stderr)
	}()
	if _, err := stdin.Write(input); err != nil {
		_ = s.Cancel(id)
		return Job{}, fmt.Errorf("send initial brief: %w", err)
	}
	if spec.InputMode == InputPlain {
		runtime.writeMu.Lock()
		_ = stdin.Close()
		runtime.closed = true
		runtime.writeMu.Unlock()
	}
	go s.wait(id, runtime)
	return s.Status(id)
}

func (s *Supervisor) Send(jobID, message string) error {
	if len(message) == 0 || len(message) > maxBriefBytes || strings.IndexByte(message, 0) >= 0 {
		return fmt.Errorf("message must contain 1..%d non-NUL bytes", maxBriefBytes)
	}
	s.mu.Lock()
	job, ok := s.jobs[jobID]
	runtime := s.runtimes[jobID]
	if !ok || runtime == nil || job.Status != StatusRunning {
		s.mu.Unlock()
		return fmt.Errorf("job %q is not running", jobID)
	}
	if runtime.inputMode == InputPlain {
		s.mu.Unlock()
		return fmt.Errorf("running %s jobs do not support live send; resume after the turn exits", job.Route.TargetHarness)
	}
	s.mu.Unlock()
	input, err := encodeInput(runtime.inputMode, message)
	if err != nil {
		return err
	}
	runtime.writeMu.Lock()
	if runtime.closed {
		runtime.writeMu.Unlock()
		return fmt.Errorf("job %q input is closed", jobID)
	}
	if runtime.workerMode {
		runtime.writeMu.Unlock()
		if err := s.sendWorkerFrame(runtime, WorkerFrame{Type: "input", Data: input}); err != nil {
			s.failWorkerTransport(jobID, fmt.Errorf("send worker input: %w", err))
			return fmt.Errorf("send job message: %w", err)
		}
	} else {
		_, err = runtime.stdin.Write(input)
		runtime.writeMu.Unlock()
		if err != nil {
			return fmt.Errorf("send job message: %w", err)
		}
	}
	s.mu.Lock()
	eventErr := s.appendEventLocked(jobID, "message.sent", map[string]any{"digest": digestString(message), "bytes": len(message)})
	var durabilityErr error
	pgid := job.PGID
	if eventErr != nil {
		durabilityErr = s.markDurabilityFailureLocked(jobID, "message event", eventErr)
	}
	s.mu.Unlock()
	if eventErr != nil {
		if runtime.workerMode {
			s.failWorkerTransport(jobID, durabilityErr)
		} else {
			_ = syscall.Kill(-pgid, syscall.SIGTERM)
		}
		return durabilityErr
	}
	return nil
}

func (s *Supervisor) Resume(ctx context.Context, jobID, brief string) (Job, error) {
	s.mu.Lock()
	job, ok := s.jobs[jobID]
	if !ok {
		s.mu.Unlock()
		return Job{}, fmt.Errorf("job %q does not exist", jobID)
	}
	if !terminal(job.Status) || job.SessionID == "" {
		s.mu.Unlock()
		return Job{}, fmt.Errorf("job %q is not terminal with a resumable session", jobID)
	}
	if job.ControlPlane != nil {
		s.mu.Unlock()
		return Job{}, fmt.Errorf("control-plane job %q requires a newly sealed admission and cannot be resumed in place", jobID)
	}
	resumeKey := sessionKey(job.Route.TargetHarness, job.SessionID)
	if s.resuming[resumeKey] {
		s.mu.Unlock()
		return Job{}, fmt.Errorf("provider session %q already has a resume admission in progress", job.SessionID)
	}
	for _, candidate := range s.jobs {
		if candidate.Route.TargetHarness == job.Route.TargetHarness && candidate.SessionID == job.SessionID &&
			(candidate.Status == StatusStarting || candidate.Status == StatusRunning) {
			s.mu.Unlock()
			return Job{}, fmt.Errorf("provider session %q already has active job %q", job.SessionID, candidate.ID)
		}
	}
	request := StartRequest{Route: job.Route, ControlPlane: job.ControlPlane, Brief: brief, Resume: job.SessionID}
	if job.Visibility != nil {
		presentation := job.Visibility.Presentation
		request.Presentation = &presentation
	}
	if job.ControlPlane == nil {
		request.Route.ParentDispatchID = job.Route.DispatchID
		request.Route.DispatchID = ""
	}
	expectedDigest := job.RoleDigest
	s.resuming[resumeKey] = true
	s.mu.Unlock()
	defer func() { s.mu.Lock(); delete(s.resuming, resumeKey); s.mu.Unlock() }()
	return s.start(ctx, request, jobID, expectedDigest)
}

func sessionKey(harness Harness, sessionID string) string {
	return string(harness) + "\x00" + sessionID
}

func (s *Supervisor) Cancel(jobID string) error {
	s.mu.Lock()
	job, ok := s.jobs[jobID]
	if !ok {
		s.mu.Unlock()
		return fmt.Errorf("job %q does not exist", jobID)
	}
	if terminal(job.Status) || job.WorkflowDisposition == controlplane.DispositionCancelled {
		s.mu.Unlock()
		return nil
	}
	if job.Cancellation != nil {
		s.mu.Unlock()
		return nil
	}
	targetIDs := s.cancellationTargetsLocked(job)
	type cancelTarget struct {
		id      string
		runtime *jobRuntime
		pgid    int
		worker  bool
	}
	targets := make([]cancelTarget, 0, len(targetIDs))
	dispatchIDs := make([]string, 0, len(targetIDs))
	leaseCount := 0
	for _, targetID := range targetIDs {
		targetJob := s.jobs[targetID]
		runtime := s.runtimes[targetID]
		if targetJob == nil || runtime == nil || (!runtime.workerMode && (runtime.command == nil || runtime.command.Process == nil)) {
			continue
		}
		runtime.canceled = true
		pgid := targetJob.PGID
		if pgid <= 0 && !runtime.workerMode {
			pgid = runtime.command.Process.Pid
		}
		targets = append(targets, cancelTarget{id: targetID, runtime: runtime, pgid: pgid, worker: runtime.workerMode})
		targetJob.WorkflowDisposition = controlplane.DispositionCancelled
		if targetJob.ControlPlane != nil {
			dispatchIDs = append(dispatchIDs, targetJob.ControlPlane.Dispatch.DispatchID)
			leaseCount += len(targetJob.ControlPlane.Ownership)
		} else {
			dispatchIDs = append(dispatchIDs, targetID)
		}
	}
	if len(targets) == 0 {
		s.mu.Unlock()
		return fmt.Errorf("job %q has no attached process", jobID)
	}
	if job.ControlPlane != nil {
		fence := controlplane.CancellationFence{
			APIVersion: controlplane.LifecycleAPIVersion, FenceID: "fence-" + job.ID,
			GoalID: job.ControlPlane.Goal.GoalID, GenerationID: job.ControlPlane.Generation.GenerationID,
			GenerationNumber: job.ControlPlane.Generation.GenerationNumber, State: controlplane.CancellationRequested,
			CancelledDispatchIDs: dispatchIDs, LiveDescendantCount: len(targets), ActiveLeaseCount: leaseCount,
			ActiveReservationCount: len(targets), LateEventDisposition: "record-only-stale",
			RequestedAt: time.Now().UTC().Format(time.RFC3339Nano),
		}
		if err := controlplane.SealCancellation(&fence); err != nil {
			s.mu.Unlock()
			return err
		}
		job.Cancellation = &fence
		if err := s.persistJob(*job); err != nil {
			s.mu.Unlock()
			return err
		}
	}
	eventErr := s.appendEventLocked(jobID, "cancel.requested", map[string]any{"cascade": len(targets), "dispatches": dispatchIDs})
	var durabilityErr error
	if eventErr != nil {
		durabilityErr = s.markDurabilityFailureLocked(jobID, "cancel event", eventErr)
	}
	s.mu.Unlock()
	for _, target := range targets {
		if target.worker {
			if err := s.sendWorkerFrame(target.runtime, WorkerFrame{Type: "cancel"}); err != nil {
				s.failWorkerTransport(target.id, fmt.Errorf("send durable cancellation: %w", err))
			}
		} else {
			_ = syscall.Kill(-target.pgid, syscall.SIGTERM)
		}
	}
	go func(targets []cancelTarget) {
		timer := time.NewTimer(2 * time.Second)
		defer timer.Stop()
		<-timer.C
		for _, target := range targets {
			s.mu.Lock()
			stillRunning := s.runtimes[target.id] == target.runtime
			s.mu.Unlock()
			if stillRunning && !target.worker {
				_ = syscall.Kill(-target.pgid, syscall.SIGKILL)
			}
		}
		s.drainCancellationFence(jobID, targetIDs)
	}(targets)
	return durabilityErr
}

func (s *Supervisor) cancellationTargetsLocked(root *Job) []string {
	result := []string{root.ID}
	if root.ControlPlane == nil {
		return result
	}
	rootDispatch := root.ControlPlane.Dispatch.DispatchID
	byDispatch := make(map[string]*Job)
	for _, job := range s.jobs {
		if job.ControlPlane != nil && job.ControlPlane.Goal.GoalID == root.ControlPlane.Goal.GoalID {
			byDispatch[job.ControlPlane.Dispatch.DispatchID] = job
		}
	}
	for _, candidate := range s.jobs {
		if candidate.ID == root.ID || candidate.ControlPlane == nil || terminal(candidate.Status) || candidate.ControlPlane.Goal.GoalID != root.ControlPlane.Goal.GoalID {
			continue
		}
		parent := candidate.ControlPlane.Dispatch.ParentDispatchID
		seen := map[string]struct{}{}
		for parent != "" {
			if parent == rootDispatch {
				result = append(result, candidate.ID)
				break
			}
			if _, duplicate := seen[parent]; duplicate {
				break
			}
			seen[parent] = struct{}{}
			ancestor := byDispatch[parent]
			if ancestor == nil || ancestor.ControlPlane == nil {
				break
			}
			parent = ancestor.ControlPlane.Dispatch.ParentDispatchID
		}
	}
	sort.Strings(result)
	return result
}

func (s *Supervisor) drainCancellationFence(jobID string, targetIDs []string) {
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		s.mu.Lock()
		live := 0
		for _, targetID := range targetIDs {
			if s.runtimes[targetID] != nil {
				live++
			}
		}
		job := s.jobs[jobID]
		if live == 0 && job != nil && job.Cancellation != nil {
			job.Cancellation.State = controlplane.CancellationDrained
			job.Cancellation.LiveDescendantCount = 0
			job.Cancellation.ActiveLeaseCount = 0
			job.Cancellation.ActiveReservationCount = 0
			job.Cancellation.DrainedAt = time.Now().UTC().Format(time.RFC3339Nano)
			if err := controlplane.SealCancellation(job.Cancellation); err == nil {
				_ = s.persistJob(*job)
				_ = s.appendEventLocked(jobID, "cancel.drained", map[string]any{"cascade": len(targetIDs)})
			}
			s.mu.Unlock()
			return
		}
		s.mu.Unlock()
		time.Sleep(10 * time.Millisecond)
	}
}

func (s *Supervisor) List() []Job {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.store.list(s.jobs)
}

func (s *Supervisor) Status(jobID string) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job, ok := s.jobs[jobID]
	if !ok {
		return Job{}, fmt.Errorf("job %q does not exist", jobID)
	}
	return *job, nil
}

func (s *Supervisor) Events(jobID string, after uint64) ([]Event, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.jobs[jobID]; !ok {
		return nil, fmt.Errorf("job %q does not exist", jobID)
	}
	return s.store.events(jobID, after)
}

func (s *Supervisor) Evidence(jobID string) (Evidence, error) {
	job, err := s.Status(jobID)
	if err != nil {
		return Evidence{}, err
	}
	events, err := s.Events(jobID, 0)
	if err != nil {
		return Evidence{}, err
	}
	return Evidence{Job: job, Events: events, RequiredChecks: job.Route.Evidence.RequiredChecks, RequiredArtifacts: job.Route.Evidence.RequiredArtifacts}, nil
}

func (s *Supervisor) readStream(jobID, stream string, reader io.Reader) {
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 32<<10), 1<<20)
	for scanner.Scan() {
		s.recordProviderLine(jobID, stream, append([]byte(nil), scanner.Bytes()...))
	}
	if err := scanner.Err(); err != nil && !errors.Is(err, os.ErrClosed) {
		s.mu.Lock()
		eventErr := s.appendEventLocked(jobID, "stream.error", map[string]any{"stream": stream, "error": err.Error()})
		runtime := s.runtimes[jobID]
		if eventErr != nil {
			s.markDurabilityFailureLocked(jobID, "stream error event", eventErr)
		}
		s.mu.Unlock()
		if eventErr != nil && runtime != nil && runtime.command.Process != nil {
			_ = syscall.Kill(-runtime.command.Process.Pid, syscall.SIGTERM)
		}
	}
}

func (s *Supervisor) recordProviderLine(jobID, stream string, line []byte) {
	line = []byte(strings.TrimSpace(string(line)))
	if len(line) == 0 {
		return
	}
	var payload map[string]any
	kind := "provider.event"
	if err := json.Unmarshal(line, &payload); err != nil {
		kind = "provider.malformed"
		payload = map[string]any{"stream": stream, "line": string(line), "error": err.Error()}
	} else {
		payload["stream"] = stream
	}
	redacted, _ := redactValue(payload).(map[string]any)
	s.mu.Lock()
	job := s.jobs[jobID]
	if job == nil {
		s.mu.Unlock()
		return
	}
	session, resultText, providerFailure, isResult := providerEventFields(job.Route.TargetHarness, redacted)
	if s.isStaleGenerationLocked(job) || isTerminalCancellation(job) {
		job.WorkflowDisposition = controlplane.DispositionStale
		job.UpdatedAt = time.Now().UTC()
		_ = s.persistJob(*job)
		_ = s.appendEventLocked(jobID, "provider.stale", redacted)
		runtime := s.runtimes[jobID]
		s.mu.Unlock()
		if isResult && runtime != nil && runtime.inputMode != InputPlain {
			runtime.writeMu.Lock()
			if !runtime.closed {
				_ = runtime.stdin.Close()
				runtime.closed = true
			}
			runtime.writeMu.Unlock()
		}
		return
	}
	violation := false
	metadataChanged := false
	if session != "" {
		if job.SessionID != "" && job.SessionID != session {
			violation = true
			job.Failure = "provider attempted to change immutable session identity"
		} else {
			job.SessionID = session
		}
		job.UpdatedAt = time.Now().UTC()
		metadataChanged = true
	}
	if resultText != "" {
		job.EvidenceSummary = appendBounded(job.EvidenceSummary, resultText, 16)
		job.UpdatedAt = time.Now().UTC()
		metadataChanged = true
	}
	if providerFailure != "" {
		job.Failure = providerFailure
		job.UpdatedAt = time.Now().UTC()
		metadataChanged = true
	}
	if violation {
		kind = "provider.protocol_error"
	}
	eventErr := s.appendEventLocked(jobID, kind, redacted)
	var persistenceErr error
	if eventErr != nil {
		persistenceErr = s.markDurabilityFailureLocked(jobID, "provider event", eventErr)
	} else if metadataChanged {
		if err := s.persistJob(*job); err != nil {
			persistenceErr = s.markDurabilityFailureLocked(jobID, "provider metadata", err)
		}
	}
	runtime := s.runtimes[jobID]
	s.mu.Unlock()
	if resultText != "" {
		if !s.recordAgentHandoff(jobID, resultText) {
			s.recordWorkflowResult(jobID, resultText)
		}
	}
	if (violation || persistenceErr != nil) && runtime != nil && runtime.command != nil && runtime.command.Process != nil {
		_ = syscall.Kill(-runtime.command.Process.Pid, syscall.SIGTERM)
	}
	if isResult && runtime != nil && !runtime.workerMode && runtime.inputMode != InputPlain {
		runtime.writeMu.Lock()
		if !runtime.closed {
			_ = runtime.stdin.Close()
			runtime.closed = true
		}
		runtime.writeMu.Unlock()
	}
}

func (s *Supervisor) isStaleGenerationLocked(job *Job) bool {
	if job == nil || job.ControlPlane == nil {
		return false
	}
	goalID := job.ControlPlane.Goal.GoalID
	generation := job.ControlPlane.Generation.GenerationNumber
	for _, candidate := range s.jobs {
		if candidate.ControlPlane != nil && candidate.ControlPlane.Goal.GoalID == goalID && candidate.ControlPlane.Generation.GenerationNumber > generation {
			return true
		}
	}
	return false
}

func providerEventFields(harness Harness, payload map[string]any) (session, result, failure string, terminal bool) {
	switch harness {
	case HarnessCodex:
		if payload["type"] == "thread.started" {
			session, _ = payload["thread_id"].(string)
		}
		if payload["type"] == "item.completed" {
			if item, ok := payload["item"].(map[string]any); ok && item["type"] == "agent_message" {
				result, _ = item["text"].(string)
			}
		}
	case HarnessClaude:
		if payload["type"] == "system" && payload["subtype"] == "init" {
			session, _ = payload["session_id"].(string)
		}
		if payload["type"] == "result" {
			result, _ = payload["result"].(string)
			terminal = true
			if subtype, _ := payload["subtype"].(string); subtype != "" && subtype != "success" {
				failure = "claude terminal result: " + subtype
			}
		}
	case HarnessAGY:
		if payload["event"] == "init" {
			session, _ = payload["conversation_id"].(string)
		}
		if payload["event"] == "result" {
			terminal = true
			if body, ok := payload["result"].(map[string]any); ok {
				result, _ = body["response"].(string)
				if status, _ := body["status"].(string); status != "" && status != "SUCCESS" {
					failure, _ = body["error"].(string)
					if failure == "" {
						failure = "agy terminal result: " + status
					}
				}
			}
		}
	}
	return session, result, failure, terminal
}

func (s *Supervisor) wait(jobID string, runtime *jobRuntime) {
	runtime.streams.Wait()
	err := runtime.command.Wait()
	exitCode := 0
	if err != nil {
		exitCode = -1
		var exitError *exec.ExitError
		if errors.As(err, &exitError) {
			exitCode = exitError.ExitCode()
		}
	}
	s.finishWorker(jobID, runtime, exitCode, err)
}

// finishWorker is shared by direct and worker-backed transports so terminal
// handoff/workflow authority remains identical.
func (s *Supervisor) finishWorker(jobID string, runtime *jobRuntime, exitCode int, processErr error) {
	now := time.Now().UTC()
	s.mu.Lock()
	job := s.jobs[jobID]
	if job == nil || s.runtimes[jobID] != runtime {
		s.mu.Unlock()
		return
	}
	delete(s.runtimes, jobID)
	job.ExitCode = &exitCode
	job.FinishedAt = &now
	job.UpdatedAt = now
	candidate := StatusSucceeded
	switch {
	case job.Failure != "":
		candidate = StatusFailed
	case runtime.canceled:
		candidate = StatusCanceled
	case processErr != nil:
		candidate = StatusFailed
		if job.Failure == "" {
			job.Failure = processErr.Error()
		}
	case !s.allowLegacyAdmission && job.ControlPlane != nil && (job.WorkflowResult == nil || job.WorkflowFailure != ""):
		candidate = StatusFailed
		if job.WorkflowFailure != "" {
			job.Failure = "workflow result rejected: " + job.WorkflowFailure
		} else {
			job.Failure = "terminal process did not return a validated workflow result"
		}
	case job.ControlPlane != nil && job.WorkflowResult != nil && job.WorkflowResult.Disposition == controlplane.DispositionCancelled:
		candidate = StatusCanceled
	case job.ControlPlane != nil && job.WorkflowResult != nil && job.WorkflowResult.Disposition != controlplane.DispositionSucceeded:
		candidate = StatusFailed
		job.Failure = "workflow result disposition " + string(job.WorkflowResult.Disposition)
	case !s.allowLegacyAdmission && job.ControlPlane == nil && job.Handoff == nil:
		candidate = StatusFailed
		if job.HandoffFailure != "" {
			job.Failure = "agent handoff rejected: " + job.HandoffFailure
		} else {
			job.Failure = "terminal process did not return an agent handoff"
		}
	case job.ControlPlane == nil && job.Handoff != nil && job.Handoff.Disposition == codingfleet.HandoffCancelled:
		candidate = StatusCanceled
	case job.ControlPlane == nil && job.Handoff != nil && job.Handoff.Disposition != codingfleet.HandoffSucceeded:
		candidate = StatusFailed
		job.Failure = "agent handoff disposition " + string(job.Handoff.Disposition) + ": " + job.Handoff.Result
	}
	if eventErr := s.appendEventLocked(jobID, "process.exited", map[string]any{"exitCode": exitCode, "status": candidate, "workflowDisposition": job.WorkflowDisposition}); eventErr != nil {
		job.Status = StatusFailed
		s.markDurabilityFailureLocked(jobID, "terminal process event", eventErr)
		s.mu.Unlock()
		closeRuntimeDone(runtime)
		return
	}
	job.Status = candidate
	if persistErr := s.persistJob(*job); persistErr != nil {
		job.Status = StatusFailed
		s.markDurabilityFailureLocked(jobID, "terminal job state", persistErr)
	}
	s.mu.Unlock()
	closeRuntimeDone(runtime)
	go s.publishVisibility(jobID, true)
	time.AfterFunc(TerminalVisibilityTTL, func() { s.clearVisibility(jobID) })
}

func (s *Supervisor) checkConcurrencyLocked(route Route, admission *ControlPlaneAdmission) error {
	active := 0
	var aggregate controlplane.BudgetAmount
	latestGeneration := uint64(0)
	latestGenerationID := ""
	for _, job := range s.jobs {
		if job.ControlPlane != nil && admission != nil && job.ControlPlane.Goal.GoalID == admission.Goal.GoalID {
			generation := job.ControlPlane.Generation
			if generation.GenerationNumber > latestGeneration {
				latestGeneration = generation.GenerationNumber
				latestGenerationID = generation.GenerationID
			}
		}
		if job.Status != StatusStarting && job.Status != StatusRunning {
			continue
		}
		active++
		if job.ControlPlane != nil && admission != nil && job.ControlPlane.Goal.GoalID == admission.Goal.GoalID {
			aggregate = addBudgetAmounts(aggregate, job.ControlPlane.Budget.Reserved)
			for _, existingClaim := range job.ControlPlane.Ownership {
				for _, requestedClaim := range admission.Ownership {
					if controlplane.OwnershipConflicts(existingClaim, requestedClaim) {
						return fmt.Errorf("ownership conflicts with active job %q", job.ID)
					}
				}
			}
		}
		if route.CapabilityMode == ModeWorkspaceWrite && job.Route.CapabilityMode == ModeWorkspaceWrite &&
			route.RepositoryRoot == job.Route.RepositoryRoot && ownershipConflicts(route.FileOwnership, job.Route.FileOwnership) {
			return fmt.Errorf("file ownership conflicts with active job %q", job.ID)
		}
	}
	if admission != nil {
		generation := admission.Generation
		switch {
		case latestGeneration == 0 && generation.GenerationNumber != 1:
			return fmt.Errorf("first admitted generation must be one")
		case latestGeneration > 0 && generation.GenerationNumber < latestGeneration:
			return fmt.Errorf("stale generation %d; current generation is %d", generation.GenerationNumber, latestGeneration)
		case latestGeneration > 0 && generation.GenerationNumber > latestGeneration+1:
			return fmt.Errorf("generation %d skips current generation %d", generation.GenerationNumber, latestGeneration)
		case latestGeneration > 0 && generation.GenerationNumber == latestGeneration+1 && generation.ParentGenerationID != latestGenerationID:
			return fmt.Errorf("new generation does not parent current generation %q", latestGenerationID)
		}
		aggregate = addBudgetAmounts(aggregate, admission.Budget.Reserved)
		ceiling := admission.Authority.ParentGrant.Budget
		if aggregate.Delegates > ceiling.MaxDelegates || aggregate.Writers > ceiling.MaxWriters || aggregate.Tokens > ceiling.MaxTokens || aggregate.DurationSeconds > ceiling.MaxDurationSeconds {
			return fmt.Errorf("aggregate descendant budget exceeds parent authority")
		}
	}
	if active >= s.maxConcurrent {
		return fmt.Errorf("run-plane concurrency limit %d reached", s.maxConcurrent)
	}
	return nil
}

func addBudgetAmounts(left, right controlplane.BudgetAmount) controlplane.BudgetAmount {
	return controlplane.BudgetAmount{
		Delegates: left.Delegates + right.Delegates, Writers: left.Writers + right.Writers,
		Tokens: left.Tokens + right.Tokens, DurationSeconds: left.DurationSeconds + right.DurationSeconds,
	}
}

func (s *Supervisor) appendEventLocked(jobID, kind string, payload map[string]any) error {
	sequence := s.sequence[jobID] + 1
	event := Event{Sequence: sequence, JobID: jobID, At: time.Now().UTC(), Kind: kind, Payload: boundEventPayload(payload)}
	if err := s.persistEvent(event); err != nil {
		return fmt.Errorf("persist %s event: %w", kind, err)
	}
	s.sequence[jobID] = sequence
	return nil
}

// markDurabilityFailureLocked records a persistence failure without calling
// itself recursively. It returns every failure so synchronous callers can
// propagate it; asynchronous callers retain the same truth in memory and force
// the provider process toward a failed terminal state.
func (s *Supervisor) markDurabilityFailureLocked(jobID, operation string, cause error) error {
	job := s.jobs[jobID]
	if job == nil {
		return cause
	}
	message := fmt.Sprintf("durable %s failed: %v", operation, cause)
	if job.Failure == "" {
		job.Failure = message
	} else if !strings.Contains(job.Failure, message) {
		job.Failure += "; " + message
	}
	job.UpdatedAt = time.Now().UTC()
	stateErr := s.persistJob(*job)
	eventErr := s.appendEventLocked(jobID, "persistence.failed", map[string]any{"operation": operation, "error": cause.Error()})
	var finalErr error
	if eventErr != nil {
		job.Failure += "; failure event could not be persisted: " + eventErr.Error()
		finalErr = s.persistJob(*job)
	}
	return errors.Join(cause, stateErr, eventErr, finalErr)
}

const maxEventPayloadBytes = 128 << 10

func boundEventPayload(payload map[string]any) map[string]any {
	if payload == nil {
		return nil
	}
	encoded, err := json.Marshal(payload)
	if err == nil && len(encoded) <= maxEventPayloadBytes {
		return payload
	}
	bounded := map[string]any{"truncated": true}
	if err != nil {
		bounded["error"] = "payload could not be encoded"
		return bounded
	}
	digest := sha256.Sum256(encoded)
	bounded["bytes"] = len(encoded)
	bounded["sha256"] = hex.EncodeToString(digest[:])
	return bounded
}

func (s *Supervisor) failStart(jobID string, cause error) error {
	now := time.Now().UTC()
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[jobID]
	if job == nil {
		return cause
	}
	job.Status = StatusFailed
	job.Failure = cause.Error()
	job.FinishedAt = &now
	job.UpdatedAt = now
	stateErr := s.persistJob(*job)
	eventErr := s.appendEventLocked(jobID, "process.start_failed", map[string]any{"error": cause.Error()})
	if stateErr != nil || eventErr != nil {
		return errors.Join(stateErr, eventErr, s.markDurabilityFailureLocked(jobID, "start failure", errors.Join(stateErr, eventErr)))
	}
	return nil
}

func (s *Supervisor) rollbackStartedProcess(jobID string, runtime *jobRuntime, stdout, stderr io.ReadCloser, pgid int, cause error) error {
	_ = runtime.stdin.Close()
	_ = stdout.Close()
	_ = stderr.Close()
	cleanupErr := terminateStartedCommand(runtime.command, pgid)
	now := time.Now().UTC()
	s.mu.Lock()
	job := s.jobs[jobID]
	var stateErr, eventErr, durabilityErr error
	if job != nil {
		job.PID = runtime.command.Process.Pid
		job.PGID = pgid
		job.Status = StatusFailed
		job.Failure = cause.Error()
		if cleanupErr != nil {
			job.Failure += "; cleanup: " + cleanupErr.Error()
		}
		job.FinishedAt = &now
		job.UpdatedAt = now
		stateErr = s.persistJob(*job)
		eventErr = s.appendEventLocked(jobID, "process.start_rolled_back", map[string]any{"error": cause.Error(), "cleanupError": errorString(cleanupErr)})
		if stateErr != nil || eventErr != nil {
			durabilityErr = s.markDurabilityFailureLocked(jobID, "start rollback", errors.Join(stateErr, eventErr))
		}
	}
	s.mu.Unlock()
	return errors.Join(cause, cleanupErr, stateErr, eventErr, durabilityErr)
}

func terminateStartedCommand(command *exec.Cmd, pgid int) error {
	if command == nil || command.Process == nil || pgid <= 0 {
		return fmt.Errorf("started process group identity is unavailable")
	}
	waited := make(chan error, 1)
	go func() { waited <- command.Wait() }()
	_ = syscall.Kill(-pgid, syscall.SIGTERM)
	select {
	case <-waited:
	case <-time.After(500 * time.Millisecond):
		_ = syscall.Kill(-pgid, syscall.SIGKILL)
		select {
		case <-waited:
		case <-time.After(2 * time.Second):
			return fmt.Errorf("process leader did not exit after TERM/KILL")
		}
	}
	if processGroupExists(pgid) {
		_ = syscall.Kill(-pgid, syscall.SIGKILL)
		deadline := time.Now().Add(500 * time.Millisecond)
		for time.Now().Before(deadline) && processGroupExists(pgid) {
			time.Sleep(10 * time.Millisecond)
		}
	}
	if processGroupExists(pgid) {
		return fmt.Errorf("process group %d still exists after TERM/KILL", pgid)
	}
	return nil
}

func processGroupExists(pgid int) bool {
	err := syscall.Kill(-pgid, 0)
	return err == nil || errors.Is(err, syscall.EPERM)
}

func errorString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

func (s *Supervisor) reconcile() error {
	var visibilityJobs []string
	for id, job := range s.jobs {
		events, err := s.store.events(id, 0)
		if err == nil && len(events) > 0 {
			s.sequence[id] = events[len(events)-1].Sequence
		}
		if job.Status != StatusStarting && job.Status != StatusRunning {
			if job.Visibility != nil {
				visibilityJobs = append(visibilityJobs, id)
			}
			continue
		}
		confirmed, note := reconcileProcessGroup(job)
		now := time.Now().UTC()
		if confirmed {
			job.Status = StatusRecovered
		} else {
			job.Status = StatusFailed
			job.Failure = "restart cleanup could not be confirmed"
		}
		job.RecoveryNote = note
		job.FinishedAt = &now
		job.UpdatedAt = now
		if err := s.persistJob(*job); err != nil {
			return err
		}
		if err := s.appendEventLocked(id, "restart.reconciled", map[string]any{"previousPid": job.PID}); err != nil {
			return err
		}
		if job.Visibility != nil {
			visibilityJobs = append(visibilityJobs, id)
		}
	}
	for _, id := range visibilityJobs {
		s.recoverVisibility(id)
	}
	return nil
}

func reconcileProcessGroup(job *Job) (bool, string) {
	if job.PID <= 0 || job.ProcessStart == "" {
		return true, "no persisted process identity remained"
	}
	current, err := readProcessStart(job.PID)
	if os.IsNotExist(err) {
		return true, "persisted process no longer exists"
	}
	if err != nil {
		return false, "could not inspect persisted process identity: " + err.Error()
	}
	if current != job.ProcessStart {
		return true, "PID was reused; no matching detached process was signaled"
	}
	pgid := job.PGID
	if pgid <= 0 {
		return false, "matching process had no persisted process-group identity"
	}
	_ = syscall.Kill(-pgid, syscall.SIGTERM)
	if waitProcessIdentityGone(job.PID, job.ProcessStart, 500*time.Millisecond) {
		return true, "matching detached process group terminated after SIGTERM"
	}
	_ = syscall.Kill(-pgid, syscall.SIGKILL)
	if waitProcessIdentityGone(job.PID, job.ProcessStart, 500*time.Millisecond) {
		return true, "matching detached process group required SIGKILL"
	}
	return false, "matching detached process group survived TERM/KILL reconciliation"
}

func waitProcessIdentityGone(pid int, identity string, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		current, err := readProcessStart(pid)
		if err != nil || current != identity {
			return true
		}
		time.Sleep(10 * time.Millisecond)
	}
	return false
}

func readProcessStart(pid int) (string, error) {
	data, err := os.ReadFile(filepath.Join("/proc", strconv.Itoa(pid), "stat"))
	if err != nil {
		return "", err
	}
	text := string(data)
	end := strings.LastIndex(text, ")")
	if end < 0 {
		return "", fmt.Errorf("malformed process stat")
	}
	fields := strings.Fields(text[end+1:])
	if len(fields) <= 19 {
		return "", fmt.Errorf("malformed process stat")
	}
	return fields[19], nil // field 22 overall; fields begin at stat field 3.
}

func randomID() (string, error) {
	data := make([]byte, 16)
	if _, err := rand.Read(data); err != nil {
		return "", fmt.Errorf("generate job ID: %w", err)
	}
	return hex.EncodeToString(data), nil
}

func digestString(value string) string {
	// A prompt/message digest is sufficient for audit correlation without
	// persisting potentially sensitive assignment text.
	return fmt.Sprintf("%x", sha256Sum([]byte(value)))
}

func sha256Sum(value []byte) [32]byte {
	return sha256.Sum256(value)
}

func terminal(status JobStatus) bool {
	return status == StatusSucceeded || status == StatusFailed || status == StatusCanceled || status == StatusRecovered
}

func findStringField(value any, keys ...string) string {
	wanted := stringSet(keys)
	var walk func(any) string
	walk = func(current any) string {
		switch typed := current.(type) {
		case map[string]any:
			for key, item := range typed {
				if _, ok := wanted[key]; ok {
					if text, ok := item.(string); ok {
						return text
					}
				}
				if found := walk(item); found != "" {
					return found
				}
			}
		case []any:
			for _, item := range typed {
				if found := walk(item); found != "" {
					return found
				}
			}
		}
		return ""
	}
	return walk(value)
}

func appendBounded(values []string, value string, maximum int) []string {
	if len(value) > 4096 {
		value = value[:4096] + "[TRUNCATED]"
	}
	values = append(values, value)
	if len(values) > maximum {
		values = values[len(values)-maximum:]
	}
	return values
}
