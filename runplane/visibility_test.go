package runplane

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/herdrbridge"
)

type fakeHerdrVisibility struct {
	mu          sync.Mutex
	probeErr    error
	metadataErr error
	layouts     []herdrbridge.LayoutSpec
	updates     []herdrbridge.MetadataUpdate
	clears      []uint64
	workerErrs  chan error
}

func (f *fakeHerdrVisibility) Probe(context.Context) error { return f.probeErr }

func (f *fakeHerdrVisibility) ApplyLayout(_ context.Context, spec herdrbridge.LayoutSpec) (herdrbridge.Locator, error) {
	f.mu.Lock()
	f.layouts = append(f.layouts, spec)
	f.mu.Unlock()
	state := spec.Env["SWARM_RUNPLANE_STATE"]
	jobID := spec.Command[len(spec.Command)-1]
	go func() {
		if err := RunWorker(context.Background(), state, jobID); err != nil && f.workerErrs != nil {
			f.workerErrs <- err
		}
	}()
	return herdrbridge.Locator{WorkspaceID: "workspace", TabID: spec.TabLabel, PaneID: "pane-" + jobID, TerminalID: "terminal-" + jobID, JobLabel: spec.TabLabel}, nil
}

func (f *fakeHerdrVisibility) Snapshot(context.Context) (herdrbridge.Snapshot, error) {
	return herdrbridge.Snapshot{}, nil
}

func (f *fakeHerdrVisibility) ReportMetadata(_ context.Context, _ herdrbridge.Locator, update herdrbridge.MetadataUpdate) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.updates = append(f.updates, update)
	return f.metadataErr
}

func (f *fakeHerdrVisibility) ClearMetadata(_ context.Context, _ herdrbridge.Locator, sequence uint64) error {
	f.mu.Lock()
	f.clears = append(f.clears, sequence)
	f.mu.Unlock()
	return f.metadataErr
}

func newVisibleTestSupervisor(t *testing.T, fake *fakeHerdrVisibility, mode VisibilityMode) *Supervisor {
	t.Helper()
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "opus-exact", "high")
	discoverer := Discoverer{Roots: roots, Runner: fakeCommandRunner{outputs: map[string]string{
		"claude --version": "2.1.test",
		"claude --help":    "--agent --agents --setting-sources --model --effort <level> (low, medium, high) --input-format stream-json --output-format --resume",
	}}}
	_, _, roles := discoverer.installedRoleMetadata(HarnessClaude, nil)
	discoverer.static = map[Harness]Capability{HarnessClaude: {
		Harness: HarnessClaude, Available: true, ModelEfforts: []ModelEffort{{Provider: "anthropic", Family: "claude", Model: "opus", Effort: "high", Reference: "exact"}}, Roles: roles,
	}}
	root := t.TempDir()
	supervisor, err := NewSupervisor(Options{
		StateDir: root, Discoverer: discoverer, AllowLegacyAdmission: true,
		Visibility:        VisibilityConfig{Mode: mode, HerdrEnv: true, BinaryPath: filepath.Join(root, "herdr"), SocketPath: filepath.Join(root, "herdr.sock"), SessionID: "session", WorkspaceID: "workspace", WorkerBinary: filepath.Join(root, "swarm-runplane"), Timeout: time.Second},
		VisibilityFactory: func(herdrbridge.Config) (HerdrVisibilityClient, error) { return fake, nil },
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = supervisor.Close() })
	return supervisor
}

func visibleRequest(repo, task, attempt, brief string) StartRequest {
	request := testStartRequest(repo, "workflow-executor", ModeWorkspaceWrite, []string{"runplane"}, brief)
	request.Presentation = &codingfleet.AgentPresentation{TaskRef: task, Task: "Expose agent work", Phase: "execution", Summary: "running focused tests", Model: "opus", Attempt: attempt}
	return request
}

func TestVisibilityRequiredCreatesStableWorkerPaneAndKeepsPromptOffDisplay(t *testing.T) {
	installFakeClaude(t, `IFS= read -r input; printf '%s\n' '{"type":"result","result":"done"}'`)
	fake := &fakeHerdrVisibility{workerErrs: make(chan error, 1)}
	supervisor := newVisibleTestSupervisor(t, fake, VisibilityRequired)
	request := visibleRequest(testRepository(t), "SWM-505", "attempt-1", "PROMPT-MUST-NOT-BE-DISPLAYED")
	job, err := supervisor.Start(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	job = waitTerminal(t, supervisor, job.ID)
	if job.Status != StatusSucceeded || job.Visibility == nil || job.Visibility.Sequence == 0 {
		t.Fatalf("visible job = %+v", job)
	}
	fake.mu.Lock()
	defer fake.mu.Unlock()
	if len(fake.layouts) != 1 || len(fake.layouts[0].Command) != 3 || fake.layouts[0].Command[1] != "worker" || fake.layouts[0].Command[2] != job.ID {
		t.Fatalf("worker argv = %#v", fake.layouts)
	}
	encoded := ""
	for _, update := range fake.updates {
		encoded += update.Presentation.Task + update.Presentation.Summary
	}
	if strings.Contains(encoded, request.Brief) || strings.Contains(strings.Join(fake.layouts[0].Command, " "), request.Brief) {
		t.Fatal("brief leaked into worker argv or display metadata")
	}
}

func TestVisibilityAutoFallsBackPreProviderAndRequiredRejects(t *testing.T) {
	installFakeClaude(t, `IFS= read -r input; printf '%s\n' '{"type":"result","result":"direct"}'`)
	repo := testRepository(t)
	for _, test := range []struct {
		mode      VisibilityMode
		wantError bool
	}{{VisibilityAuto, false}, {VisibilityRequired, true}} {
		fake := &fakeHerdrVisibility{probeErr: errors.New("not ready")}
		supervisor := newVisibleTestSupervisor(t, fake, test.mode)
		job, err := supervisor.Start(context.Background(), visibleRequest(repo, "SWM-506", string(test.mode), "fallback"))
		if test.wantError {
			if err == nil {
				t.Fatal("required visibility accepted unavailable Herdr")
			}
			continue
		}
		if err != nil {
			t.Fatal(err)
		}
		job = waitTerminal(t, supervisor, job.ID)
		if job.Status != StatusSucceeded || job.Visibility == nil || job.Visibility.LastError == "" {
			t.Fatalf("auto fallback job = %+v", job)
		}
	}
}

func TestVisibilityMetadataFailureDoesNotChangeTerminalAuthority(t *testing.T) {
	installFakeClaude(t, `IFS= read -r input; printf '%s\n' '{"type":"result","result":"done"}'`)
	fake := &fakeHerdrVisibility{metadataErr: errors.New("metadata unavailable")}
	supervisor := newVisibleTestSupervisor(t, fake, VisibilityRequired)
	job, err := supervisor.Start(context.Background(), visibleRequest(testRepository(t), "SWM-507", "attempt-1", "metadata isolation"))
	if err != nil {
		t.Fatal(err)
	}
	job = waitTerminal(t, supervisor, job.ID)
	if job.Status != StatusSucceeded || job.WorkflowDisposition != "uncertain" || job.Visibility.LastError == "" {
		t.Fatalf("metadata failure changed authority: %+v", job)
	}
}

func TestVisibilityWorkerSendAndCancelPreserveProviderBoundary(t *testing.T) {
	t.Run("send", func(t *testing.T) {
		installFakeClaude(t, `IFS= read -r first; IFS= read -r second; printf '%s\n' '{"type":"result","result":"sent"}'`)
		fake := &fakeHerdrVisibility{}
		supervisor := newVisibleTestSupervisor(t, fake, VisibilityRequired)
		job, err := supervisor.Start(context.Background(), visibleRequest(testRepository(t), "SWM-506", "send-1", "first"))
		if err != nil {
			t.Fatal(err)
		}
		if err := supervisor.Send(job.ID, "second"); err != nil {
			t.Fatal(err)
		}
		if terminalJob := waitTerminal(t, supervisor, job.ID); terminalJob.Status != StatusSucceeded {
			t.Fatalf("send terminal = %+v", terminalJob)
		}
	})
	t.Run("cancel", func(t *testing.T) {
		installFakeClaude(t, `IFS= read -r first; sleep 30`)
		fake := &fakeHerdrVisibility{}
		supervisor := newVisibleTestSupervisor(t, fake, VisibilityRequired)
		job, err := supervisor.Start(context.Background(), visibleRequest(testRepository(t), "SWM-506", "cancel-1", "cancel"))
		if err != nil {
			t.Fatal(err)
		}
		if err := supervisor.Cancel(job.ID); err != nil {
			t.Fatal(err)
		}
		if terminalJob := waitTerminal(t, supervisor, job.ID); terminalJob.Status != StatusCanceled {
			t.Fatalf("cancel terminal = %+v", terminalJob)
		}
	})
}

func TestVisibilityConcurrentJobsReceiveDistinctDurableLabels(t *testing.T) {
	installFakeClaude(t, `IFS= read -r input; sleep 0.1; printf '%s\n' '{"type":"result","result":"done"}'`)
	fake := &fakeHerdrVisibility{}
	supervisor := newVisibleTestSupervisor(t, fake, VisibilityRequired)
	repo := testRepository(t)
	first := visibleRequest(repo, "SWM-508", "one", "one")
	first.Route.FileOwnership = []string{"runplane"}
	second := visibleRequest(repo, "SWM-508", "two", "two")
	second.Route.FileOwnership = []string{"cmd"}
	job1, err := supervisor.Start(context.Background(), first)
	if err != nil {
		t.Fatal(err)
	}
	job2, err := supervisor.Start(context.Background(), second)
	if err != nil {
		t.Fatal(err)
	}
	_ = waitTerminal(t, supervisor, job1.ID)
	_ = waitTerminal(t, supervisor, job2.ID)
	fake.mu.Lock()
	defer fake.mu.Unlock()
	if len(fake.layouts) != 2 || fake.layouts[0].TabLabel == fake.layouts[1].TabLabel {
		t.Fatalf("layouts = %#v", fake.layouts)
	}
}
