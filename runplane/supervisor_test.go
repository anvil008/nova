package runplane

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
)

func TestSupervisorRunsWithoutPromptInArgvAndCollectsRedactedReplayEvidence(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "opus-exact", "high")
	installFakeClaude(t, `
for arg in "$@"; do
  case "$arg" in *PROMPT-MUST-STAY-OFF-ARGV*) exit 97;; esac
done
IFS= read -r input
printf '%s\n' '{"type":"system","subtype":"init","session_id":"session-123","authorization":"Bearer top-secret"}'
printf '%s\n' 'malformed token=secretvalue'
printf '%s\n' '{"type":"result","result":"done","api_key":"key-secretvalue"}'
`)
	supervisor := newTestSupervisor(t, roots, 20, 4)
	request := testStartRequest(repo, "workflow-executor", ModeWorkspaceWrite, []string{"runplane"}, "PROMPT-MUST-STAY-OFF-ARGV")
	job, err := supervisor.Start(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	job = waitTerminal(t, supervisor, job.ID)
	if job.Status != StatusSucceeded || job.SessionID != "session-123" {
		t.Fatalf("job = %+v", job)
	}
	evidence, err := supervisor.Evidence(job.ID)
	if err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(evidence)
	text := string(encoded)
	if strings.Contains(text, "top-secret") || strings.Contains(text, "secretvalue") {
		t.Fatalf("evidence leaked secret: %s", text)
	}
	if !strings.Contains(text, "[REDACTED]") || !strings.Contains(text, "provider.malformed") {
		t.Fatalf("evidence lacks redaction/malformed event: %s", text)
	}
	events, err := supervisor.Events(job.ID, evidence.Events[0].Sequence)
	if err != nil || len(events) != len(evidence.Events)-1 {
		t.Fatalf("replay events = %d, err = %v", len(events), err)
	}
}

func TestSupervisorCancellationRaceAndProcessGroupCleanup(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "opus-exact", "high")
	installFakeClaude(t, `
IFS= read -r input
printf '%s\n' '{"type":"system","subtype":"init","session_id":"session-cancel"}'
sleep 30
`)
	supervisor := newTestSupervisor(t, roots, 20, 4)
	job, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-executor", ModeWorkspaceWrite, []string{"runplane"}, "cancel me"))
	if err != nil {
		t.Fatal(err)
	}
	var wait sync.WaitGroup
	for range 2 {
		wait.Add(1)
		go func() { defer wait.Done(); _ = supervisor.Cancel(job.ID) }()
	}
	wait.Wait()
	job = waitTerminal(t, supervisor, job.ID)
	if job.Status != StatusCanceled {
		t.Fatalf("status = %q, want canceled; failure=%q", job.Status, job.Failure)
	}
	if err := syscall.Kill(job.PID, 0); err == nil {
		t.Fatalf("process %d still exists after cancellation", job.PID)
	}
}

func TestStartRollsBackProcessWhenRunningIdentityCannotBePersisted(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "opus-exact", "high")
	installFakeClaude(t, `IFS= read -r input; sleep 30`)
	supervisor := newTestSupervisor(t, roots, 20, 4)
	originalPersist := supervisor.persistJob
	launchedPID := 0
	supervisor.persistJob = func(job Job) error {
		if job.Status == StatusRunning {
			launchedPID = job.PID
			return errors.New("forced running-state persistence failure")
		}
		return originalPersist(job)
	}
	_, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-executor", ModeWorkspaceWrite, []string{"runplane"}, "must roll back"))
	if err == nil || !strings.Contains(err.Error(), "persist running process identity") {
		t.Fatalf("start error = %v", err)
	}
	if launchedPID <= 0 {
		t.Fatal("running-state persistence was not attempted with a process identity")
	}
	if err := syscall.Kill(launchedPID, 0); err == nil {
		t.Fatalf("process %d survived failed durable admission", launchedPID)
	}
	jobs := supervisor.List()
	if len(jobs) != 1 || jobs[0].Status != StatusFailed || !strings.Contains(jobs[0].Failure, "persistence failure") {
		t.Fatalf("rolled-back job = %+v", jobs)
	}
}

func TestTerminalPersistenceWaitsForBothStreamsAndFollowsFinalEvent(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	command := exec.Command("true")
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	job := &Job{APIVersion: APIVersion, ID: "stream-order", Route: Route{TargetHarness: HarnessClaude}, Status: StatusRunning, StartedAt: now, UpdatedAt: now}
	runtime := &jobRuntime{command: command, inputMode: InputPlain}
	supervisor.jobs[job.ID] = job
	supervisor.runtimes[job.ID] = runtime
	if err := supervisor.persistJob(*job); err != nil {
		t.Fatal(err)
	}
	stdoutGate := make(chan struct{})
	stderrGate := make(chan struct{})
	runtime.streams.Add(2)
	go func() {
		defer runtime.streams.Done()
		supervisor.readStream(job.ID, "stdout", &gatedReader{gate: stdoutGate, data: []byte("{\"type\":\"result\",\"result\":\"last provider event\"}\n")})
	}()
	go func() {
		defer runtime.streams.Done()
		supervisor.readStream(job.ID, "stderr", &gatedReader{gate: stderrGate})
	}()
	go supervisor.wait(job.ID, runtime)
	close(stdoutGate)
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		observed, _ := supervisor.Status(job.ID)
		if len(observed.EvidenceSummary) > 0 {
			if terminal(observed.Status) {
				t.Fatalf("job became terminal before stderr drained: %+v", observed)
			}
			break
		}
		time.Sleep(time.Millisecond)
	}
	close(stderrGate)
	finished := waitTerminal(t, supervisor, job.ID)
	if finished.Status != StatusSucceeded || len(finished.EvidenceSummary) != 1 {
		t.Fatalf("finished job = %+v", finished)
	}
	events, err := supervisor.Events(job.ID, 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(events) < 2 || events[len(events)-2].Kind != "provider.event" || events[len(events)-1].Kind != "process.exited" {
		t.Fatalf("terminal event order = %+v", events)
	}
}

func TestTerminalContractGateFollowsAdmissionKind(t *testing.T) {
	tests := []struct {
		name            string
		controlPlane    *ControlPlaneAdmission
		workflowResult  *controlplane.WorkflowResult
		workflowFailure string
		handoff         *codingfleet.AgentHandoff
		wantStatus      JobStatus
		wantFailure     string
	}{
		{
			name: "validated heavyweight success", controlPlane: &ControlPlaneAdmission{},
			workflowResult: &controlplane.WorkflowResult{Disposition: controlplane.DispositionSucceeded},
			wantStatus:     StatusSucceeded,
		},
		{
			name: "missing heavyweight result", controlPlane: &ControlPlaneAdmission{},
			wantStatus: StatusFailed, wantFailure: "did not return a validated workflow result",
		},
		{
			name: "failed heavyweight result", controlPlane: &ControlPlaneAdmission{},
			workflowResult: &controlplane.WorkflowResult{Disposition: controlplane.DispositionFailed},
			wantStatus:     StatusFailed, wantFailure: "workflow result disposition failed",
		},
		{
			name: "rejected heavyweight result", controlPlane: &ControlPlaneAdmission{},
			workflowResult:  &controlplane.WorkflowResult{Disposition: controlplane.DispositionSucceeded},
			workflowFailure: "contract mismatch", wantStatus: StatusFailed, wantFailure: "workflow result rejected",
		},
		{
			name:       "validated compact handoff success",
			handoff:    &codingfleet.AgentHandoff{Disposition: codingfleet.HandoffSucceeded},
			wantStatus: StatusSucceeded,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			supervisor := newTestSupervisorWithLegacy(t, testDefinitionRoots(t), 20, 4, false)
			command := exec.Command("true")
			if err := command.Start(); err != nil {
				t.Fatal(err)
			}
			now := time.Now().UTC()
			job := &Job{
				APIVersion: APIVersion, ID: "terminal-contract", Route: Route{TargetHarness: HarnessClaude},
				ControlPlane: test.controlPlane, WorkflowResult: test.workflowResult, WorkflowFailure: test.workflowFailure,
				Handoff: test.handoff, Status: StatusRunning, StartedAt: now, UpdatedAt: now,
			}
			if test.workflowResult != nil {
				job.WorkflowDisposition = test.workflowResult.Disposition
			}
			runtime := &jobRuntime{command: command, inputMode: InputPlain}
			supervisor.jobs[job.ID] = job
			supervisor.runtimes[job.ID] = runtime
			if err := supervisor.persistJob(*job); err != nil {
				t.Fatal(err)
			}
			supervisor.wait(job.ID, runtime)
			got, err := supervisor.Status(job.ID)
			if err != nil {
				t.Fatal(err)
			}
			if got.Status != test.wantStatus || (test.wantFailure != "" && !strings.Contains(got.Failure, test.wantFailure)) {
				t.Fatalf("terminal job = %+v, want status %q failure containing %q", got, test.wantStatus, test.wantFailure)
			}
		})
	}
}

func TestRealCommandPipesDrainFinalProviderAndStderrEventsBeforeExit(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 100, 4)
	command := exec.Command("sh", "-c", `printf '%s\n' '{"type":"system","subtype":"init","session_id":"real-pipe"}'; printf '%s\n' '{"type":"result","subtype":"success","result":"real final result"}'; printf '%s\n' 'real-stderr-tail' >&2`)
	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	stderr, err := command.StderrPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	job := &Job{APIVersion: APIVersion, ID: "real-pipe-order", Route: Route{TargetHarness: HarnessClaude}, Status: StatusRunning, StartedAt: now, UpdatedAt: now}
	runtime := &jobRuntime{command: command, inputMode: InputPlain}
	supervisor.jobs[job.ID] = job
	supervisor.runtimes[job.ID] = runtime
	if err := supervisor.persistJob(*job); err != nil {
		t.Fatal(err)
	}
	runtime.streams.Add(2)
	go func() {
		defer runtime.streams.Done()
		supervisor.readStream(job.ID, "stdout", stdout)
	}()
	go func() {
		defer runtime.streams.Done()
		supervisor.readStream(job.ID, "stderr", stderr)
	}()
	go supervisor.wait(job.ID, runtime)
	finished := waitTerminal(t, supervisor, job.ID)
	if finished.Status != StatusSucceeded || len(finished.EvidenceSummary) != 1 || finished.EvidenceSummary[0] != "real final result" {
		t.Fatalf("real pipe job = %+v", finished)
	}
	events, err := supervisor.Events(job.ID, 0)
	if err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(events)
	if !strings.Contains(string(encoded), "real-stderr-tail") {
		t.Fatalf("stderr tail was truncated: %s", encoded)
	}
	if len(events) < 4 || events[len(events)-1].Kind != "process.exited" {
		t.Fatalf("real pipe final ordering = %+v", events)
	}
}

func TestTerminalSuccessRequiresDurableJobAndEventState(t *testing.T) {
	for _, test := range []struct {
		name        string
		operation   string
		inject      func(*Supervisor)
		wantExitEvt bool
	}{
		{
			name:      "terminal-job-state",
			operation: "terminal job state",
			inject: func(supervisor *Supervisor) {
				original := supervisor.persistJob
				supervisor.persistJob = func(job Job) error {
					if job.Status == StatusSucceeded {
						return errors.New("forced terminal job persistence failure")
					}
					return original(job)
				}
			},
			wantExitEvt: true,
		},
		{
			name:      "terminal-process-event",
			operation: "terminal process event",
			inject: func(supervisor *Supervisor) {
				original := supervisor.persistEvent
				supervisor.persistEvent = func(event Event) error {
					if event.Kind == "process.exited" {
						return errors.New("forced terminal event persistence failure")
					}
					return original(event)
				}
			},
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			repo := testRepository(t)
			roots := testDefinitionRoots(t)
			writeDefinition(t, roots, HarnessClaude, "workflow-research", "", "")
			installFakeClaude(t, `
IFS= read -r input
printf '%s\n' '{"type":"system","subtype":"init","session_id":"durability-session"}'
printf '%s\n' '{"type":"result","subtype":"success","result":"durable result"}'
`)
			supervisor := newTestSupervisor(t, roots, 20, 4)
			test.inject(supervisor)
			job, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-research", ModeReadOnly, nil, "durability"))
			if err != nil {
				t.Fatal(err)
			}
			job = waitTerminal(t, supervisor, job.ID)
			if job.Status != StatusFailed || !strings.Contains(job.Failure, test.operation) {
				t.Fatalf("non-durable terminal job = %+v", job)
			}
			persisted, err := supervisor.store.loadJobs()
			if err != nil {
				t.Fatal(err)
			}
			if persisted[job.ID].Status != StatusFailed || !strings.Contains(persisted[job.ID].Failure, test.operation) {
				t.Fatalf("persisted non-durable job = %+v", persisted[job.ID])
			}
			events, err := supervisor.Events(job.ID, 0)
			if err != nil {
				t.Fatal(err)
			}
			foundExit, foundFailure := false, false
			for _, event := range events {
				foundExit = foundExit || event.Kind == "process.exited"
				foundFailure = foundFailure || event.Kind == "persistence.failed"
			}
			if foundExit != test.wantExitEvt || !foundFailure {
				t.Fatalf("durability events = %+v", events)
			}
		})
	}
}

func TestProviderEvidencePersistenceFailureCannotEndInSuccess(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-research", "", "")
	installFakeClaude(t, `
IFS= read -r input
printf '%s\n' '{"type":"system","subtype":"init","session_id":"metadata-session"}'
printf '%s\n' '{"type":"result","subtype":"success","result":"must be durable"}'
`)
	supervisor := newTestSupervisor(t, roots, 20, 4)
	original := supervisor.persistJob
	supervisor.persistJob = func(job Job) error {
		if job.Status == StatusRunning && len(job.EvidenceSummary) > 0 {
			return errors.New("forced provider evidence persistence failure")
		}
		return original(job)
	}
	job, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-research", ModeReadOnly, nil, "metadata durability"))
	if err != nil {
		t.Fatal(err)
	}
	job = waitTerminal(t, supervisor, job.ID)
	if job.Status != StatusFailed || !strings.Contains(job.Failure, "provider metadata") {
		t.Fatalf("provider evidence failure job = %+v", job)
	}
	persisted, err := supervisor.store.loadJobs()
	if err != nil {
		t.Fatal(err)
	}
	if persisted[job.ID].Status != StatusFailed {
		t.Fatalf("provider evidence failure persisted as %+v", persisted[job.ID])
	}
}

func TestSupervisorSendAndResumeUseStreamStdin(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-research", "opus-exact", "high")
	installFakeClaude(t, `
for arg in "$@"; do
  case "$arg" in *SECOND-MESSAGE-NOT-ARGV*) exit 97;; esac
done
IFS= read -r first
case " $* " in *" --resume session-stream "*)
  printf '%s\n' '{"type":"result","session_id":"session-stream","result":"resumed"}'
  exit 0
esac
printf '%s\n' '{"type":"system","subtype":"init","session_id":"session-stream"}'
IFS= read -r second
case "$second" in *SECOND-MESSAGE-NOT-ARGV*) :;; *) exit 96;; esac
printf '%s\n' '{"type":"result","session_id":"session-stream","result":"sent"}'
`)
	supervisor := newTestSupervisor(t, roots, 20, 4)
	job, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-research", ModeReadOnly, nil, "first message"))
	if err != nil {
		t.Fatal(err)
	}
	if err := supervisor.Send(job.ID, "SECOND-MESSAGE-NOT-ARGV"); err != nil {
		t.Fatal(err)
	}
	job = waitTerminal(t, supervisor, job.ID)
	if job.SessionID != "session-stream" || job.Status != StatusSucceeded {
		t.Fatalf("sent job = %+v", job)
	}
	resumed, err := supervisor.Resume(context.Background(), job.ID, "resume via stdin")
	if err != nil {
		t.Fatal(err)
	}
	if resumed.ID == job.ID || resumed.Route.DispatchID != resumed.ID || resumed.Route.ParentDispatchID != job.Route.DispatchID {
		t.Fatalf("resumed run lineage = parent job %q dispatch %q, child job %q route %+v", job.ID, job.Route.DispatchID, resumed.ID, resumed.Route)
	}
	resumed = waitTerminal(t, supervisor, resumed.ID)
	if resumed.Status != StatusSucceeded || len(resumed.EvidenceSummary) == 0 || resumed.EvidenceSummary[0] != "resumed" {
		t.Fatalf("resumed job = %+v", resumed)
	}
	events, err := supervisor.Events(resumed.ID, 0)
	if err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(events)
	if !strings.Contains(string(encoded), `"--resume","session-stream"`) {
		t.Fatalf("resume argv missing persisted session: %s", encoded)
	}
}

func TestProductionTerminalNarrativeWithoutHandoffFails(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-research", "opus-exact", "high")
	installFakeClaude(t, `
IFS= read -r input
printf '%s\n' '{"type":"system","subtype":"init","session_id":"narrative-only"}'
printf '%s\n' '{"type":"result","subtype":"success","result":"narrative without a handoff"}'
`)
	supervisor := newTestSupervisorWithLegacy(t, roots, 20, 4, false)
	job, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-research", ModeReadOnly, nil, "require a handoff"))
	if err != nil {
		t.Fatal(err)
	}
	job = waitTerminal(t, supervisor, job.ID)
	if job.Status != StatusFailed || !strings.Contains(job.Failure, "did not return an agent handoff") {
		t.Fatalf("narrative-only production job = %+v", job)
	}
}

func TestResumeDeniesConcurrentDuplicateAdmission(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	now := time.Now().UTC()
	job := &Job{APIVersion: APIVersion, ID: "resume-parent", Route: Route{TargetHarness: HarnessClaude}, Status: StatusSucceeded, SessionID: "session", StartedAt: now, UpdatedAt: now}
	supervisor.jobs[job.ID] = job
	supervisor.resuming[sessionKey(HarnessClaude, job.SessionID)] = true
	if _, err := supervisor.Resume(context.Background(), job.ID, "again"); err == nil || !strings.Contains(err.Error(), "in progress") {
		t.Fatalf("duplicate resume error=%v", err)
	}
}

func TestResumeRejectsControlPlaneJobWithoutNewSealedAdmission(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	now := time.Now().UTC()
	job := &Job{
		APIVersion: APIVersion, ID: "control-plane-parent", Route: Route{TargetHarness: HarnessClaude},
		ControlPlane: &ControlPlaneAdmission{}, Status: StatusSucceeded, SessionID: "control-plane-session",
		StartedAt: now, UpdatedAt: now,
	}
	supervisor.jobs[job.ID] = job
	if _, err := supervisor.Resume(context.Background(), job.ID, "again"); err == nil || !strings.Contains(err.Error(), "newly sealed admission") {
		t.Fatalf("control-plane resume error = %v", err)
	}
}

func TestResumeSingleFlightUsesProviderSessionAcrossLineage(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	now := time.Now().UTC()
	parent := &Job{APIVersion: APIVersion, ID: "lineage-parent", Route: Route{TargetHarness: HarnessClaude}, Status: StatusSucceeded, SessionID: "shared-session", StartedAt: now, UpdatedAt: now}
	activeChild := &Job{APIVersion: APIVersion, ID: "lineage-child", Route: Route{TargetHarness: HarnessClaude}, Status: StatusRunning, SessionID: "shared-session", ResumeOf: parent.ID, StartedAt: now, UpdatedAt: now}
	supervisor.jobs[parent.ID] = parent
	supervisor.jobs[activeChild.ID] = activeChild
	if _, err := supervisor.Resume(context.Background(), parent.ID, "again"); err == nil || !strings.Contains(err.Error(), "active job") {
		t.Fatalf("lineage session duplicate error=%v", err)
	}
}

func TestResumedSessionIdentityIsInitializedAndCannotBeReplaced(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-research", "opus-exact", "high")
	installFakeClaude(t, `
IFS= read -r input
case " $* " in *" --resume session-stored "*)
  printf '%s\n' '{"type":"system","subtype":"init","session_id":"session-replaced"}'
  printf '%s\n' '{"type":"result","subtype":"success","result":"should fail"}'
  exit 0
esac
printf '%s\n' '{"type":"system","subtype":"init","session_id":"session-stored"}'
printf '%s\n' '{"type":"result","subtype":"success","result":"initial"}'
`)
	supervisor := newTestSupervisor(t, roots, 20, 4)
	parent, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-research", ModeReadOnly, nil, "initial"))
	if err != nil {
		t.Fatal(err)
	}
	parent = waitTerminal(t, supervisor, parent.ID)
	child, err := supervisor.Resume(context.Background(), parent.ID, "resume")
	if err != nil {
		t.Fatal(err)
	}
	if child.SessionID != "session-stored" {
		t.Fatalf("resumed child did not initialize stored session: %+v", child)
	}
	child = waitTerminal(t, supervisor, child.ID)
	if child.Status != StatusFailed || child.SessionID != "session-stored" || !strings.Contains(child.Failure, "immutable") {
		t.Fatalf("resumed session replacement job = %+v", child)
	}
}

func TestSupervisorAllowsReadOnlyAndDisjointWritersButRejectsOverlap(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "opus-exact", "high")
	writeDefinition(t, roots, HarnessClaude, "workflow-research", "opus-exact", "high")
	installFakeClaude(t, `IFS= read -r input; sleep 30`)
	supervisor := newTestSupervisor(t, roots, 20, 4)
	first, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-executor", ModeWorkspaceWrite, []string{"runplane"}, "writer one"))
	if err != nil {
		t.Fatal(err)
	}
	second, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-executor", ModeWorkspaceWrite, []string{"cmd/swarm-runplane"}, "writer two"))
	if err != nil {
		t.Fatalf("disjoint writer rejected: %v", err)
	}
	if _, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-executor", ModeWorkspaceWrite, []string{"runplane/store.go"}, "overlap")); err == nil || !strings.Contains(err.Error(), "conflicts") {
		t.Fatalf("overlap error = %v", err)
	}
	reader, err := supervisor.Start(context.Background(), testStartRequest(repo, "workflow-research", ModeReadOnly, nil, "reader"))
	if err != nil {
		t.Fatalf("read-only route rejected: %v", err)
	}
	for _, id := range []string{first.ID, second.ID, reader.ID} {
		_ = supervisor.Cancel(id)
		waitTerminal(t, supervisor, id)
	}
}

func TestRestartRecoveryTerminatesOnlyMatchingDetachedProcess(t *testing.T) {
	command := exec.Command("sleep", "30")
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	waited := make(chan error, 1)
	go func() { waited <- command.Wait() }()
	defer func() { _ = syscall.Kill(-command.Process.Pid, syscall.SIGKILL) }()
	identity, err := readProcessStart(command.Process.Pid)
	if err != nil {
		t.Fatal(err)
	}
	state := t.TempDir()
	store, err := newStateStore(state, 20)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	job := Job{APIVersion: APIVersion, ID: "recovery-job", Status: StatusRunning, PID: command.Process.Pid, PGID: command.Process.Pid, ProcessStart: identity, StartedAt: now, UpdatedAt: now}
	if err := store.saveJob(job); err != nil {
		t.Fatal(err)
	}
	supervisor, err := NewSupervisor(Options{StateDir: state, Discoverer: Discoverer{Runner: fakeCommandRunner{}}})
	if err != nil {
		t.Fatal(err)
	}
	recovered, err := supervisor.Status(job.ID)
	if err != nil || recovered.Status != StatusRecovered {
		t.Fatalf("recovered = %+v, err = %v", recovered, err)
	}
	select {
	case <-waited:
		return
	case <-time.After(2 * time.Second):
		t.Fatal("detached matching process survived reconciliation")
	}
}

func TestStateDirectoryRefusesSecondLiveOwnerWithoutSignalingJobs(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-research", "opus-exact", "high")
	installFakeClaude(t, `IFS= read -r input; sleep 30`)
	state := t.TempDir()
	discoverer := Discoverer{Roots: roots, Runner: fakeCommandRunner{outputs: map[string]string{
		"claude --version": "2.1.test",
		"claude --help":    "--agent --agents --setting-sources --model --effort <level> (low, medium, high) --input-format stream-json --output-format --resume",
	}}}
	_, _, roles := discoverer.installedRoleMetadata(HarnessClaude, nil)
	discoverer.static = map[Harness]Capability{HarnessClaude: {
		Harness: HarnessClaude, Available: true, ModelEfforts: []ModelEffort{{Model: "opus", Effort: "high", Reference: "exact"}}, Roles: roles,
	}}
	first, err := NewSupervisor(Options{StateDir: state, Discoverer: discoverer, AllowLegacyAdmission: true})
	if err != nil {
		t.Fatal(err)
	}
	job, err := first.Start(context.Background(), testStartRequest(repo, "workflow-research", ModeReadOnly, nil, "keep alive"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewSupervisor(Options{StateDir: state, Discoverer: discoverer}); err == nil || !strings.Contains(err.Error(), "live supervisor owner") {
		t.Fatalf("second owner error = %v", err)
	}
	if err := syscall.Kill(job.PID, 0); err != nil {
		t.Fatalf("second owner signaled first owner's process: %v", err)
	}
	if err := first.Cancel(job.ID); err != nil {
		t.Fatal(err)
	}
	waitTerminal(t, first, job.ID)
	if err := first.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestStateDirectoryReusesStaleUnlockedLockFile(t *testing.T) {
	state := t.TempDir()
	if err := os.WriteFile(filepath.Join(state, "supervisor.lock"), []byte("pid=999999\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	supervisor, err := NewSupervisor(Options{StateDir: state, Discoverer: Discoverer{Runner: fakeCommandRunner{}}})
	if err != nil {
		t.Fatalf("stale unlocked lock file blocked recovery: %v", err)
	}
	if err := supervisor.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestFragmentedMalformedStreamsRemainBoundedAndSequenced(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 3, 4)
	now := time.Now().UTC()
	job := &Job{APIVersion: APIVersion, ID: "stream-job", Status: StatusRunning, StartedAt: now, UpdatedAt: now}
	supervisor.jobs[job.ID] = job
	if err := supervisor.store.saveJob(*job); err != nil {
		t.Fatal(err)
	}
	data := []byte("{\"type\":\"system\",\"session_id\":\"fragmented\"}\nnot-json password=hunter2\n{\"type\":\"assistant\",\"value\":1}\n{\"type\":\"result\",\"result\":\"ok\"}\n")
	supervisor.readStream(job.ID, "stdout", &oneByteReader{data: data})
	events, err := supervisor.Events(job.ID, 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(events) != 3 || events[0].Sequence != 2 || events[2].Sequence != 4 {
		t.Fatalf("bounded events = %+v", events)
	}
	encoded, _ := json.Marshal(events)
	if strings.Contains(string(encoded), "hunter2") || !strings.Contains(string(encoded), "[REDACTED]") {
		t.Fatalf("events not redacted: %s", encoded)
	}
	replay, err := supervisor.Events(job.ID, 2)
	if err != nil || len(replay) != 2 {
		t.Fatalf("replay = %+v, err = %v", replay, err)
	}
}

func TestEventPayloadAndAggregateStorageAreByteBounded(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 500, 4)
	now := time.Now().UTC()
	job := &Job{APIVersion: APIVersion, ID: "byte-bounded-events", Status: StatusRunning, StartedAt: now, UpdatedAt: now}
	supervisor.jobs[job.ID] = job
	if err := supervisor.persistJob(*job); err != nil {
		t.Fatal(err)
	}
	supervisor.mu.Lock()
	supervisor.appendEventLocked(job.ID, "oversized", map[string]any{"blob": strings.Repeat("x", maxEventPayloadBytes+1)})
	for index := range 30 {
		supervisor.appendEventLocked(job.ID, "volume", map[string]any{"index": index, "blob": strings.Repeat("y", 100<<10)})
	}
	supervisor.mu.Unlock()
	events, err := supervisor.Events(job.ID, 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(events) >= 31 || events[len(events)-1].Sequence != 31 {
		t.Fatalf("aggregate bound did not retain only newest replay window: count=%d last=%d", len(events), events[len(events)-1].Sequence)
	}
	path := filepath.Join(supervisor.store.root, "events", job.ID+".jsonl")
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Size() > maxStoredEventBytes {
		t.Fatalf("event storage size=%d, max=%d", info.Size(), maxStoredEventBytes)
	}
	if bounded := boundEventPayload(map[string]any{"blob": strings.Repeat("z", maxEventPayloadBytes+1)}); bounded["truncated"] != true || bounded["sha256"] == "" {
		t.Fatalf("oversized payload not reduced to bounded digest: %+v", bounded)
	}
}

func TestProviderSessionIdentityIsAuthoritativeAndImmutable(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	now := time.Now().UTC()
	job := &Job{APIVersion: APIVersion, ID: "identity-job", Route: Route{TargetHarness: HarnessClaude}, Status: StatusRunning, StartedAt: now, UpdatedAt: now}
	supervisor.jobs[job.ID] = job
	if err := supervisor.store.saveJob(*job); err != nil {
		t.Fatal(err)
	}
	supervisor.recordProviderLine(job.ID, "stdout", []byte(`{"type":"assistant","session_id":"evil-top","nested":{"session_id":"evil-nested"}}`))
	if got, _ := supervisor.Status(job.ID); got.SessionID != "" {
		t.Fatalf("untrusted event set session %q", got.SessionID)
	}
	supervisor.recordProviderLine(job.ID, "stdout", []byte(`{"type":"system","subtype":"init","session_id":"session-good"}`))
	if got, _ := supervisor.Status(job.ID); got.SessionID != "session-good" {
		t.Fatalf("authoritative session=%q", got.SessionID)
	}
	supervisor.recordProviderLine(job.ID, "stdout", []byte(`{"type":"system","subtype":"init","session_id":"session-changed"}`))
	got, _ := supervisor.Status(job.ID)
	if got.SessionID != "session-good" || !strings.Contains(got.Failure, "immutable") {
		t.Fatalf("changed session job=%+v", got)
	}
	events, _ := supervisor.Events(job.ID, 0)
	if events[len(events)-1].Kind != "provider.protocol_error" {
		t.Fatalf("last event=%+v", events[len(events)-1])
	}
}

func TestAGYTerminalErrorIsNotReportedAsSuccess(t *testing.T) {
	session, result, failure, terminal := providerEventFields(HarnessAGY, map[string]any{"event": "result", "result": map[string]any{"conversation_id": "nested-untrusted", "status": "ERROR", "response": "", "error": "model failed"}})
	if session != "" || result != "" || failure != "model failed" || !terminal {
		t.Fatalf("fields=%q %q %q %v", session, result, failure, terminal)
	}
}

type oneByteReader struct{ data []byte }

func (r *oneByteReader) Read(buffer []byte) (int, error) {
	if len(r.data) == 0 {
		return 0, io.EOF
	}
	buffer[0], r.data = r.data[0], r.data[1:]
	return 1, nil
}

type gatedReader struct {
	gate <-chan struct{}
	data []byte
	done bool
}

func (r *gatedReader) Read(buffer []byte) (int, error) {
	if r.done {
		return 0, io.EOF
	}
	<-r.gate
	r.done = true
	return copy(buffer, r.data), nil
}

func newTestSupervisor(t *testing.T, roots DefinitionRoots, maxEvents, maxConcurrent int) *Supervisor {
	return newTestSupervisorWithLegacy(t, roots, maxEvents, maxConcurrent, true)
}

func newTestSupervisorWithLegacy(t *testing.T, roots DefinitionRoots, maxEvents, maxConcurrent int, allowLegacy bool) *Supervisor {
	t.Helper()
	discoverer := Discoverer{Roots: roots, Runner: fakeCommandRunner{outputs: map[string]string{
		"claude --version": "2.1.test",
		"claude --help":    "--agent --agents --setting-sources --model --effort <level> (low, medium, high) --input-format stream-json --output-format --resume",
	}}}
	_, _, roles := discoverer.installedRoleMetadata(HarnessClaude, nil)
	discoverer.static = map[Harness]Capability{HarnessClaude: {
		Harness: HarnessClaude, Available: true, ModelEfforts: []ModelEffort{{Model: "opus", Effort: "high", Reference: "exact"}}, Roles: roles,
	}}
	supervisor, err := NewSupervisor(Options{StateDir: t.TempDir(), MaxEvents: maxEvents, MaxConcurrent: maxConcurrent, Discoverer: discoverer, AllowLegacyAdmission: allowLegacy})
	if err != nil {
		t.Fatal(err)
	}
	return supervisor
}

func TestSupervisorDefaultConcurrencySupportsFleetOrchestrator(t *testing.T) {
	supervisor, err := NewSupervisor(Options{StateDir: t.TempDir(), Discoverer: Discoverer{Runner: fakeCommandRunner{}}})
	if err != nil {
		t.Fatal(err)
	}
	defer supervisor.Close()
	if DefaultMaxConcurrent != 25 {
		t.Fatalf("DefaultMaxConcurrent = %d, want 25", DefaultMaxConcurrent)
	}
	if supervisor.maxConcurrent != DefaultMaxConcurrent {
		t.Fatalf("default maxConcurrent = %d, want %d", supervisor.maxConcurrent, DefaultMaxConcurrent)
	}
}

func testStartRequest(repo, roleID string, mode CapabilityMode, ownership []string, brief string) StartRequest {
	return StartRequest{Route: Route{SourceHarness: HarnessCodex, TargetHarness: HarnessClaude, Provider: "anthropic", Family: "claude", ExactModel: "opus", Effort: "high", CanonicalRoleID: roleID, ParentGoalID: "goal-test", CapabilityMode: mode, RepositoryRoot: repo, FileOwnership: ownership, Evidence: EvidenceContract{RequiredChecks: []string{"go test ./runplane"}}}, Brief: brief}
}

func installFakeClaude(t *testing.T, body string) {
	t.Helper()
	bin := t.TempDir()
	path := filepath.Join(bin, "claude")
	script := "#!/bin/sh\nset -eu\n" + body + "\n"
	if err := os.WriteFile(path, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
}

func waitTerminal(t *testing.T, supervisor *Supervisor, id string) Job {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		job, err := supervisor.Status(id)
		if err != nil {
			t.Fatal(err)
		}
		if terminal(job.Status) {
			return job
		}
		time.Sleep(10 * time.Millisecond)
	}
	job, _ := supervisor.Status(id)
	t.Fatalf("job did not terminate: %+v", job)
	return Job{}
}

var _ = context.Canceled
