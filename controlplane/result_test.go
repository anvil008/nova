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
	diffCommand := CommandEvidence{
		CommandID: "command-diff", ArgvDigest: testDigest("diff-argv"), ExitCode: 0,
		StartedAt: "2026-08-23T20:00:02Z", FinishedAt: "2026-08-23T20:00:03Z",
		StdoutDigest: testDigest("diff-stdout"), StderrDigest: testDigest("diff-stderr"),
	}
	result := WorkflowResult{
		APIVersion: WorkflowResultAPIVersion, ResultID: "result-1", GoalID: "goal-1", AssignmentID: "assignment-1",
		GenerationID: "generation-1", DispatchID: "dispatch-1", ParentDispatchID: "dispatch-root", Cycle: 1, Pass: 1,
		RoleID: "workflow-executor", Lane: "execution", RouteDigest: testDigest("route"), AuthorityDigest: testDigest("authority"),
		SelectionDigest: testDigest("selection"), RoleDigest: testDigest("role"), CatalogDigest: testDigest("catalog"),
		RepositoryBefore: repoBefore, RepositoryAfter: repoAfter, CapabilityDigest: testDigest("capability"),
		SpecialistChoices: []SpecialistChoice{}, Files: []string{"controlplane/result.go"}, Symbols: []SymbolClaim{},
		Mutations: []MutationEvidence{{Path: "controlplane/result.go", BeforeDigest: testDigest("before"), AfterDigest: testDigest("after")}},
		Commands:  []CommandEvidence{command, diffCommand},
		DiffReview: &DiffReview{
			CommandID: diffCommand.CommandID, DiffDigest: testDigest("diff"), ReviewedAt: "2026-08-23T20:00:04Z",
			Findings: []string{"ownership and error paths reviewed against the brief"},
		},
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

func TestExecutionResultRequiresADiffReview(t *testing.T) {
	result, expected := validWorkflowResult(t)
	if err := ValidateWorkflowResult(result, expected); err != nil {
		t.Fatal(err)
	}
	result.DiffReview = nil
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(result, expected); err == nil {
		t.Fatal("successful execution result without a diff review accepted")
	}
}

func TestDiffReviewMustCiteAnExecutedCommand(t *testing.T) {
	result, expected := validWorkflowResult(t)
	result.DiffReview.CommandID = "command-absent"
	if err := SealWorkflowResult(&result); err == nil {
		t.Fatal("diff review referencing an unknown command accepted")
	}
	_ = expected
}

func TestDiffReviewContinuityRejectsADifferentChange(t *testing.T) {
	execution, _ := validWorkflowResult(t)
	assurance, _ := validWorkflowResult(t)
	assurance.RoleID, assurance.Lane = "workflow-code-review", "assurance"
	if err := SealWorkflowResult(&assurance); err != nil {
		t.Fatal(err)
	}
	if err := RequireDiffReviewContinuity(execution, assurance); err != nil {
		t.Fatal(err)
	}
	assurance.DiffReview.DiffDigest = testDigest("some-other-change")
	if err := SealWorkflowResult(&assurance); err != nil {
		t.Fatal(err)
	}
	if err := RequireDiffReviewContinuity(execution, assurance); err == nil {
		t.Fatal("assurance pass over a different diff accepted")
	}
	assurance.DiffReview = nil
	if err := SealWorkflowResult(&assurance); err != nil {
		t.Fatal(err)
	}
	if err := RequireDiffReviewContinuity(execution, assurance); err == nil {
		t.Fatal("assurance pass without a diff review accepted")
	}
}

func TestAssuranceAndEvaluationWithoutCommandsCannotPass(t *testing.T) {
	for _, lane := range []string{"assurance", "evaluation"} {
		result, expected := validWorkflowResult(t)
		result.RoleID, result.Lane = "workflow-code-review", lane
		result.Commands, result.Checks, result.Artifacts, result.Mutations = []CommandEvidence{}, []CheckEvidence{}, []ArtifactEvidence{}, []MutationEvidence{}
		result.DiffReview = nil
		expected.RoleID, expected.Lane = result.RoleID, lane
		expected.RequiredChecks, expected.RequiredArtifacts = []string{}, []string{}
		if err := SealWorkflowResult(&result); err != nil {
			t.Fatal(err)
		}
		if err := ValidateWorkflowResult(result, expected); err == nil {
			t.Fatalf("%s result with no executed command was allowed to pass", lane)
		}
		result.Disposition, result.Uncertainty = DispositionUncertain, []string{"no verifier was available"}
		if err := SealWorkflowResult(&result); err != nil {
			t.Fatal(err)
		}
		if err := ValidateWorkflowResult(result, expected); err == nil {
			t.Fatalf("%s result with no executed command was allowed to warn", lane)
		}
		result.Disposition = DispositionUnverified
		if err := SealWorkflowResult(&result); err != nil {
			t.Fatal(err)
		}
		if err := ValidateWorkflowResult(result, expected); err != nil {
			t.Fatalf("%s: %v", lane, err)
		}
	}
}

func TestDiscoveryResultsCarryPointersNotExcerpts(t *testing.T) {
	result, expected := validWorkflowResult(t)
	result.RoleID, result.Lane = "workflow-research", "discovery"
	result.Mutations, result.DiffReview = []MutationEvidence{}, nil
	expected.RoleID, expected.Lane = result.RoleID, result.Lane
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(result, expected); err == nil {
		t.Fatal("discovery result listing files without pointers accepted")
	}
	result.Pointers = []Pointer{{Path: "controlplane/result.go", StartLine: 77, EndLine: 122, Symbol: "WorkflowResult", Why: "the contract the change extends"}}
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(result, expected); err != nil {
		t.Fatal(err)
	}
	result.Pointers[0].EndLine = 10
	if err := SealWorkflowResult(&result); err == nil {
		t.Fatal("pointer with an inverted line range accepted")
	}
	result.Pointers[0].EndLine, result.Pointers[0].Why = 122, ""
	if err := SealWorkflowResult(&result); err == nil {
		t.Fatal("pointer without a reason accepted")
	}
}
