package controlplane

import "testing"

func validSelectionEnvelope(t *testing.T) SelectionEnvelope {
	t.Helper()
	envelope := SelectionEnvelope{
		APIVersion: SelectionAPIVersion, SelectionID: "selection-1", GoalID: "goal-1",
		GenerationID: "generation-1", DispatchID: "dispatch-1",
		ProposedWorkflowID: "workflow-executor", WorkflowOwnerID: "workflow-executor",
		ProposedLenses: []LensProposal{{RoleID: "toolchain-go", Kind: RoleKindTechnical, Reason: "Go files are owned"}},
		Refinements:    []SelectionRefinement{}, SelectedLeafIDs: []string{"toolchain-go"},
		Invocations: []InvocationEdge{
			{ParentRoleID: "workflow-coding-orchestrator", ParentKind: RoleKindOrchestrator, ChildRoleID: "workflow-executor", ChildKind: RoleKindWorkflow},
			{ParentRoleID: "workflow-executor", ParentKind: RoleKindWorkflow, ChildRoleID: "toolchain-go", ChildKind: RoleKindTechnical},
		},
		CatalogDigest: testDigest("catalog"), RoleDigest: testDigest("executor"), IssuedAt: "2026-08-23T20:00:00Z",
	}
	if err := SealSelection(&envelope); err != nil {
		t.Fatal(err)
	}
	return envelope
}

func TestSelectionWorkflowOwnsLeafInvocation(t *testing.T) {
	envelope := validSelectionEnvelope(t)
	if err := ValidateSelection(envelope); err != nil {
		t.Fatal(err)
	}
}

func TestSelectionAllowsJustifiedZeroLeaves(t *testing.T) {
	envelope := validSelectionEnvelope(t)
	envelope.ProposedLenses = []LensProposal{}
	envelope.SelectedLeafIDs = []string{}
	envelope.ZeroSelectionReason = "The workflow has sufficient direct capability"
	envelope.Invocations = envelope.Invocations[:1]
	if err := SealSelection(&envelope); err != nil {
		t.Fatal(err)
	}
	if err := ValidateSelection(envelope); err != nil {
		t.Fatal(err)
	}
}

func TestSelectionRejectsDirectRootToLeaf(t *testing.T) {
	envelope := validSelectionEnvelope(t)
	envelope.Invocations[1] = InvocationEdge{
		ParentRoleID: "workflow-coding-orchestrator", ParentKind: RoleKindOrchestrator,
		ChildRoleID: "toolchain-go", ChildKind: RoleKindTechnical,
	}
	if err := SealSelection(&envelope); err != nil {
		t.Fatal(err)
	}
	if err := ValidateSelection(envelope); err == nil {
		t.Fatal("direct root-to-leaf invocation accepted")
	}
}

func TestSelectionRejectsWrongRefinementOwner(t *testing.T) {
	envelope := validSelectionEnvelope(t)
	envelope.Refinements = []SelectionRefinement{{
		ActorRoleID: "workflow-planner", RoleID: "toolchain-go", Kind: RoleKindTechnical,
		Action: RefinementRetain, Reason: "incorrect owner", Evidence: []string{testDigest("evidence")},
	}}
	if err := SealSelection(&envelope); err != nil {
		t.Fatal(err)
	}
	if err := ValidateSelection(envelope); err == nil {
		t.Fatal("wrong refinement owner accepted")
	}
}
