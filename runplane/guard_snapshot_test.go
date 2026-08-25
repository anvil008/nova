package runplane

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
	"github.com/anvil008/swarm-coder/guard"
)

// writeGuardState lays down the records anvil-guard would have produced for a
// sealed repository. The supervisor reads this directory itself; nothing about
// it travels over the network.
func writeGuardState(t *testing.T, repository, greenCommandID string) {
	t.Helper()
	directory, err := guard.StateDirectory(repository)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(directory, 0o700); err != nil {
		t.Fatal(err)
	}
	seal := guard.Seal{
		SealedAt: "2026-08-23T19:59:30Z",
		Base:     guard.Base{HeadCommit: "abc", TreeDigest: "sha256:tree"},
		Tests:    []guard.TestDigest{{Path: "runplane/result_test.go", Digest: "sha256:red-test"}},
		Red: controlplane.CommandEvidence{
			CommandID: "cmd-red", ArgvDigest: "sha256:red-argv", ExitCode: 1,
			StartedAt: "2026-08-23T19:59:00Z", FinishedAt: "2026-08-23T19:59:10Z",
			StdoutDigest: "sha256:red-out", StderrDigest: "sha256:red-err",
		},
		Amendments: []guard.Amendment{},
	}
	// The digests mirror backingWorkflowResult: an honest reporter's own
	// CommandEvidence repeats the run the guard recorded, and the supervisor now
	// compares the two rather than taking the reporter's word for the argv.
	green := controlplane.CommandEvidence{
		CommandID: greenCommandID, ArgvDigest: "sha256:argv", ExitCode: 0,
		StartedAt: "2026-08-23T20:00:00Z", FinishedAt: "2026-08-23T20:00:01Z",
		StdoutDigest: "sha256:out", StderrDigest: "sha256:err",
	}
	for name, value := range map[string]any{"seal.json": seal, "green.json": green} {
		encoded, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(directory, name), encoded, 0o600); err != nil {
			t.Fatal(err)
		}
	}
}

// The supervisor must resolve a foreign child's cited commandIds against the
// guard state on disk, not against the child's own prose.
func TestSupervisorResolvesHandoffTestsAgainstGuardState(t *testing.T) {
	stateBase := t.TempDir()
	t.Setenv(guard.StateEnv, stateBase)
	repository, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}

	supervisor, job, handoff := agentHandoffFixture(t)
	supervisor.mu.Lock()
	job.Route.RepositoryRoot = repository
	supervisor.mu.Unlock()

	// The guard ran a different green command than the one the handoff cites.
	writeGuardState(t, repository, "cmd-green")
	raw, err := json.Marshal(handoff)
	if err != nil {
		t.Fatal(err)
	}
	if recognized := supervisor.recordAgentHandoff(job.ID, string(raw)); !recognized {
		t.Fatal("handoff was not recognized")
	}
	got, err := supervisor.Status(job.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Handoff != nil || got.HandoffFailure == "" {
		t.Fatalf("a commandId with no guard record was accepted: %+v", got)
	}

	// The same handoff, once the guard actually recorded that run.
	writeGuardState(t, repository, "command-unit")
	if recognized := supervisor.recordAgentHandoff(job.ID, string(raw)); !recognized {
		t.Fatal("handoff was not recognized")
	}
	got, err = supervisor.Status(job.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Handoff == nil || got.HandoffFailure != "" {
		t.Fatalf("a guard-produced commandId was rejected: %+v", got)
	}
}
