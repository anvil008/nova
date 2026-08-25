package codingfleet

import (
	"fmt"

	"github.com/anvil008/swarm-coder/controlplane"
)

type SelectionRequest struct {
	SelectionID         string
	GoalID              string
	GenerationID        string
	DispatchID          string
	WorkflowID          string
	ProposedLenses      []controlplane.LensProposal
	Refinements         []controlplane.SelectionRefinement
	SelectedLeafIDs     []string
	ZeroSelectionReason string
	IssuedAt            string
}

// BuildSelection binds the proposal/refinement decision to the exact catalog.
// The returned graph always keeps root-to-workflow and workflow-to-leaf as
// separate edges; no caller can request a direct root-to-leaf edge here.
func BuildSelection(document Document, request SelectionRequest) (controlplane.SelectionEnvelope, error) {
	workflow, ok := catalogRoleByID(document, request.WorkflowID)
	if !ok || workflow.Class != ClassWorkflow || workflow.ID == workflowCodingOrchestratorID || workflow.Workflow == nil {
		return controlplane.SelectionEnvelope{}, fmt.Errorf("workflow %q is not an invocable peer workflow", request.WorkflowID)
	}
	orchestrator, ok := catalogRoleByID(document, workflowCodingOrchestratorID)
	if !ok || orchestrator.Workflow == nil || !containsStringValue(orchestrator.Workflow.InvocableRoleIDs, workflow.ID) {
		return controlplane.SelectionEnvelope{}, fmt.Errorf("workflow %q is outside orchestrator invocation authority", workflow.ID)
	}
	for _, proposal := range request.ProposedLenses {
		if err := validateCatalogLens(document, workflow, proposal.RoleID, proposal.Kind); err != nil {
			return controlplane.SelectionEnvelope{}, err
		}
	}
	for _, refinement := range request.Refinements {
		if refinement.ActorRoleID != workflow.ID {
			return controlplane.SelectionEnvelope{}, fmt.Errorf("selection refinement is not owned by workflow %q", workflow.ID)
		}
		if err := validateCatalogLens(document, workflow, refinement.RoleID, refinement.Kind); err != nil {
			return controlplane.SelectionEnvelope{}, err
		}
	}

	catalogDigest, err := CatalogDigest(document)
	if err != nil {
		return controlplane.SelectionEnvelope{}, err
	}
	roleDigest, err := RoleDigest(document, workflow.ID)
	if err != nil {
		return controlplane.SelectionEnvelope{}, err
	}
	invocations := []controlplane.InvocationEdge{{
		ParentRoleID: workflowCodingOrchestratorID, ParentKind: controlplane.RoleKindOrchestrator,
		ChildRoleID: workflow.ID, ChildKind: controlplane.RoleKindWorkflow,
	}}
	for _, roleID := range request.SelectedLeafIDs {
		role, exists := catalogRoleByID(document, roleID)
		if !exists {
			return controlplane.SelectionEnvelope{}, fmt.Errorf("selected leaf %q does not exist", roleID)
		}
		kind, err := controlplaneKind(role.Class)
		if err != nil {
			return controlplane.SelectionEnvelope{}, err
		}
		if err := validateCatalogLens(document, workflow, role.ID, kind); err != nil {
			return controlplane.SelectionEnvelope{}, err
		}
		invocations = append(invocations, controlplane.InvocationEdge{
			ParentRoleID: workflow.ID, ParentKind: controlplane.RoleKindWorkflow,
			ChildRoleID: role.ID, ChildKind: kind,
		})
	}
	envelope := controlplane.SelectionEnvelope{
		APIVersion: controlplane.SelectionAPIVersion, SelectionID: request.SelectionID,
		GoalID: request.GoalID, GenerationID: request.GenerationID, DispatchID: request.DispatchID,
		ProposedWorkflowID: workflow.ID, ProposedLenses: append([]controlplane.LensProposal(nil), request.ProposedLenses...),
		Refinements:     append([]controlplane.SelectionRefinement(nil), request.Refinements...),
		SelectedLeafIDs: append([]string(nil), request.SelectedLeafIDs...), ZeroSelectionReason: request.ZeroSelectionReason,
		WorkflowOwnerID: workflow.ID, Invocations: invocations, CatalogDigest: catalogDigest,
		RoleDigest: roleDigest, IssuedAt: request.IssuedAt,
	}
	if envelope.ProposedLenses == nil {
		envelope.ProposedLenses = []controlplane.LensProposal{}
	}
	if envelope.Refinements == nil {
		envelope.Refinements = []controlplane.SelectionRefinement{}
	}
	if envelope.SelectedLeafIDs == nil {
		envelope.SelectedLeafIDs = []string{}
	}
	if err := controlplane.SealSelection(&envelope); err != nil {
		return controlplane.SelectionEnvelope{}, err
	}
	if err := ValidateSelection(document, envelope); err != nil {
		return controlplane.SelectionEnvelope{}, err
	}
	return envelope, nil
}

func ValidateSelection(document Document, envelope controlplane.SelectionEnvelope) error {
	if err := controlplane.ValidateSelection(envelope); err != nil {
		return err
	}
	catalogDigest, err := CatalogDigest(document)
	if err != nil {
		return err
	}
	if envelope.CatalogDigest != catalogDigest {
		return fmt.Errorf("selection catalog digest is stale")
	}
	workflow, ok := catalogRoleByID(document, envelope.WorkflowOwnerID)
	if !ok || workflow.Workflow == nil || workflow.ID == workflowCodingOrchestratorID {
		return fmt.Errorf("selection workflow owner %q is invalid", envelope.WorkflowOwnerID)
	}
	roleDigest, err := RoleDigest(document, workflow.ID)
	if err != nil {
		return err
	}
	if envelope.RoleDigest != roleDigest {
		return fmt.Errorf("selection workflow role digest is stale")
	}
	for _, proposal := range envelope.ProposedLenses {
		if err := validateCatalogLens(document, workflow, proposal.RoleID, proposal.Kind); err != nil {
			return err
		}
	}
	for _, refinement := range envelope.Refinements {
		if err := validateCatalogLens(document, workflow, refinement.RoleID, refinement.Kind); err != nil {
			return err
		}
	}
	for _, roleID := range envelope.SelectedLeafIDs {
		role, ok := catalogRoleByID(document, roleID)
		if !ok {
			return fmt.Errorf("selected leaf %q is absent from catalog", roleID)
		}
		kind, err := controlplaneKind(role.Class)
		if err != nil {
			return err
		}
		if err := validateCatalogLens(document, workflow, roleID, kind); err != nil {
			return err
		}
	}
	return nil
}

func CatalogDigest(document Document) (string, error) {
	encoded, err := controlplane.EncodeCanonical(document)
	if err != nil {
		return "", err
	}
	return controlplane.CanonicalDigest(encoded)
}

func RoleDigest(document Document, roleID string) (string, error) {
	role, ok := catalogRoleByID(document, roleID)
	if !ok {
		return "", fmt.Errorf("role %q does not exist", roleID)
	}
	authority, err := AuthorityForRole(document, roleID)
	if err != nil {
		return "", err
	}
	payload := struct {
		Role      Role             `json:"role"`
		Authority AuthorityProfile `json:"authority"`
	}{Role: role, Authority: authority}
	encoded, err := controlplane.EncodeCanonical(payload)
	if err != nil {
		return "", err
	}
	return controlplane.CanonicalDigest(encoded)
}

func validateCatalogLens(document Document, workflow Role, roleID string, kind controlplane.RoleKind) error {
	role, ok := catalogRoleByID(document, roleID)
	if !ok {
		return fmt.Errorf("specialist lens %q does not exist", roleID)
	}
	wantKind, err := controlplaneKind(role.Class)
	if err != nil || wantKind != kind {
		return fmt.Errorf("specialist lens %q kind does not match catalog", roleID)
	}
	pool := SpecialistPool(role.Class)
	if !containsPool(workflow.Workflow.InvocableSpecialistPools, pool) {
		return fmt.Errorf("workflow %q cannot invoke %s pool", workflow.ID, pool)
	}
	return nil
}

func controlplaneKind(class RoleClass) (controlplane.RoleKind, error) {
	switch class {
	case ClassTechnical:
		return controlplane.RoleKindTechnical, nil
	case ClassDomain:
		return controlplane.RoleKindDomain, nil
	default:
		return "", fmt.Errorf("role class %q is not a specialist leaf", class)
	}
}

func catalogRoleByID(document Document, roleID string) (Role, bool) {
	for _, role := range document.Roles {
		if role.ID == roleID {
			return role, true
		}
	}
	return Role{}, false
}

func containsPool(values []SpecialistPool, wanted SpecialistPool) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func containsStringValue(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}
