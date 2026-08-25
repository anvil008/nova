package controlplane

import (
	"fmt"
	"sort"
	"time"
)

const RouteAPIVersion = "anvil.route/v1"

const RouteUnavailableReject = "reject"

// RouteDecision records whether a child inherited its parent's exact route or
// used an explicitly authorized refinement. Reject is a recorded admission
// outcome and is never a launchable envelope.
type RouteDecision string

const (
	RouteInherit RouteDecision = "inherit"
	RouteRefine  RouteDecision = "refine"
	RouteReject  RouteDecision = "reject"
)

// ExactRoute deliberately keeps provider, family, model, and effort separate.
// Callers must resolve aliases before constructing this value.
type ExactRoute struct {
	Provider string `json:"provider"`
	Family   string `json:"family"`
	Model    string `json:"model"`
	Effort   string `json:"effort"`
}

// CapabilitySnapshot is the exact discovered allowlist used at admission.
// It is embedded into the route record so later reviewers can distinguish a
// genuinely unavailable route from a silent substitution.
type CapabilitySnapshot struct {
	HarnessID  string       `json:"harnessId"`
	Routes     []ExactRoute `json:"routes"`
	ObservedAt string       `json:"observedAt"`
	ExpiresAt  string       `json:"expiresAt"`
	Digest     string       `json:"digest"`
}

// RouteEnvelope is the immutable admission record for one dispatch.
type RouteEnvelope struct {
	APIVersion           string              `json:"apiVersion"`
	RouteID              string              `json:"routeId"`
	GoalID               string              `json:"goalId"`
	AssignmentID         string              `json:"assignmentId"`
	GenerationID         string              `json:"generationId"`
	DispatchID           string              `json:"dispatchId"`
	ParentDispatchID     string              `json:"parentDispatchId"`
	SourceHarness        string              `json:"sourceHarness"`
	TargetHarness        string              `json:"targetHarness"`
	Decision             RouteDecision       `json:"decision"`
	ParentRoute          *ExactRoute         `json:"parentRoute"`
	RequestedRoute       ExactRoute          `json:"requestedRoute"`
	EffectiveRoute       ExactRoute          `json:"effectiveRoute"`
	CanonicalRoleID      string              `json:"canonicalRoleId"`
	RoleDigest           string              `json:"roleDigest"`
	AuthorityDigest      string              `json:"authorityDigest"`
	SelectionDigest      string              `json:"selectionDigest"`
	RepositoryDigest     string              `json:"repositoryDigest"`
	Capability           CapabilitySnapshot  `json:"capability"`
	OwnershipClaimIDs    []string            `json:"ownershipClaimIds"`
	BudgetReservationID  string              `json:"budgetReservationId"`
	Evidence             EvidenceRequirement `json:"evidence"`
	RefinementAuthorized bool                `json:"refinementAuthorized"`
	RefinementReason     string              `json:"refinementReason"`
	OnUnavailable        string              `json:"onUnavailable"`
	IssuedAt             string              `json:"issuedAt"`
	ExpiresAt            string              `json:"expiresAt"`
	Digest               string              `json:"digest"`
}

// SealCapabilitySnapshot normalizes the allowlist and records its digest.
func SealCapabilitySnapshot(snapshot *CapabilitySnapshot) error {
	if snapshot == nil {
		return fmt.Errorf("%w: nil capability snapshot", ErrInvalidContract)
	}
	sort.Slice(snapshot.Routes, func(i, j int) bool { return routeKey(snapshot.Routes[i]) < routeKey(snapshot.Routes[j]) })
	for index := 1; index < len(snapshot.Routes); index++ {
		if routeEqual(snapshot.Routes[index-1], snapshot.Routes[index]) {
			return fmt.Errorf("%w: duplicate capability route %q", ErrInvalidContract, routeKey(snapshot.Routes[index]))
		}
	}
	snapshot.Digest = ""
	digest, err := digestWithoutField(*snapshot, "digest")
	if err != nil {
		return err
	}
	snapshot.Digest = digest
	return validateCapabilitySnapshot(*snapshot)
}

func validateCapabilitySnapshot(snapshot CapabilitySnapshot) error {
	if err := ValidateIdentifier(snapshot.HarnessID); err != nil {
		return fmt.Errorf("%w: capability harness: %v", ErrInvalidContract, err)
	}
	if snapshot.Routes == nil {
		return fmt.Errorf("%w: capability routes must be explicit", ErrInvalidContract)
	}
	if len(snapshot.Routes) > 512 {
		return fmt.Errorf("%w: capability snapshot exceeds 512 routes", ErrInvalidContract)
	}
	seen := make(map[string]struct{}, len(snapshot.Routes))
	for _, route := range snapshot.Routes {
		if err := validateExactRoute(route); err != nil {
			return err
		}
		key := routeKey(route)
		if _, duplicate := seen[key]; duplicate {
			return fmt.Errorf("%w: duplicate capability route %q", ErrInvalidContract, key)
		}
		seen[key] = struct{}{}
	}
	observed, err := time.Parse(time.RFC3339Nano, snapshot.ObservedAt)
	if err != nil || observed.IsZero() {
		return fmt.Errorf("%w: invalid capability observedAt", ErrInvalidContract)
	}
	expires, err := time.Parse(time.RFC3339Nano, snapshot.ExpiresAt)
	if err != nil || !expires.After(observed) {
		return fmt.Errorf("%w: capability expiresAt must follow observedAt", ErrInvalidContract)
	}
	if err := ValidateDigest(snapshot.Digest); err != nil {
		return err
	}
	expected, err := digestWithoutField(snapshot, "digest")
	if err != nil {
		return err
	}
	if snapshot.Digest != expected {
		return fmt.Errorf("%w: capability snapshot digest mismatch", ErrInvalidDigest)
	}
	return nil
}

// ResolveRoute applies the fail-closed inheritance/refinement rules without
// launching a process or reserving resources.
func ResolveRoute(parent *ExactRoute, requested ExactRoute, decision RouteDecision, refinementAuthorized bool, refinementReason string, capability CapabilitySnapshot, issuedAt string) (ExactRoute, error) {
	if err := validateCapabilitySnapshot(capability); err != nil {
		return ExactRoute{}, err
	}
	issued, err := time.Parse(time.RFC3339Nano, issuedAt)
	if err != nil {
		return ExactRoute{}, fmt.Errorf("%w: invalid route issuedAt", ErrInvalidContract)
	}
	observed, _ := time.Parse(time.RFC3339Nano, capability.ObservedAt)
	expires, _ := time.Parse(time.RFC3339Nano, capability.ExpiresAt)
	if issued.Before(observed) || !issued.Before(expires) {
		return ExactRoute{}, fmt.Errorf("%w: capability snapshot is stale at admission", ErrInvalidContract)
	}
	if err := validateExactRoute(requested); err != nil {
		return ExactRoute{}, err
	}
	var effective ExactRoute
	switch decision {
	case RouteInherit:
		if parent == nil {
			return ExactRoute{}, fmt.Errorf("%w: inherited route lacks parent", ErrInvalidContract)
		}
		if err := validateExactRoute(*parent); err != nil {
			return ExactRoute{}, fmt.Errorf("%w: invalid parent route: %v", ErrInvalidContract, err)
		}
		if !routeEqual(requested, *parent) {
			return ExactRoute{}, fmt.Errorf("%w: inherited route changed the exact tuple", ErrInvalidContract)
		}
		if refinementAuthorized || refinementReason != "" {
			return ExactRoute{}, fmt.Errorf("%w: inherited route cannot carry refinement authority", ErrInvalidContract)
		}
		effective = *parent
	case RouteRefine:
		if parent == nil {
			return ExactRoute{}, fmt.Errorf("%w: refined route lacks parent", ErrInvalidContract)
		}
		if err := validateExactRoute(*parent); err != nil {
			return ExactRoute{}, err
		}
		if !refinementAuthorized || refinementReason == "" {
			return ExactRoute{}, fmt.Errorf("%w: route refinement is not explicitly authorized and justified", ErrInvalidContract)
		}
		effective = requested
	case RouteReject:
		return ExactRoute{}, fmt.Errorf("%w: rejected route is not launchable", ErrInvalidContract)
	default:
		return ExactRoute{}, fmt.Errorf("%w: unknown route decision %q", ErrInvalidContract, decision)
	}
	if !snapshotContainsRoute(capability, effective) {
		return ExactRoute{}, fmt.Errorf("%w: exact route %q is unavailable", ErrInvalidContract, routeKey(effective))
	}
	return effective, nil
}

func SealRoute(envelope *RouteEnvelope) error {
	if envelope == nil {
		return fmt.Errorf("%w: nil route envelope", ErrInvalidContract)
	}
	effective, err := ResolveRoute(envelope.ParentRoute, envelope.RequestedRoute, envelope.Decision, envelope.RefinementAuthorized, envelope.RefinementReason, envelope.Capability, envelope.IssuedAt)
	if err != nil {
		return err
	}
	envelope.EffectiveRoute = effective
	envelope.OwnershipClaimIDs = sortedUnique(envelope.OwnershipClaimIDs)
	envelope.Evidence.RequiredChecks = sortedUnique(envelope.Evidence.RequiredChecks)
	envelope.Evidence.RequiredArtifacts = sortedUnique(envelope.Evidence.RequiredArtifacts)
	envelope.Digest = ""
	digest, err := digestWithoutField(*envelope, "digest")
	if err != nil {
		return err
	}
	envelope.Digest = digest
	return ValidateRoute(*envelope)
}

func ValidateRoute(envelope RouteEnvelope) error {
	if envelope.APIVersion != RouteAPIVersion {
		return fmt.Errorf("%w: route apiVersion %q", ErrInvalidContractVer, envelope.APIVersion)
	}
	for name, value := range map[string]string{
		"routeId": envelope.RouteID, "goalId": envelope.GoalID, "assignmentId": envelope.AssignmentID,
		"generationId": envelope.GenerationID, "dispatchId": envelope.DispatchID,
		"sourceHarness": envelope.SourceHarness, "targetHarness": envelope.TargetHarness,
		"canonicalRoleId": envelope.CanonicalRoleID, "budgetReservationId": envelope.BudgetReservationID,
	} {
		if err := ValidateIdentifier(value); err != nil {
			return fmt.Errorf("%w: %s: %v", ErrInvalidContract, name, err)
		}
	}
	if envelope.ParentDispatchID != "" {
		if err := ValidateIdentifier(envelope.ParentDispatchID); err != nil {
			return err
		}
		if envelope.ParentDispatchID == envelope.DispatchID {
			return fmt.Errorf("%w: dispatch cannot parent itself", ErrInvalidContract)
		}
	}
	if envelope.SourceHarness == envelope.TargetHarness && envelope.Decision == RouteRefine {
		return fmt.Errorf("%w: same-harness route cannot masquerade as a foreign refinement", ErrInvalidContract)
	}
	for _, digest := range []string{envelope.RoleDigest, envelope.AuthorityDigest, envelope.SelectionDigest, envelope.RepositoryDigest} {
		if err := ValidateDigest(digest); err != nil {
			return err
		}
	}
	if envelope.OwnershipClaimIDs == nil || envelope.Evidence.RequiredChecks == nil || envelope.Evidence.RequiredArtifacts == nil {
		return fmt.Errorf("%w: route sets must be explicit", ErrInvalidContract)
	}
	if len(envelope.OwnershipClaimIDs) > 256 || len(envelope.Evidence.RequiredChecks) > 256 || len(envelope.Evidence.RequiredArtifacts) > 256 {
		return fmt.Errorf("%w: route set exceeds bounded cardinality", ErrInvalidContract)
	}
	for _, claimID := range envelope.OwnershipClaimIDs {
		if err := ValidateIdentifier(claimID); err != nil {
			return err
		}
	}
	if envelope.OnUnavailable != RouteUnavailableReject {
		return fmt.Errorf("%w: onUnavailable must be reject", ErrInvalidContract)
	}
	issued, err := time.Parse(time.RFC3339Nano, envelope.IssuedAt)
	if err != nil || issued.IsZero() {
		return fmt.Errorf("%w: invalid route issuedAt", ErrInvalidContract)
	}
	expires, err := time.Parse(time.RFC3339Nano, envelope.ExpiresAt)
	if err != nil || !expires.After(issued) {
		return fmt.Errorf("%w: route expiresAt must follow issuedAt", ErrInvalidContract)
	}
	effective, err := ResolveRoute(envelope.ParentRoute, envelope.RequestedRoute, envelope.Decision, envelope.RefinementAuthorized, envelope.RefinementReason, envelope.Capability, envelope.IssuedAt)
	if err != nil {
		return err
	}
	if !routeEqual(effective, envelope.EffectiveRoute) {
		return fmt.Errorf("%w: effective route does not match decision", ErrInvalidContract)
	}
	if err := ValidateDigest(envelope.Digest); err != nil {
		return err
	}
	expected, err := digestWithoutField(envelope, "digest")
	if err != nil {
		return err
	}
	if envelope.Digest != expected {
		return fmt.Errorf("%w: route digest mismatch", ErrInvalidDigest)
	}
	return nil
}

func DecodeRoute(raw []byte) (RouteEnvelope, error) {
	var envelope RouteEnvelope
	if err := DecodeStrict(raw, &envelope); err != nil {
		return RouteEnvelope{}, err
	}
	if err := ValidateRoute(envelope); err != nil {
		return RouteEnvelope{}, err
	}
	return envelope, nil
}

func validateExactRoute(route ExactRoute) error {
	for name, value := range map[string]string{"provider": route.Provider, "family": route.Family, "model": route.Model, "effort": route.Effort} {
		if err := ValidateIdentifier(value); err != nil {
			return fmt.Errorf("%w: route %s: %v", ErrInvalidContract, name, err)
		}
	}
	return nil
}

func snapshotContainsRoute(snapshot CapabilitySnapshot, route ExactRoute) bool {
	for _, available := range snapshot.Routes {
		if routeEqual(available, route) {
			return true
		}
	}
	return false
}

func routeEqual(left, right ExactRoute) bool {
	return left.Provider == right.Provider && left.Family == right.Family && left.Model == right.Model && left.Effort == right.Effort
}

func routeKey(route ExactRoute) string {
	return route.Provider + "/" + route.Family + "/" + route.Model + "@" + route.Effort
}
