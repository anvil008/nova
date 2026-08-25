package controlplane

import (
	"fmt"
	"sort"
)

const SelectionAPIVersion = "anvil.selection/v1"

type RoleKind string

const (
	RoleKindOrchestrator RoleKind = "orchestrator"
	RoleKindWorkflow     RoleKind = "workflow"
	RoleKindTechnical    RoleKind = "technical"
	RoleKindDomain       RoleKind = "domain"
)

type LensProposal struct {
	RoleID string   `json:"roleId"`
	Kind   RoleKind `json:"kind"`
	Reason string   `json:"reason"`
}

type RefinementAction string

const (
	RefinementAdd    RefinementAction = "add"
	RefinementRemove RefinementAction = "remove"
	RefinementRetain RefinementAction = "retain"
)

type SelectionRefinement struct {
	ActorRoleID string           `json:"actorRoleId"`
	RoleID      string           `json:"roleId"`
	Kind        RoleKind         `json:"kind"`
	Action      RefinementAction `json:"action"`
	Reason      string           `json:"reason"`
	Evidence    []string         `json:"evidence"`
}

type InvocationEdge struct {
	ParentRoleID string   `json:"parentRoleId"`
	ParentKind   RoleKind `json:"parentKind"`
	ChildRoleID  string   `json:"childRoleId"`
	ChildKind    RoleKind `json:"childKind"`
}

// SelectionEnvelope separates proposal visibility from invocation. The
// orchestrator may propose workflow and specialist lenses, but leaf edges are
// owned by the selected workflow.
type SelectionEnvelope struct {
	APIVersion          string                `json:"apiVersion"`
	SelectionID         string                `json:"selectionId"`
	GoalID              string                `json:"goalId"`
	GenerationID        string                `json:"generationId"`
	DispatchID          string                `json:"dispatchId"`
	ProposedWorkflowID  string                `json:"proposedWorkflowId"`
	ProposedLenses      []LensProposal        `json:"proposedLenses"`
	Refinements         []SelectionRefinement `json:"refinements"`
	SelectedLeafIDs     []string              `json:"selectedLeafIds"`
	ZeroSelectionReason string                `json:"zeroSelectionReason"`
	WorkflowOwnerID     string                `json:"workflowOwnerId"`
	Invocations         []InvocationEdge      `json:"invocations"`
	CatalogDigest       string                `json:"catalogDigest"`
	RoleDigest          string                `json:"roleDigest"`
	IssuedAt            string                `json:"issuedAt"`
	Digest              string                `json:"digest"`
}

func ValidateSelection(envelope SelectionEnvelope) error {
	if envelope.APIVersion != SelectionAPIVersion {
		return fmt.Errorf("%w: selection apiVersion %q", ErrInvalidContractVer, envelope.APIVersion)
	}
	for name, value := range map[string]string{
		"selectionId": envelope.SelectionID, "goalId": envelope.GoalID,
		"generationId": envelope.GenerationID, "dispatchId": envelope.DispatchID,
		"proposedWorkflowId": envelope.ProposedWorkflowID, "workflowOwnerId": envelope.WorkflowOwnerID,
	} {
		if err := ValidateIdentifier(value); err != nil {
			return fmt.Errorf("%w: %s: %v", ErrInvalidContract, name, err)
		}
	}
	if envelope.ProposedWorkflowID != envelope.WorkflowOwnerID {
		return fmt.Errorf("%w: workflow owner must be the proposed workflow", ErrInvalidContract)
	}
	if envelope.ProposedLenses == nil || envelope.Refinements == nil || envelope.SelectedLeafIDs == nil || envelope.Invocations == nil {
		return fmt.Errorf("%w: selection sets must be explicit, not null", ErrInvalidContract)
	}
	if len(envelope.ProposedLenses) > 256 || len(envelope.Refinements) > 256 || len(envelope.SelectedLeafIDs) > 256 || len(envelope.Invocations) > 257 {
		return fmt.Errorf("%w: selection exceeds bounded cardinality", ErrInvalidContract)
	}
	if err := ValidateDigest(envelope.CatalogDigest); err != nil {
		return fmt.Errorf("%w: catalogDigest: %v", ErrInvalidContract, err)
	}
	if err := ValidateDigest(envelope.RoleDigest); err != nil {
		return fmt.Errorf("%w: roleDigest: %v", ErrInvalidContract, err)
	}
	if err := ValidateTimestamp(envelope.IssuedAt); err != nil {
		return err
	}

	available := make(map[string]RoleKind)
	removed := make(map[string]bool)
	for _, proposal := range envelope.ProposedLenses {
		if err := validateLens(proposal.RoleID, proposal.Kind, proposal.Reason); err != nil {
			return fmt.Errorf("%w: proposal: %v", ErrInvalidContract, err)
		}
		if _, duplicate := available[proposal.RoleID]; duplicate {
			return fmt.Errorf("%w: duplicate proposed lens %q", ErrInvalidContract, proposal.RoleID)
		}
		available[proposal.RoleID] = proposal.Kind
	}
	for _, refinement := range envelope.Refinements {
		if refinement.ActorRoleID != envelope.WorkflowOwnerID {
			return fmt.Errorf("%w: refinement actor %q is not workflow owner", ErrInvalidContract, refinement.ActorRoleID)
		}
		if err := validateLens(refinement.RoleID, refinement.Kind, refinement.Reason); err != nil {
			return fmt.Errorf("%w: refinement: %v", ErrInvalidContract, err)
		}
		if refinement.Evidence == nil || len(refinement.Evidence) == 0 {
			return fmt.Errorf("%w: refinement %q lacks evidence", ErrInvalidContract, refinement.RoleID)
		}
		for _, digest := range refinement.Evidence {
			if err := ValidateDigest(digest); err != nil {
				return fmt.Errorf("%w: refinement evidence: %v", ErrInvalidContract, err)
			}
		}
		switch refinement.Action {
		case RefinementAdd:
			available[refinement.RoleID] = refinement.Kind
			delete(removed, refinement.RoleID)
		case RefinementRemove:
			if _, ok := available[refinement.RoleID]; !ok {
				return fmt.Errorf("%w: cannot remove unknown lens %q", ErrInvalidContract, refinement.RoleID)
			}
			removed[refinement.RoleID] = true
		case RefinementRetain:
			if _, ok := available[refinement.RoleID]; !ok {
				return fmt.Errorf("%w: cannot retain unknown lens %q", ErrInvalidContract, refinement.RoleID)
			}
		default:
			return fmt.Errorf("%w: invalid refinement action %q", ErrInvalidContract, refinement.Action)
		}
	}

	selected := sortedUnique(envelope.SelectedLeafIDs)
	if len(selected) != len(envelope.SelectedLeafIDs) {
		return fmt.Errorf("%w: selected leaf ids contain duplicates", ErrInvalidContract)
	}
	if len(selected) == 0 {
		if envelope.ZeroSelectionReason == "" {
			return fmt.Errorf("%w: zero-leaf selection requires a reason", ErrInvalidContract)
		}
	} else if envelope.ZeroSelectionReason != "" {
		return fmt.Errorf("%w: zero-leaf reason present with selected leaves", ErrInvalidContract)
	}
	selectedSet := make(map[string]struct{}, len(selected))
	for _, roleID := range selected {
		kind, ok := available[roleID]
		if !ok || removed[roleID] {
			return fmt.Errorf("%w: selected leaf %q was not retained or added", ErrInvalidContract, roleID)
		}
		if kind != RoleKindTechnical && kind != RoleKindDomain {
			return fmt.Errorf("%w: selected role %q is not a leaf", ErrInvalidContract, roleID)
		}
		selectedSet[roleID] = struct{}{}
	}

	invokedLeaves := make(map[string]struct{})
	workflowEdge := false
	for _, edge := range envelope.Invocations {
		if err := ValidateIdentifier(edge.ParentRoleID); err != nil {
			return err
		}
		if err := ValidateIdentifier(edge.ChildRoleID); err != nil {
			return err
		}
		switch {
		case edge.ParentKind == RoleKindOrchestrator && edge.ChildKind == RoleKindWorkflow:
			if edge.ChildRoleID != envelope.WorkflowOwnerID {
				return fmt.Errorf("%w: orchestrator invoked an unselected workflow", ErrInvalidContract)
			}
			workflowEdge = true
		case edge.ParentKind == RoleKindWorkflow && (edge.ChildKind == RoleKindTechnical || edge.ChildKind == RoleKindDomain):
			if edge.ParentRoleID != envelope.WorkflowOwnerID {
				return fmt.Errorf("%w: leaf invocation is not owned by the selected workflow", ErrInvalidContract)
			}
			if _, selected := selectedSet[edge.ChildRoleID]; !selected {
				return fmt.Errorf("%w: invoked leaf %q is not selected", ErrInvalidContract, edge.ChildRoleID)
			}
			invokedLeaves[edge.ChildRoleID] = struct{}{}
		case edge.ParentKind == RoleKindOrchestrator && (edge.ChildKind == RoleKindTechnical || edge.ChildKind == RoleKindDomain):
			return fmt.Errorf("%w: direct orchestrator-to-leaf invocation", ErrInvalidContract)
		case (edge.ParentKind == RoleKindTechnical || edge.ParentKind == RoleKindDomain) && edge.ChildKind == RoleKindWorkflow:
			return fmt.Errorf("%w: specialist-to-workflow invocation", ErrInvalidContract)
		default:
			return fmt.Errorf("%w: invalid invocation edge %s->%s", ErrInvalidContract, edge.ParentKind, edge.ChildKind)
		}
	}
	if !workflowEdge {
		return fmt.Errorf("%w: missing orchestrator-to-workflow edge", ErrInvalidContract)
	}
	if len(invokedLeaves) != len(selectedSet) {
		return fmt.Errorf("%w: selected and invoked leaf sets differ", ErrInvalidContract)
	}
	if err := ValidateDigest(envelope.Digest); err != nil {
		return err
	}
	expectedDigest, err := digestWithoutField(envelope, "digest")
	if err != nil {
		return err
	}
	if envelope.Digest != expectedDigest {
		return fmt.Errorf("%w: selection digest mismatch", ErrInvalidDigest)
	}
	return nil
}

func SealSelection(envelope *SelectionEnvelope) error {
	if envelope == nil {
		return fmt.Errorf("%w: nil selection envelope", ErrInvalidContract)
	}
	sort.Slice(envelope.ProposedLenses, func(i, j int) bool { return envelope.ProposedLenses[i].RoleID < envelope.ProposedLenses[j].RoleID })
	envelope.SelectedLeafIDs = sortedUnique(envelope.SelectedLeafIDs)
	envelope.Digest = ""
	digest, err := digestWithoutField(*envelope, "digest")
	if err != nil {
		return err
	}
	envelope.Digest = digest
	return nil
}

func DecodeSelection(raw []byte) (SelectionEnvelope, error) {
	var envelope SelectionEnvelope
	if err := DecodeStrict(raw, &envelope); err != nil {
		return SelectionEnvelope{}, err
	}
	if err := ValidateSelection(envelope); err != nil {
		return SelectionEnvelope{}, err
	}
	return envelope, nil
}

func validateLens(roleID string, kind RoleKind, reason string) error {
	if err := ValidateIdentifier(roleID); err != nil {
		return err
	}
	if kind != RoleKindTechnical && kind != RoleKindDomain {
		return fmt.Errorf("role %q has non-leaf kind %q", roleID, kind)
	}
	if reason == "" {
		return fmt.Errorf("role %q lacks a reason", roleID)
	}
	return nil
}
