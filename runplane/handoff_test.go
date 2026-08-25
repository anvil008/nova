package runplane

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
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
	// The authoritative record of the run the handoff cites. A required check is
	// satisfied by this evidence, never by the handoff's own boolean.
	job := &Job{
		APIVersion: APIVersion, ID: route.DispatchID, Route: route, Status: StatusRunning,
		WorkflowResult: backingWorkflowResult(),
		StartedAt:      time.Now().UTC(), UpdatedAt: time.Now().UTC(),
	}
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
		ChangedFiles: []string{"runplane/result.go"}, Tests: []codingfleet.AgentHandoffTest{{Name: "go test ./runplane", Passed: true, CommandID: "command-unit"}},
		Result: "implemented and verified", Disposition: codingfleet.HandoffSucceeded,
	}
	return supervisor, job, handoff
}

// backingWorkflowResult is the authoritative record a handoff test must cite.
func backingWorkflowResult() *controlplane.WorkflowResult {
	return &controlplane.WorkflowResult{
		APIVersion: controlplane.WorkflowResultAPIVersion, Lane: "execution",
		Commands: []controlplane.CommandEvidence{{
			CommandID: "command-unit", ArgvDigest: "sha256:argv", ExitCode: 0,
			StartedAt: "2026-08-23T20:00:00Z", FinishedAt: "2026-08-23T20:00:01Z",
			StdoutDigest: "sha256:out", StderrDigest: "sha256:err",
		}},
		Checks: []controlplane.CheckEvidence{{
			CheckID: "go test ./runplane", CommandID: "command-unit", Passed: true, Current: true,
			EvidenceDigest: "sha256:proof",
		}},
	}
}

func TestSupervisorRejectsARequiredCheckWithoutAuthoritativeEvidence(t *testing.T) {
	// A `passed: true` boolean with no workflow result behind it is exactly the
	// self-reported evidence the contract exists to reject.
	supervisor, job, handoff := agentHandoffFixture(t)
	supervisor.mu.Lock()
	job.WorkflowResult = nil
	supervisor.mu.Unlock()
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
		t.Fatalf("a self-reported required check was accepted: %+v", got)
	}
}

func TestSupervisorRejectsAHandoffTestCitingAnUnrecordedCommand(t *testing.T) {
	supervisor, job, handoff := agentHandoffFixture(t)
	handoff.Tests[0].CommandID = "command-fabricated"
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
	if got.Handoff != nil || !strings.Contains(got.HandoffFailure, "command-fabricated") {
		t.Fatalf("a fabricated commandId was accepted: %+v", got)
	}
}

func TestSupervisorRejectsAHandoffTestBackedByAFailedCommand(t *testing.T) {
	supervisor, job, handoff := agentHandoffFixture(t)
	supervisor.mu.Lock()
	job.WorkflowResult.Commands[0].ExitCode = 1
	supervisor.mu.Unlock()
	raw, err := json.Marshal(handoff)
	if err != nil {
		t.Fatal(err)
	}
	supervisor.recordAgentHandoff(job.ID, string(raw))
	got, err := supervisor.Status(job.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Handoff != nil || got.HandoffFailure == "" {
		t.Fatalf("a passing test claim backed by a failed command was accepted: %+v", got)
	}
}

func TestSupervisorRejectsAHandoffTheLaterWorkflowResultDoesNotBack(t *testing.T) {
	supervisor, job, handoff := agentHandoffFixture(t)
	raw, err := json.Marshal(handoff)
	if err != nil {
		t.Fatal(err)
	}
	if recognized := supervisor.recordAgentHandoff(job.ID, string(raw)); !recognized {
		t.Fatal("handoff was not recognized")
	}
	if got, _ := supervisor.Status(job.ID); got.Handoff == nil {
		t.Fatalf("backed handoff was rejected: %+v", got)
	}

	// The authoritative result arrives afterwards and does not record the run
	// the handoff cited.
	supervisor.mu.Lock()
	replacement := backingWorkflowResult()
	replacement.Commands[0].CommandID = "command-other"
	replacement.Checks[0].CommandID = "command-other"
	job.WorkflowResult = replacement
	err = supervisor.reconcileHandoffEvidenceLocked(job)
	supervisor.mu.Unlock()
	if err == nil {
		t.Fatal("a later workflow result that does not back the handoff was accepted")
	}
}

func TestSupervisorRequiresDiffReviewContinuityWithinAGoal(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	execution := &Job{
		APIVersion: APIVersion, ID: "execution-job",
		ControlPlane:   &ControlPlaneAdmission{Goal: controlplane.GoalRecord{GoalID: "goal-1"}},
		WorkflowResult: &controlplane.WorkflowResult{Lane: "execution", DiffReview: &controlplane.DiffReview{CommandID: "command-diff", DiffDigest: "sha256:the-change"}},
	}
	assurance := &Job{
		APIVersion: APIVersion, ID: "assurance-job",
		ControlPlane:   &ControlPlaneAdmission{Goal: controlplane.GoalRecord{GoalID: "goal-1"}},
		WorkflowResult: &controlplane.WorkflowResult{Lane: "assurance", DiffReview: &controlplane.DiffReview{CommandID: "command-diff", DiffDigest: "sha256:the-change"}},
	}
	supervisor.mu.Lock()
	defer supervisor.mu.Unlock()
	supervisor.jobs[execution.ID] = execution
	supervisor.jobs[assurance.ID] = assurance

	if err := supervisor.requireDiffReviewContinuityLocked(assurance); err != nil {
		t.Fatalf("matching diff review rejected: %v", err)
	}
	assurance.WorkflowResult.DiffReview.DiffDigest = "sha256:a-different-change"
	if err := supervisor.requireDiffReviewContinuityLocked(assurance); err == nil {
		t.Fatal("an assurance pass over a different change was accepted")
	}
	assurance.WorkflowResult.DiffReview = nil
	if err := supervisor.requireDiffReviewContinuityLocked(assurance); err == nil {
		t.Fatal("an assurance pass with no recorded diff review was accepted")
	}
}
