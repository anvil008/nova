package codingfleet

import (
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
)

func TestSelectModelDispatchUsesNativeWithinProvider(t *testing.T) {
	tests := []struct {
		current, requested string
		want               ModelDispatchPolicy
	}{
		{"google", "google", SameProviderNativeSubagentExplicitOverride},
		{"anthropic", "anthropic", SameProviderNativeSubagentExplicitOverride},
		{"openai", "google", CrossProviderSupervisorExactRoleHeadless},
	}
	for _, test := range tests {
		got, err := SelectModelDispatch(test.current, test.requested)
		if err != nil || got != test.want {
			t.Fatalf("SelectModelDispatch(%q, %q) = %q, %v; want %q", test.current, test.requested, got, err, test.want)
		}
	}
}

func TestAgentHandoffIsSmallAndTruthful(t *testing.T) {
	handoff := AgentHandoff{
		APIVersion: AgentHandoffAPIVersion, RunID: "run-1", ParentRunID: "goal-1",
		CanonicalRole: "toolchain-go", Provider: "google", Model: "gemini-3.7-flash", Effort: "max",
		Mode: CapabilityWorkspaceWrite, OwnedFiles: []string{"codingfleet/handoff.go"},
		Limits:       AgentHandoffLimits{MaxMessages: 100, MaxDurationSeconds: 600, MaxChildren: 2},
		ChangedFiles: []string{"codingfleet/handoff.go"},
		Tests:        []AgentHandoffTest{{Name: "go test ./codingfleet", Passed: true, CommandID: "command-unit"}},
		Result:       "implemented native-first routing", Disposition: HandoffSucceeded,
	}
	if err := ValidateAgentHandoff(handoff); err != nil {
		t.Fatal(err)
	}
	handoff.Tests[0].Passed = false
	if err := ValidateAgentHandoff(handoff); err == nil {
		t.Fatal("successful handoff with a failed test was accepted")
	}
	handoff.Tests[0].Passed = true
	handoff.OwnedFiles = []string{"../escape"}
	if err := ValidateAgentHandoff(handoff); err == nil {
		t.Fatal("escaping owned file was accepted")
	}
}

func TestPassedHandoffTestMustCiteACommand(t *testing.T) {
	handoff := AgentHandoff{
		APIVersion: AgentHandoffAPIVersion, RunID: "run-1", CanonicalRole: "workflow-executor",
		Provider: "anthropic", Model: "opus", Effort: "high", Mode: CapabilityWorkspaceWrite,
		OwnedFiles:   []string{"codingfleet/handoff.go"},
		Limits:       AgentHandoffLimits{MaxMessages: 100, MaxDurationSeconds: 600, MaxChildren: 2},
		ChangedFiles: []string{"codingfleet/handoff.go"},
		Tests:        []AgentHandoffTest{{Name: "go test ./codingfleet", Passed: true}},
		Result:       "implemented the seal contract", Disposition: HandoffSucceeded,
	}
	if err := ValidateAgentHandoff(handoff); err == nil {
		t.Fatal("passed test without a commandId was accepted")
	}
	handoff.Tests[0].CommandID = "command-unit"
	if err := ValidateAgentHandoff(handoff); err != nil {
		t.Fatal(err)
	}
	handoff.Tests[0].CommandID = "not a command id"
	if err := ValidateAgentHandoff(handoff); err == nil {
		t.Fatal("malformed commandId was accepted")
	}
}

func TestReconcileHandoffTestsRequiresCurrentPassingEvidence(t *testing.T) {
	handoff := AgentHandoff{Tests: []AgentHandoffTest{{Name: "unit", Passed: true, CommandID: "command-unit"}}}
	result := controlplane.WorkflowResult{
		Commands: []controlplane.CommandEvidence{{CommandID: "command-unit", ExitCode: 0}},
		Checks:   []controlplane.CheckEvidence{{CheckID: "unit", CommandID: "command-unit", Passed: true, Current: true}},
	}
	if err := ReconcileHandoffTests(handoff, result, nil); err != nil {
		t.Fatal(err)
	}
	result.Commands[0].ExitCode = 1
	if err := ReconcileHandoffTests(handoff, result, nil); err == nil {
		t.Fatal("passed test backed by a failing command was accepted")
	}
	result.Commands[0].ExitCode = 0
	result.Checks[0].Current = false
	if err := ReconcileHandoffTests(handoff, result, nil); err == nil {
		t.Fatal("passed test backed by stale evidence was accepted")
	}
	result.Checks = []controlplane.CheckEvidence{}
	if err := ReconcileHandoffTests(handoff, result, nil); err == nil {
		t.Fatal("passed test with no check evidence was accepted")
	}
	handoff.Tests[0].CommandID = "command-absent"
	if err := ReconcileHandoffTests(handoff, result, nil); err == nil {
		t.Fatal("passed test citing an unknown command was accepted")
	}
}
