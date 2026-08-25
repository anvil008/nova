package controlplane

import "testing"

func validWorkflowResult(t *testing.T) (WorkflowResult, ResultExpectation) {
	t.Helper()
	repoBefore := testDigest("repo-before")
	repoAfter := testDigest("repo-after")
	command := CommandEvidence{
		CommandID: "command-unit", ArgvDigest: testDigest("argv"), ExitCode: 0,
		StartedAt: "2026-08-23T20:00:00Z", FinishedAt: "2026-08-23T20:00:01Z",
		StdoutDigest: testDigest("stdout"), StderrDigest: testDigest("stderr"),
	}
	result := WorkflowResult{
		APIVersion: WorkflowResultAPIVersion, ResultID: "result-1", GoalID: "goal-1", AssignmentID: "assignment-1",
		GenerationID: "generation-1", DispatchID: "dispatch-1", ParentDispatchID: "dispatch-root", Cycle: 1, Pass: 1,
		RoleID: "workflow-executor", Lane: "execution", RouteDigest: testDigest("route"), AuthorityDigest: testDigest("authority"),
		SelectionDigest: testDigest("selection"), RoleDigest: testDigest("role"), CatalogDigest: testDigest("catalog"),
		RepositoryBefore: repoBefore, RepositoryAfter: repoAfter, CapabilityDigest: testDigest("capability"),
		SpecialistChoices: []SpecialistChoice{}, Files: []string{"controlplane/result.go"}, Symbols: []SymbolClaim{},
		Mutations: []MutationEvidence{{Path: "controlplane/result.go", BeforeDigest: testDigest("before"), AfterDigest: testDigest("after")}},
		Commands:  []CommandEvidence{command},
		Checks:    []CheckEvidence{{CheckID: "unit", CommandID: "command-unit", Passed: true, Current: true, EvidenceDigest: testDigest("unit-proof")}},
		Artifacts: []ArtifactEvidence{{ArtifactID: "patch", Path: "controlplane/result.go", Digest: testDigest("artifact"), Current: true}},
		Findings:  []FindingEvidence{}, Uncertainty: []string{}, Decisions: []string{"implemented bounded result validation"},
		Errors: []string{}, Assumptions: []string{}, MissingEvidence: []string{}, ChildResultDigests: []string{},
		BudgetReserved: BudgetAmount{Delegates: 1, Writers: 1, Tokens: 1000, DurationSeconds: 60},
		BudgetConsumed: BudgetAmount{Delegates: 1, Writers: 1, Tokens: 800, DurationSeconds: 50},
		BudgetReleased: BudgetAmount{Tokens: 200, DurationSeconds: 10}, SuggestedNextAction: "independent-review",
		StartedAt: "2026-08-23T20:00:00Z", FinishedAt: "2026-08-23T20:01:00Z", Disposition: DispositionSucceeded,
	}
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	expected := ResultExpectation{
		GoalID: result.GoalID, AssignmentID: result.AssignmentID, GenerationID: result.GenerationID,
		DispatchID: result.DispatchID, ParentDispatchID: result.ParentDispatchID, RoleID: result.RoleID, Lane: result.Lane,
		RouteDigest: result.RouteDigest, AuthorityDigest: result.AuthorityDigest, SelectionDigest: result.SelectionDigest,
		RoleDigest: result.RoleDigest, CatalogDigest: result.CatalogDigest, RepositoryBefore: repoBefore,
		CurrentRepositoryDigest: repoAfter, CapabilityDigest: result.CapabilityDigest,
		RequiredChecks: []string{"unit"}, RequiredArtifacts: []string{"patch"},
	}
	return result, expected
}

func TestWorkflowResultRequiresCurrentProof(t *testing.T) {
	result, expected := validWorkflowResult(t)
	if err := ValidateWorkflowResult(result, expected); err != nil {
		t.Fatal(err)
	}
	result.Checks[0].Current = false
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(result, expected); err == nil {
		t.Fatal("stale required check accepted")
	}
}

func TestWorkflowResultExitZeroAloneIsInsufficient(t *testing.T) {
	result, expected := validWorkflowResult(t)
	result.Checks = []CheckEvidence{}
	result.Artifacts = []ArtifactEvidence{}
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(result, expected); err == nil {
		t.Fatal("exit zero without proof accepted")
	}
}

func TestWorkflowResultRejectsFailedCommandAndChangedState(t *testing.T) {
	result, expected := validWorkflowResult(t)
	result.Commands[0].ExitCode = 1
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(result, expected); err == nil {
		t.Fatal("successful result with failed command accepted")
	}
	result, expected = validWorkflowResult(t)
	expected.CurrentRepositoryDigest = testDigest("newer-repo")
	if err := ValidateWorkflowResult(result, expected); err == nil {
		t.Fatal("result for changed repository accepted")
	}
}

func TestWorkflowResultMissingSpecialistIsTruthfulNonSuccess(t *testing.T) {
	result, expected := validWorkflowResult(t)
	result.Disposition = DispositionMissingSpecialist
	result.MissingSpecialist = &MissingSpecialist{
		Kind: "technical", RequiredCapability: "language-x", EvidenceDigests: []string{testDigest("gap")}, FactoryRequested: true,
	}
	result.Errors = []string{"required specialist is absent"}
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(result, expected); err != nil {
		t.Fatal(err)
	}
}
