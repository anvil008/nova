package runplane

import (
	"fmt"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
)

const capabilitySnapshotTTL = 5 * time.Minute

// BuildControlPlaneAdmission is a deterministic constructor for trusted
// orchestrator clients. The supervisor independently validates every returned
// record against the live catalog and capability snapshot before launch.
func BuildControlPlaneAdmission(route Route, capability Capability, issuedAt time.Time) (ControlPlaneAdmission, error) {
	issuedAt = issuedAt.UTC()
	if issuedAt.IsZero() {
		return ControlPlaneAdmission{}, fmt.Errorf("issuedAt is required")
	}
	if capability.ObservedAt.IsZero() {
		return ControlPlaneAdmission{}, fmt.Errorf("capability observation timestamp is required")
	}
	if route.Provider == "" || route.Family == "" {
		route.Provider, route.Family = harnessProviderFamily(route.TargetHarness)
	}
	if route.ParentRoleID == "" {
		route.ParentRoleID = "workflow-coding-orchestrator"
	}
	if route.AssignmentID == "" || route.GenerationID == "" || route.DispatchID == "" || route.GenerationNumber == 0 || route.RepositoryDigest == "" {
		return ControlPlaneAdmission{}, fmt.Errorf("assignment, generation, dispatch, generation number, and repository digest are required")
	}
	if route.Decision == "" {
		route.Decision = controlplane.RouteInherit
	}
	exact := controlplane.ExactRoute{Provider: route.Provider, Family: route.Family, Model: route.ExactModel, Effort: route.Effort}
	if route.ParentExactRoute == nil {
		parent := exact
		route.ParentExactRoute = &parent
	}

	document, err := codingfleet.Load()
	if err != nil {
		return ControlPlaneAdmission{}, err
	}
	binding, err := loadRoleBinding(route.CanonicalRoleID)
	if err != nil {
		return ControlPlaneAdmission{}, err
	}
	selectionRequest := codingfleet.SelectionRequest{
		SelectionID: "selection-" + route.DispatchID, GoalID: route.ParentGoalID,
		GenerationID: route.GenerationID, DispatchID: route.DispatchID, IssuedAt: issuedAt.Format(time.RFC3339Nano),
	}
	switch binding.Class {
	case codingfleet.ClassWorkflow:
		selectionRequest.WorkflowID = route.CanonicalRoleID
		selectionRequest.ProposedLenses = []controlplane.LensProposal{}
		selectionRequest.Refinements = []controlplane.SelectionRefinement{}
		selectionRequest.SelectedLeafIDs = []string{}
		selectionRequest.ZeroSelectionReason = "leaf selection is deferred to the selected workflow"
	case codingfleet.ClassTechnical, codingfleet.ClassDomain:
		selectionRequest.WorkflowID = route.ParentRoleID
		kind := controlplane.RoleKindTechnical
		if binding.Class == codingfleet.ClassDomain {
			kind = controlplane.RoleKindDomain
		}
		selectionRequest.ProposedLenses = []controlplane.LensProposal{{RoleID: route.CanonicalRoleID, Kind: kind, Reason: "selected by the parent workflow for this assignment"}}
		selectionRequest.Refinements = []controlplane.SelectionRefinement{}
		selectionRequest.SelectedLeafIDs = []string{route.CanonicalRoleID}
	default:
		return ControlPlaneAdmission{}, fmt.Errorf("role %q is not launchable", route.CanonicalRoleID)
	}
	selection, err := codingfleet.BuildSelection(document, selectionRequest)
	if err != nil {
		return ControlPlaneAdmission{}, err
	}

	requested := binding.Authority.Grant
	requested.Routes = controlplane.RouteConstraint{Providers: []string{exact.Provider}, Families: []string{exact.Family}, Models: []string{exact.Model}, Efforts: []string{exact.Effort}}
	requested.Budget = controlplane.BudgetLimit{
		MaxDelegates: route.Budget.Delegates, MaxWriters: route.Budget.Writers,
		MaxTokens: route.Budget.Tokens, MaxDurationSeconds: route.Budget.DurationSeconds,
	}
	requested.Evidence = controlplane.EvidenceRequirement{
		RequiredChecks: explicitStrings(route.Evidence.RequiredChecks), RequiredArtifacts: explicitStrings(route.Evidence.RequiredArtifacts),
		IndependentVerification: binding.Authority.Grant.Evidence.IndependentVerification,
	}
	if route.CapabilityMode == ModeWorkspaceWrite {
		requested.FilesystemWrite = explicitStrings(route.FileOwnership)
	} else {
		requested.FilesystemWrite = []string{}
	}
	observed := requested
	observed.ToolAllow = explicitStrings(binding.Authority.Grant.ToolAllow)
	observed.ToolDeny = explicitStrings(binding.Authority.Grant.ToolDeny)
	observed.FilesystemRead = explicitStrings(binding.Authority.Grant.FilesystemRead)
	observed.InvocableRoleKinds = explicitStrings(binding.Authority.Grant.InvocableRoleKinds)
	observed.InvocableRoleIDs = explicitStrings(binding.Authority.Grant.InvocableRoleIDs)
	capabilityMode, err := controlplaneCapabilityMode(route.CapabilityMode, binding.Authority.CapabilityMode)
	if err != nil {
		return ControlPlaneAdmission{}, err
	}
	authority := controlplane.AuthorityEnvelope{
		APIVersion: controlplane.AuthorityAPIVersion, GrantID: "grant-" + route.DispatchID,
		ParentGrantID: "grant-" + route.ParentGoalID, RoleID: route.CanonicalRoleID, RoleDigest: binding.Digest,
		Lane: string(roleLane(document, route.CanonicalRoleID)), CapabilityMode: capabilityMode,
		ParentGrant: binding.Authority.Grant, RoleCeiling: binding.Authority.Grant,
		RequestedGrant: requested, ObservedGrant: observed, IssuedAt: issuedAt.Format(time.RFC3339Nano),
	}
	if err := controlplane.SealAuthority(&authority); err != nil {
		return ControlPlaneAdmission{}, err
	}

	goal := controlplane.GoalRecord{APIVersion: controlplane.LifecycleAPIVersion, GoalID: route.ParentGoalID, RepositoryDigest: route.RepositoryDigest, CreatedAt: issuedAt.Format(time.RFC3339Nano)}
	if err := controlplane.SealGoal(&goal); err != nil {
		return ControlPlaneAdmission{}, err
	}
	assignment := controlplane.AssignmentRecord{
		APIVersion: controlplane.LifecycleAPIVersion, AssignmentID: route.AssignmentID, GoalID: route.ParentGoalID,
		GenerationID: route.GenerationID, RoleID: route.CanonicalRoleID, Lane: string(roleLane(document, route.CanonicalRoleID)), CreatedAt: issuedAt.Format(time.RFC3339Nano),
	}
	if err := controlplane.SealAssignment(&assignment); err != nil {
		return ControlPlaneAdmission{}, err
	}
	generation := controlplane.GenerationRecord{
		APIVersion: controlplane.LifecycleAPIVersion, GoalID: route.ParentGoalID, GenerationID: route.GenerationID,
		GenerationNumber: route.GenerationNumber, ParentGenerationID: route.ParentGenerationID,
		RepositoryDigest: route.RepositoryDigest, CreatedAt: issuedAt.Format(time.RFC3339Nano),
	}
	if err := controlplane.SealGeneration(&generation); err != nil {
		return ControlPlaneAdmission{}, err
	}
	dispatch := controlplane.DispatchRecord{
		APIVersion: controlplane.LifecycleAPIVersion, DispatchID: route.DispatchID, ParentDispatchID: route.ParentDispatchID,
		GoalID: route.ParentGoalID, AssignmentID: route.AssignmentID, GenerationID: route.GenerationID,
		RoleID: route.CanonicalRoleID, CreatedAt: issuedAt.Format(time.RFC3339Nano),
	}
	if err := controlplane.SealDispatch(&dispatch); err != nil {
		return ControlPlaneAdmission{}, err
	}

	reservation := controlplane.BudgetReservation{
		APIVersion: controlplane.LifecycleAPIVersion, ReservationID: "budget-" + route.DispatchID,
		GoalID: route.ParentGoalID, GenerationID: route.GenerationID, DispatchID: route.DispatchID,
		Reserved: route.Budget, Active: route.Budget, UpdatedAt: issuedAt.Format(time.RFC3339Nano),
	}
	if err := controlplane.SealBudgetReservation(&reservation); err != nil {
		return ControlPlaneAdmission{}, err
	}

	ownership := []controlplane.OwnershipClaim{}
	claimIDs := []string{}
	if len(route.FileOwnership)+len(route.SymbolOwnership) > 0 {
		mode := controlplane.OwnershipRead
		if route.CapabilityMode == ModeWorkspaceWrite {
			mode = controlplane.OwnershipWrite
		}
		claim := controlplane.OwnershipClaim{
			APIVersion: controlplane.LifecycleAPIVersion, ClaimID: "ownership-" + route.DispatchID,
			GoalID: route.ParentGoalID, GenerationID: route.GenerationID, DispatchID: route.DispatchID, Mode: mode,
			Paths: explicitStrings(route.FileOwnership), Symbols: explicitSymbols(route.SymbolOwnership),
			IssuedAt: issuedAt.Format(time.RFC3339Nano), ExpiresAt: issuedAt.Add(capabilitySnapshotTTL).Format(time.RFC3339Nano),
		}
		if err := controlplane.SealOwnership(&claim); err != nil {
			return ControlPlaneAdmission{}, err
		}
		ownership = append(ownership, claim)
		claimIDs = append(claimIDs, claim.ClaimID)
	}

	snapshot := controlplane.CapabilitySnapshot{
		HarnessID: string(capability.Harness), Routes: capabilityExactRoutes(capability),
		ObservedAt: capability.ObservedAt.UTC().Format(time.RFC3339Nano),
		ExpiresAt:  capability.ObservedAt.UTC().Add(capabilitySnapshotTTL).Format(time.RFC3339Nano),
	}
	if err := controlplane.SealCapabilitySnapshot(&snapshot); err != nil {
		return ControlPlaneAdmission{}, err
	}
	cpRoute := controlplane.RouteEnvelope{
		APIVersion: controlplane.RouteAPIVersion, RouteID: "route-" + route.DispatchID,
		GoalID: route.ParentGoalID, AssignmentID: route.AssignmentID, GenerationID: route.GenerationID,
		DispatchID: route.DispatchID, ParentDispatchID: route.ParentDispatchID,
		SourceHarness: string(route.SourceHarness), TargetHarness: string(route.TargetHarness),
		Decision: route.Decision, ParentRoute: route.ParentExactRoute, RequestedRoute: exact,
		CanonicalRoleID: route.CanonicalRoleID, RoleDigest: binding.Digest, AuthorityDigest: authority.Digest,
		SelectionDigest: selection.Digest, RepositoryDigest: route.RepositoryDigest, Capability: snapshot,
		OwnershipClaimIDs: claimIDs, BudgetReservationID: reservation.ReservationID,
		Evidence:             controlplane.EvidenceRequirement{RequiredChecks: explicitStrings(route.Evidence.RequiredChecks), RequiredArtifacts: explicitStrings(route.Evidence.RequiredArtifacts), IndependentVerification: authority.EffectiveGrant.Evidence.IndependentVerification},
		RefinementAuthorized: route.RefinementAuthorized, RefinementReason: route.RefinementReason,
		OnUnavailable: controlplane.RouteUnavailableReject, IssuedAt: issuedAt.Format(time.RFC3339Nano),
		ExpiresAt: issuedAt.Add(capabilitySnapshotTTL).Format(time.RFC3339Nano),
	}
	if err := controlplane.SealRoute(&cpRoute); err != nil {
		return ControlPlaneAdmission{}, err
	}
	return ControlPlaneAdmission{
		Authority: authority, Selection: selection, Route: cpRoute, Goal: goal,
		Assignment: assignment, Generation: generation, Dispatch: dispatch,
		Budget: reservation, Ownership: ownership,
	}, nil
}

func capabilityExactRoutes(capability Capability) []controlplane.ExactRoute {
	routes := make([]controlplane.ExactRoute, 0, len(capability.ModelEfforts))
	for _, pair := range capability.ModelEfforts {
		if pair.Reference == "alias" {
			continue
		}
		provider, family := pair.Provider, pair.Family
		if provider == "" || family == "" {
			provider, family = harnessProviderFamily(capability.Harness)
		}
		routes = append(routes, controlplane.ExactRoute{Provider: provider, Family: family, Model: pair.Model, Effort: pair.Effort})
	}
	return routes
}

func roleLane(document codingfleet.Document, roleID string) codingfleet.WorkflowLane {
	for _, role := range document.Roles {
		if role.ID == roleID && role.Workflow != nil {
			return role.Workflow.Lane
		}
	}
	return "specialist"
}

func explicitStrings(values []string) []string {
	result := make([]string, len(values))
	copy(result, values)
	return result
}

func explicitSymbols(values []controlplane.SymbolClaim) []controlplane.SymbolClaim {
	result := make([]controlplane.SymbolClaim, len(values))
	copy(result, values)
	return result
}
