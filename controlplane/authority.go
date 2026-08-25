package controlplane

import (
	"fmt"
	"path"
	"sort"
	"strings"
)

const AuthorityAPIVersion = "anvil.authority/v1"

// CapabilityMode is the coarse sandbox ceiling. Fine-grained authority is
// represented by AuthorityGrant and can only narrow this ceiling.
type CapabilityMode string

const (
	CapabilityOrchestration CapabilityMode = "orchestration-only"
	CapabilityReadOnly      CapabilityMode = "read-only"
	CapabilityWorkspace     CapabilityMode = "workspace-write"
	CapabilityFactory       CapabilityMode = "factory-write"
)

// RouteConstraint restricts the exact route tuple available to a dispatch.
// Every slice is a closed allow-set; an empty slice allows nothing.
type RouteConstraint struct {
	Providers []string `json:"providers"`
	Families  []string `json:"families"`
	Models    []string `json:"models"`
	Efforts   []string `json:"efforts"`
}

// BudgetLimit is an aggregate ceiling inherited by every child dispatch.
type BudgetLimit struct {
	MaxDelegates       int   `json:"maxDelegates"`
	MaxWriters         int   `json:"maxWriters"`
	MaxTokens          int64 `json:"maxTokens"`
	MaxDurationSeconds int64 `json:"maxDurationSeconds"`
}

// EvidenceRequirement is part of authority: a child cannot discard proof
// obligations imposed by its parent.
type EvidenceRequirement struct {
	RequiredChecks          []string `json:"requiredChecks"`
	RequiredArtifacts       []string `json:"requiredArtifacts"`
	IndependentVerification bool     `json:"independentVerification"`
}

// AuthorityGrant is a closed, composable grant. Nil set dimensions are
// invalid because nil would make "missing" indistinguishable from "none".
type AuthorityGrant struct {
	ToolAllow          []string            `json:"toolAllow"`
	ToolDeny           []string            `json:"toolDeny"`
	FilesystemRead     []string            `json:"filesystemRead"`
	FilesystemWrite    []string            `json:"filesystemWrite"`
	Network            bool                `json:"network"`
	Process            bool                `json:"process"`
	InvocableRoleKinds []string            `json:"invocableRoleKinds"`
	InvocableRoleIDs   []string            `json:"invocableRoleIds"`
	Routes             RouteConstraint     `json:"routes"`
	Budget             BudgetLimit         `json:"budget"`
	Evidence           EvidenceRequirement `json:"evidence"`
}

// AuthorityEnvelope binds the four inputs and their exact effective
// intersection to one role and lane.
type AuthorityEnvelope struct {
	APIVersion     string         `json:"apiVersion"`
	GrantID        string         `json:"grantId"`
	ParentGrantID  string         `json:"parentGrantId"`
	RoleID         string         `json:"roleId"`
	RoleDigest     string         `json:"roleDigest"`
	Lane           string         `json:"lane"`
	CapabilityMode CapabilityMode `json:"capabilityMode"`
	ParentGrant    AuthorityGrant `json:"parentGrant"`
	RoleCeiling    AuthorityGrant `json:"roleCeiling"`
	RequestedGrant AuthorityGrant `json:"requestedGrant"`
	ObservedGrant  AuthorityGrant `json:"observedGrant"`
	EffectiveGrant AuthorityGrant `json:"effectiveGrant"`
	DenialReasons  []string       `json:"denialReasons"`
	IssuedAt       string         `json:"issuedAt"`
	Digest         string         `json:"digest"`
}

// IntersectAuthority computes the exact four-way intersection. It rejects a
// missing or malformed dimension instead of interpreting it as unbounded.
func IntersectAuthority(parent, roleCeiling, requested, observed AuthorityGrant) (AuthorityGrant, error) {
	inputs := []struct {
		name  string
		grant AuthorityGrant
	}{
		{"parent", parent},
		{"role ceiling", roleCeiling},
		{"requested", requested},
		{"observed", observed},
	}
	for _, input := range inputs {
		if err := validateAuthorityGrant(input.grant); err != nil {
			return AuthorityGrant{}, fmt.Errorf("%w: %s grant: %v", ErrInvalidContract, input.name, err)
		}
	}

	grants := []AuthorityGrant{parent, roleCeiling, requested, observed}
	effective := AuthorityGrant{
		ToolAllow:          intersectMany(grants, func(grant AuthorityGrant) []string { return grant.ToolAllow }),
		ToolDeny:           unionMany(grants, func(grant AuthorityGrant) []string { return grant.ToolDeny }),
		FilesystemRead:     intersectScopeMany(grants, func(grant AuthorityGrant) []string { return grant.FilesystemRead }),
		FilesystemWrite:    intersectScopeMany(grants, func(grant AuthorityGrant) []string { return grant.FilesystemWrite }),
		Network:            parent.Network && roleCeiling.Network && requested.Network && observed.Network,
		Process:            parent.Process && roleCeiling.Process && requested.Process && observed.Process,
		InvocableRoleKinds: intersectMany(grants, func(grant AuthorityGrant) []string { return grant.InvocableRoleKinds }),
		InvocableRoleIDs:   intersectWildcardMany(grants, func(grant AuthorityGrant) []string { return grant.InvocableRoleIDs }),
		Routes: RouteConstraint{
			Providers: intersectWildcardMany(grants, func(grant AuthorityGrant) []string { return grant.Routes.Providers }),
			Families:  intersectWildcardMany(grants, func(grant AuthorityGrant) []string { return grant.Routes.Families }),
			Models:    intersectWildcardMany(grants, func(grant AuthorityGrant) []string { return grant.Routes.Models }),
			Efforts:   intersectWildcardMany(grants, func(grant AuthorityGrant) []string { return grant.Routes.Efforts }),
		},
		Budget: BudgetLimit{
			MaxDelegates:       minInt(parent.Budget.MaxDelegates, roleCeiling.Budget.MaxDelegates, requested.Budget.MaxDelegates, observed.Budget.MaxDelegates),
			MaxWriters:         minInt(parent.Budget.MaxWriters, roleCeiling.Budget.MaxWriters, requested.Budget.MaxWriters, observed.Budget.MaxWriters),
			MaxTokens:          minInt64(parent.Budget.MaxTokens, roleCeiling.Budget.MaxTokens, requested.Budget.MaxTokens, observed.Budget.MaxTokens),
			MaxDurationSeconds: minInt64(parent.Budget.MaxDurationSeconds, roleCeiling.Budget.MaxDurationSeconds, requested.Budget.MaxDurationSeconds, observed.Budget.MaxDurationSeconds),
		},
		Evidence: EvidenceRequirement{
			RequiredChecks:          unionMany(grants, func(grant AuthorityGrant) []string { return grant.Evidence.RequiredChecks }),
			RequiredArtifacts:       unionMany(grants, func(grant AuthorityGrant) []string { return grant.Evidence.RequiredArtifacts }),
			IndependentVerification: parent.Evidence.IndependentVerification || roleCeiling.Evidence.IndependentVerification || requested.Evidence.IndependentVerification || observed.Evidence.IndependentVerification,
		},
	}
	effective.ToolAllow = difference(effective.ToolAllow, effective.ToolDeny)
	return effective, nil
}

// ValidateAuthority verifies identity, intersection, denial accounting, time,
// and the self digest. Expansion attempts must be represented as denials.
func ValidateAuthority(envelope AuthorityEnvelope) error {
	if envelope.APIVersion != AuthorityAPIVersion {
		return fmt.Errorf("%w: authority apiVersion %q", ErrInvalidContractVer, envelope.APIVersion)
	}
	for name, value := range map[string]string{
		"grantId": envelope.GrantID, "roleId": envelope.RoleID, "lane": envelope.Lane,
	} {
		if err := ValidateIdentifier(value); err != nil {
			return fmt.Errorf("%w: %s: %v", ErrInvalidContract, name, err)
		}
	}
	if envelope.ParentGrantID != "" {
		if err := ValidateIdentifier(envelope.ParentGrantID); err != nil {
			return err
		}
	}
	if err := ValidateDigest(envelope.RoleDigest); err != nil {
		return fmt.Errorf("%w: roleDigest: %v", ErrInvalidContract, err)
	}
	if !validCapabilityMode(envelope.CapabilityMode) {
		return fmt.Errorf("%w: invalid capabilityMode %q", ErrInvalidContract, envelope.CapabilityMode)
	}
	if err := ValidateTimestamp(envelope.IssuedAt); err != nil {
		return err
	}
	expected, err := IntersectAuthority(envelope.ParentGrant, envelope.RoleCeiling, envelope.RequestedGrant, envelope.ObservedGrant)
	if err != nil {
		return err
	}
	normalizeAuthorityGrant(&envelope.EffectiveGrant)
	if !authorityGrantEqual(expected, envelope.EffectiveGrant) {
		return fmt.Errorf("%w: effective grant is not the exact four-way intersection", ErrInvalidContract)
	}
	expansions := requestedExpansions(envelope.RequestedGrant, envelope.ParentGrant, envelope.RoleCeiling, envelope.ObservedGrant)
	if len(expansions) > 0 && len(envelope.DenialReasons) == 0 {
		return fmt.Errorf("%w: authority expansion lacks denial reasons", ErrInvalidContract)
	}
	if len(expansions) == 0 && len(envelope.DenialReasons) > 0 {
		return fmt.Errorf("%w: denial reasons present without an expansion", ErrInvalidContract)
	}
	if err := ValidateDigest(envelope.Digest); err != nil {
		return err
	}
	expectedDigest, err := digestWithoutField(envelope, "digest")
	if err != nil {
		return err
	}
	if envelope.Digest != expectedDigest {
		return fmt.Errorf("%w: authority digest mismatch", ErrInvalidDigest)
	}
	return nil
}

// SealAuthority normalizes set fields, computes the effective grant and
// denial reasons, and writes the canonical digest.
func SealAuthority(envelope *AuthorityEnvelope) error {
	if envelope == nil {
		return fmt.Errorf("%w: nil authority envelope", ErrInvalidContract)
	}
	effective, err := IntersectAuthority(envelope.ParentGrant, envelope.RoleCeiling, envelope.RequestedGrant, envelope.ObservedGrant)
	if err != nil {
		return err
	}
	envelope.EffectiveGrant = effective
	envelope.DenialReasons = requestedExpansions(envelope.RequestedGrant, envelope.ParentGrant, envelope.RoleCeiling, envelope.ObservedGrant)
	sort.Strings(envelope.DenialReasons)
	envelope.Digest = ""
	digest, err := digestWithoutField(*envelope, "digest")
	if err != nil {
		return err
	}
	envelope.Digest = digest
	return nil
}

func validateAuthorityGrant(grant AuthorityGrant) error {
	setDimensions := []struct {
		name   string
		values []string
	}{
		{"toolAllow", grant.ToolAllow}, {"toolDeny", grant.ToolDeny},
		{"filesystemRead", grant.FilesystemRead}, {"filesystemWrite", grant.FilesystemWrite},
		{"invocableRoleKinds", grant.InvocableRoleKinds}, {"invocableRoleIds", grant.InvocableRoleIDs},
		{"routes.providers", grant.Routes.Providers}, {"routes.families", grant.Routes.Families},
		{"routes.models", grant.Routes.Models}, {"routes.efforts", grant.Routes.Efforts},
		{"evidence.requiredChecks", grant.Evidence.RequiredChecks},
		{"evidence.requiredArtifacts", grant.Evidence.RequiredArtifacts},
	}
	for _, dimension := range setDimensions {
		if dimension.values == nil {
			return fmt.Errorf("%s is missing; use an explicit empty set for none", dimension.name)
		}
		if len(dimension.values) > 256 {
			return fmt.Errorf("%s exceeds 256 entries", dimension.name)
		}
		seen := make(map[string]struct{}, len(dimension.values))
		for _, value := range dimension.values {
			if value == "" {
				return fmt.Errorf("%s contains an empty value", dimension.name)
			}
			if _, duplicate := seen[value]; duplicate {
				return fmt.Errorf("%s contains duplicate %q", dimension.name, value)
			}
			seen[value] = struct{}{}
		}
	}
	for _, scope := range append(append([]string{}, grant.FilesystemRead...), grant.FilesystemWrite...) {
		if !validRelativeScope(scope) {
			return fmt.Errorf("invalid filesystem scope %q", scope)
		}
	}
	if grant.Budget.MaxDelegates < 0 || grant.Budget.MaxWriters < 0 || grant.Budget.MaxTokens < 0 || grant.Budget.MaxDurationSeconds < 0 {
		return fmt.Errorf("budget limits cannot be negative")
	}
	return nil
}

func normalizeAuthorityGrant(grant *AuthorityGrant) {
	if grant == nil {
		return
	}
	grant.ToolAllow = sortedUnique(grant.ToolAllow)
	grant.ToolDeny = sortedUnique(grant.ToolDeny)
	grant.FilesystemRead = sortedUnique(grant.FilesystemRead)
	grant.FilesystemWrite = sortedUnique(grant.FilesystemWrite)
	grant.InvocableRoleKinds = sortedUnique(grant.InvocableRoleKinds)
	grant.InvocableRoleIDs = sortedUnique(grant.InvocableRoleIDs)
	grant.Routes.Providers = sortedUnique(grant.Routes.Providers)
	grant.Routes.Families = sortedUnique(grant.Routes.Families)
	grant.Routes.Models = sortedUnique(grant.Routes.Models)
	grant.Routes.Efforts = sortedUnique(grant.Routes.Efforts)
	grant.Evidence.RequiredChecks = sortedUnique(grant.Evidence.RequiredChecks)
	grant.Evidence.RequiredArtifacts = sortedUnique(grant.Evidence.RequiredArtifacts)
}

func authorityGrantEqual(left, right AuthorityGrant) bool {
	normalizeAuthorityGrant(&left)
	normalizeAuthorityGrant(&right)
	leftJSON, _ := EncodeCanonical(left)
	rightJSON, _ := EncodeCanonical(right)
	return string(leftJSON) == string(rightJSON)
}

func requestedExpansions(requested AuthorityGrant, ceilings ...AuthorityGrant) []string {
	reasons := make([]string, 0)
	for _, ceiling := range ceilings {
		checks := []struct {
			name      string
			requested []string
			ceiling   []string
			allows    func(string, []string) bool
		}{
			{"tools", requested.ToolAllow, ceiling.ToolAllow, exactSetAllows},
			{"filesystem.read", requested.FilesystemRead, ceiling.FilesystemRead, scopeSetAllows},
			{"filesystem.write", requested.FilesystemWrite, ceiling.FilesystemWrite, scopeSetAllows},
			{"roles.kinds", requested.InvocableRoleKinds, ceiling.InvocableRoleKinds, exactSetAllows},
			{"roles.ids", requested.InvocableRoleIDs, ceiling.InvocableRoleIDs, wildcardSetAllows},
			{"routes.providers", requested.Routes.Providers, ceiling.Routes.Providers, wildcardSetAllows},
			{"routes.families", requested.Routes.Families, ceiling.Routes.Families, wildcardSetAllows},
			{"routes.models", requested.Routes.Models, ceiling.Routes.Models, wildcardSetAllows},
			{"routes.efforts", requested.Routes.Efforts, ceiling.Routes.Efforts, wildcardSetAllows},
		}
		for _, check := range checks {
			for _, value := range sortedUnique(check.requested) {
				if !check.allows(value, check.ceiling) {
					reasons = append(reasons, check.name+":"+value)
				}
			}
		}
		if requested.Network && !ceiling.Network {
			reasons = append(reasons, "network")
		}
		if requested.Process && !ceiling.Process {
			reasons = append(reasons, "process")
		}
		if requested.Budget.MaxDelegates > ceiling.Budget.MaxDelegates || requested.Budget.MaxWriters > ceiling.Budget.MaxWriters ||
			requested.Budget.MaxTokens > ceiling.Budget.MaxTokens || requested.Budget.MaxDurationSeconds > ceiling.Budget.MaxDurationSeconds {
			reasons = append(reasons, "budget")
		}
	}
	return sortedUnique(reasons)
}

func validCapabilityMode(mode CapabilityMode) bool {
	switch mode {
	case CapabilityOrchestration, CapabilityReadOnly, CapabilityWorkspace, CapabilityFactory:
		return true
	default:
		return false
	}
}

func validRelativeScope(scope string) bool {
	if scope == "" || strings.ContainsRune(scope, '\\') || strings.HasPrefix(scope, "/") {
		return false
	}
	clean := path.Clean(scope)
	return clean == scope && clean != ".." && !strings.HasPrefix(clean, "../")
}

func intersectMany(grants []AuthorityGrant, getter func(AuthorityGrant) []string) []string {
	if len(grants) == 0 {
		return []string{}
	}
	result := sortedUnique(getter(grants[0]))
	for _, grant := range grants[1:] {
		result = intersection(result, getter(grant))
	}
	return result
}

func intersectWildcardMany(grants []AuthorityGrant, getter func(AuthorityGrant) []string) []string {
	if len(grants) == 0 {
		return []string{}
	}
	result := sortedUnique(getter(grants[0]))
	for _, grant := range grants[1:] {
		result = intersectWildcard(result, getter(grant))
	}
	return result
}

func intersectWildcard(left, right []string) []string {
	leftAll, rightAll := containsValue(left, "*"), containsValue(right, "*")
	switch {
	case leftAll && rightAll:
		return []string{"*"}
	case leftAll:
		return sortedUnique(right)
	case rightAll:
		return sortedUnique(left)
	default:
		return intersection(left, right)
	}
}

func intersectScopeMany(grants []AuthorityGrant, getter func(AuthorityGrant) []string) []string {
	if len(grants) == 0 {
		return []string{}
	}
	result := sortedUnique(getter(grants[0]))
	for _, grant := range grants[1:] {
		result = intersectScopes(result, getter(grant))
	}
	return result
}

func intersectScopes(left, right []string) []string {
	result := make([]string, 0)
	for _, a := range left {
		for _, b := range right {
			switch {
			case scopeContains(a, b):
				result = append(result, b)
			case scopeContains(b, a):
				result = append(result, a)
			}
		}
	}
	return sortedUnique(result)
}

func unionMany(grants []AuthorityGrant, getter func(AuthorityGrant) []string) []string {
	var result []string
	for _, grant := range grants {
		result = append(result, getter(grant)...)
	}
	return sortedUnique(result)
}

func intersection(left, right []string) []string {
	rightSet := make(map[string]struct{}, len(right))
	for _, value := range right {
		rightSet[value] = struct{}{}
	}
	result := make([]string, 0)
	for _, value := range sortedUnique(left) {
		if _, ok := rightSet[value]; ok {
			result = append(result, value)
		}
	}
	return result
}

func difference(left, right []string) []string {
	rightSet := make(map[string]struct{}, len(right))
	for _, value := range right {
		rightSet[value] = struct{}{}
	}
	result := make([]string, 0)
	for _, value := range sortedUnique(left) {
		if _, ok := rightSet[value]; !ok {
			result = append(result, value)
		}
	}
	return result
}

func exactSetAllows(value string, allowed []string) bool {
	return containsValue(allowed, value)
}

func wildcardSetAllows(value string, allowed []string) bool {
	return containsValue(allowed, "*") || containsValue(allowed, value)
}

func scopeSetAllows(value string, allowed []string) bool {
	for _, scope := range allowed {
		if scopeContains(scope, value) {
			return true
		}
	}
	return false
}

func scopeContains(parent, child string) bool {
	return parent == "." || parent == child || strings.HasPrefix(child, parent+"/")
}

func containsValue(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func sortedUnique(values []string) []string {
	if values == nil {
		return nil
	}
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func minInt(values ...int) int {
	result := values[0]
	for _, value := range values[1:] {
		if value < result {
			result = value
		}
	}
	return result
}

func minInt64(values ...int64) int64 {
	result := values[0]
	for _, value := range values[1:] {
		if value < result {
			result = value
		}
	}
	return result
}
