package runplane

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
)

func TestSupervisorAcceptsSmallAgentHandoffAgainstRoute(t *testing.T) {
	supervisor, job, handoff := agentHandoffFixture(t)
	raw, err := json.Marshal(handoff)
	if err != nil {
		t.Fatal(err)
	}
	if recognized := supervisor.recordAgentHandoff(job.ID, string(raw)); !recognized {
		t.Fatal("small handoff was not recognized")
	}
	got, err := supervisor.Status(job.ID)
	if err != nil || got.Handoff == nil || got.Handoff.Disposition != codingfleet.HandoffSucceeded || got.HandoffFailure != "" {
		t.Fatalf("stored handoff = %+v, err=%v", got, err)
	}
}

func TestSupervisorInvalidLaterHandoffClearsPriorValidState(t *testing.T) {
	supervisor, job, handoff := agentHandoffFixture(t)
	raw, err := json.Marshal(handoff)
	if err != nil {
		t.Fatal(err)
	}
	if recognized := supervisor.recordAgentHandoff(job.ID, string(raw)); !recognized {
		t.Fatal("initial small handoff was not recognized")
	}

	handoff.ChangedFiles = []string{"outside/file.go"}
	raw, err = json.Marshal(handoff)
	if err != nil {
		t.Fatal(err)
	}
	if recognized := supervisor.recordAgentHandoff(job.ID, string(raw)); !recognized {
		t.Fatal("invalid later handoff was not recognized")
	}
	got, err := supervisor.Status(job.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Handoff != nil || got.HandoffFailure == "" {
		t.Fatalf("invalid later handoff retained prior valid state: %+v", got)
	}
}

func agentHandoffFixture(t *testing.T) (*Supervisor, *Job, codingfleet.AgentHandoff) {
	t.Helper()
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	route := Route{
		SourceHarness: HarnessCodex, TargetHarness: HarnessClaude,
		Provider: "anthropic", Family: "claude", ExactModel: "opus", Effort: "high",
		CanonicalRoleID: "workflow-executor", ParentGoalID: "goal-1",
		DispatchID: "0123456789abcdef0123456789abcdef", ParentDispatchID: "parent-1",
		CapabilityMode: ModeWorkspaceWrite, FileOwnership: []string{"runplane"},
		Limits:   codingfleet.AgentHandoffLimits{MaxMessages: 100, MaxDurationSeconds: 600, MaxChildren: 2},
		Evidence: EvidenceContract{RequiredChecks: []string{"go test ./runplane"}},
	}
	job := &Job{APIVersion: APIVersion, ID: route.DispatchID, Route: route, Status: StatusRunning, StartedAt: time.Now().UTC(), UpdatedAt: time.Now().UTC()}
	supervisor.mu.Lock()
	supervisor.jobs[job.ID] = job
	if err := supervisor.persistJob(*job); err != nil {
		supervisor.mu.Unlock()
		t.Fatal(err)
	}
	supervisor.mu.Unlock()

	handoff := codingfleet.AgentHandoff{
		APIVersion: codingfleet.AgentHandoffAPIVersion, RunID: route.DispatchID, ParentRunID: route.ParentDispatchID,
		CanonicalRole: route.CanonicalRoleID, Provider: route.Provider, Model: route.ExactModel, Effort: route.Effort,
		Mode: codingfleet.CapabilityWorkspaceWrite, OwnedFiles: []string{"runplane"}, Limits: route.Limits,
		ChangedFiles: []string{"runplane/result.go"}, Tests: []codingfleet.AgentHandoffTest{{Name: "go test ./runplane", Passed: true}},
		Result: "implemented and verified", Disposition: codingfleet.HandoffSucceeded,
	}
	return supervisor, job, handoff
}
