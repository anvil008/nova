package codingfleet

import (
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
)

func TestBuildSelectionKeepsWorkflowOwnership(t *testing.T) {
	document := mustLoad(t)
	envelope, err := BuildSelection(document, SelectionRequest{
		SelectionID: "selection-1", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-1",
		WorkflowID:     workflowExecutorID,
		ProposedLenses: []controlplane.LensProposal{{RoleID: "technical-go", Kind: controlplane.RoleKindTechnical, Reason: "Go implementation"}},
		Refinements:    []controlplane.SelectionRefinement{}, SelectedLeafIDs: []string{"technical-go"}, IssuedAt: "2026-08-23T20:00:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := ValidateSelection(document, envelope); err != nil {
		t.Fatal(err)
	}
	if got := envelope.Invocations[1].ParentRoleID; got != workflowExecutorID {
		t.Fatalf("leaf invocation parent = %q", got)
	}
}

func TestBuildSelectionAllowsZeroLeaves(t *testing.T) {
	document := mustLoad(t)
	envelope, err := BuildSelection(document, SelectionRequest{
		SelectionID: "selection-zero", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-1",
		WorkflowID: workflowResearchID, ProposedLenses: []controlplane.LensProposal{}, Refinements: []controlplane.SelectionRefinement{},
		SelectedLeafIDs: []string{}, ZeroSelectionReason: "Direct repository inspection is sufficient", IssuedAt: "2026-08-23T20:00:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(envelope.Invocations) != 1 {
		t.Fatalf("zero-leaf selection invocations = %+v", envelope.Invocations)
	}
}

func TestCatalogSelectionRejectsRootToLeafAndStaleCatalog(t *testing.T) {
	document := mustLoad(t)
	envelope, err := BuildSelection(document, SelectionRequest{
		SelectionID: "selection-1", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-1",
		WorkflowID:     workflowExecutorID,
		ProposedLenses: []controlplane.LensProposal{{RoleID: "technical-go", Kind: controlplane.RoleKindTechnical, Reason: "Go implementation"}},
		Refinements:    []controlplane.SelectionRefinement{}, SelectedLeafIDs: []string{"technical-go"}, IssuedAt: "2026-08-23T20:00:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	envelope.Invocations[1].ParentRoleID = workflowCodingOrchestratorID
	envelope.Invocations[1].ParentKind = controlplane.RoleKindOrchestrator
	if err := controlplane.SealSelection(&envelope); err != nil {
		t.Fatal(err)
	}
	if err := ValidateSelection(document, envelope); err == nil {
		t.Fatal("direct root-to-leaf edge accepted")
	}
	envelope, err = BuildSelection(document, SelectionRequest{
		SelectionID: "selection-2", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-2",
		WorkflowID: workflowResearchID, ProposedLenses: []controlplane.LensProposal{}, Refinements: []controlplane.SelectionRefinement{},
		SelectedLeafIDs: []string{}, ZeroSelectionReason: "No leaf needed", IssuedAt: "2026-08-23T20:00:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	document.CatalogVersion = "changed"
	if err := ValidateSelection(document, envelope); err == nil {
		t.Fatal("selection against changed catalog accepted")
	}
}

func TestAuthorityProfilesSeparateWorkflowAndLeafInvocation(t *testing.T) {
	document := mustLoad(t)
	orchestrator, err := AuthorityForRole(document, workflowCodingOrchestratorID)
	if err != nil {
		t.Fatal(err)
	}
	if len(orchestrator.Grant.InvocableRoleKinds) != 1 || orchestrator.Grant.InvocableRoleKinds[0] != "workflow" {
		t.Fatalf("orchestrator invocation ceiling = %+v", orchestrator.Grant)
	}
	leaf, err := AuthorityForRole(document, "technical-go")
	if err != nil {
		t.Fatal(err)
	}
	if len(leaf.Grant.InvocableRoleKinds) != 0 || len(leaf.Grant.InvocableRoleIDs) != 0 {
		t.Fatalf("leaf gained delegation authority: %+v", leaf.Grant)
	}
}
