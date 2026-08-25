package codingfleet

import "testing"

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
		CanonicalRole: "technical-go", Provider: "google", Model: "gemini-3.7-flash", Effort: "max",
		Mode: CapabilityWorkspaceWrite, OwnedFiles: []string{"codingfleet/handoff.go"},
		Limits:       AgentHandoffLimits{MaxMessages: 100, MaxDurationSeconds: 600, MaxChildren: 2},
		ChangedFiles: []string{"codingfleet/handoff.go"},
		Tests:        []AgentHandoffTest{{Name: "go test ./codingfleet", Passed: true}},
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
