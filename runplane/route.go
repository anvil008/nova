package runplane

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
)

const maxBriefBytes = 64 << 10

var goalIDPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)

type admittedRoute struct {
	Route           Route
	Presentation    *codingfleet.AgentPresentation
	Binding         roleBinding
	Capability      Capability
	Definition      string
	DefinitionBytes []byte
	RoleDigest      string
	Prompt          string
	PromptDigest    string
}

func admitRoute(request StartRequest, capability Capability, roots DefinitionRoots) (admittedRoute, error) {
	route := request.Route
	if route.Limits == (codingfleet.AgentHandoffLimits{}) {
		route.Limits = codingfleet.AgentHandoffLimits{MaxMessages: 100, MaxDurationSeconds: 3600, MaxChildren: 4}
	}
	if route.SourceHarness != HarnessCodex && route.SourceHarness != HarnessClaude && route.SourceHarness != HarnessAGY {
		return admittedRoute{}, fmt.Errorf("unsupported source harness %q", route.SourceHarness)
	}
	if route.TargetHarness != HarnessCodex && route.TargetHarness != HarnessClaude && route.TargetHarness != HarnessAGY {
		return admittedRoute{}, fmt.Errorf("unsupported target harness %q", route.TargetHarness)
	}
	if route.SourceHarness == route.TargetHarness {
		return admittedRoute{}, fmt.Errorf("source and target harness must differ for a foreign job")
	}
	if route.Provider == "" || route.Family == "" {
		return admittedRoute{}, fmt.Errorf("provider and family must both be explicit")
	}
	if !goalIDPattern.MatchString(route.Provider) || !goalIDPattern.MatchString(route.Family) {
		return admittedRoute{}, fmt.Errorf("provider and family must be explicit bounded identifiers")
	}
	sourceProvider, _ := harnessProviderFamily(route.SourceHarness)
	if route.Provider == sourceProvider {
		return admittedRoute{}, fmt.Errorf("foreign route provider %q must differ from source harness provider", route.Provider)
	}
	targetProvider, targetFamily := harnessProviderFamily(route.TargetHarness)
	if route.Provider != targetProvider {
		return admittedRoute{}, fmt.Errorf("provider %q does not match target harness provider %q", route.Provider, targetProvider)
	}
	if route.Family != targetFamily {
		return admittedRoute{}, fmt.Errorf("family %q does not match target harness family %q", route.Family, targetFamily)
	}
	if capability.Harness != route.TargetHarness || !capability.Available {
		return admittedRoute{}, fmt.Errorf("target harness %q is unavailable: %s", route.TargetHarness, capability.Error)
	}
	exactRoute := controlplane.ExactRoute{Provider: route.Provider, Family: route.Family, Model: route.ExactModel, Effort: route.Effort}
	if !capabilityContainsExactRoute(capability, exactRoute) {
		return admittedRoute{}, fmt.Errorf("exact provider/family/model/effort route pair %q/%q/%q/%q is not in the discovered %s allowlist", route.Provider, route.Family, route.ExactModel, route.Effort, route.TargetHarness)
	}
	if request.Presentation != nil {
		if err := request.Presentation.Validate(); err != nil {
			return admittedRoute{}, err
		}
		if request.Presentation.Model != route.ExactModel {
			return admittedRoute{}, fmt.Errorf("presentation model %q must equal the admitted exact model %q", request.Presentation.Model, route.ExactModel)
		}
	}
	if !goalIDPattern.MatchString(route.ParentGoalID) {
		return admittedRoute{}, fmt.Errorf("parent goal ID must be a bounded stable identifier")
	}
	if route.DispatchID != "" && !goalIDPattern.MatchString(route.DispatchID) {
		return admittedRoute{}, fmt.Errorf("run ID must be a bounded stable identifier")
	}
	if route.Limits.MaxMessages < 1 || route.Limits.MaxDurationSeconds < 1 || route.Limits.MaxChildren < 0 {
		return admittedRoute{}, fmt.Errorf("handoff limits are invalid")
	}
	binding, err := loadRoleBinding(route.CanonicalRoleID)
	if err != nil {
		return admittedRoute{}, err
	}
	if binding.Mode != route.CapabilityMode {
		return admittedRoute{}, fmt.Errorf("route capability mode %q conflicts with canonical role mode %q", route.CapabilityMode, binding.Mode)
	}
	if !contains(capability.Roles, binding.NativeName) {
		return admittedRoute{}, fmt.Errorf("native role %q is not in the discovered %s allowlist", binding.NativeName, route.TargetHarness)
	}
	definition, err := roots.verifyExactDefinition(route.TargetHarness, binding)
	if err != nil {
		return admittedRoute{}, err
	}
	route.RepositoryRoot, err = validateRepositoryRoot(route.RepositoryRoot)
	if err != nil {
		return admittedRoute{}, err
	}
	route.FileOwnership, err = normalizeOwnership(route.RepositoryRoot, route.FileOwnership)
	if err != nil {
		return admittedRoute{}, err
	}
	if route.CapabilityMode == ModeWorkspaceWrite && len(route.FileOwnership) == 0 {
		return admittedRoute{}, fmt.Errorf("workspace-write routes require explicit file ownership")
	}
	if request.ControlPlane != nil {
		if err := validateControlPlaneAdmission(*request.ControlPlane, route, capability, binding); err != nil {
			return admittedRoute{}, fmt.Errorf("control-plane admission: %w", err)
		}
	}
	if len(request.Brief) == 0 || len(request.Brief) > maxBriefBytes {
		return admittedRoute{}, fmt.Errorf("brief must contain 1..%d bytes", maxBriefBytes)
	}
	if strings.IndexByte(request.Brief, 0) >= 0 {
		return admittedRoute{}, fmt.Errorf("brief must not contain NUL bytes")
	}
	if len(route.Evidence.RequiredChecks) > 32 || len(route.Evidence.RequiredArtifacts) > 32 {
		return admittedRoute{}, fmt.Errorf("evidence contract exceeds 32 checks or artifacts")
	}
	if request.ControlPlane == nil && len(route.Evidence.RequiredArtifacts) != 0 {
		return admittedRoute{}, fmt.Errorf("compact agent handoff cannot satisfy required artifacts")
	}
	prompt, err := composeBrief(route, request.Brief)
	if err != nil {
		return admittedRoute{}, err
	}
	digest := sha256.Sum256([]byte(prompt))
	definitionBytes, err := os.ReadFile(definition)
	if err != nil {
		return admittedRoute{}, fmt.Errorf("read verified role definition: %w", err)
	}
	return admittedRoute{Route: route, Presentation: request.Presentation, Binding: binding, Capability: capability, Definition: definition, DefinitionBytes: definitionBytes, RoleDigest: binding.Digest, Prompt: prompt, PromptDigest: hex.EncodeToString(digest[:])}, nil
}

func validateRepositoryRoot(root string) (string, error) {
	if root == "" || !filepath.IsAbs(root) {
		return "", fmt.Errorf("repository root %q must be absolute", root)
	}
	resolved, err := filepath.EvalSymlinks(filepath.Clean(root))
	if err != nil {
		return "", fmt.Errorf("resolve repository root %q: %w", root, err)
	}
	info, err := os.Stat(resolved)
	if err != nil || !info.IsDir() {
		return "", fmt.Errorf("repository root %q must be an existing directory", root)
	}
	if _, errGit := os.Stat(filepath.Join(resolved, ".git")); errGit != nil {
		if _, errJJ := os.Stat(filepath.Join(resolved, ".jj")); errJJ != nil {
			return "", fmt.Errorf("repository root %q is not a Git or Jujutsu working copy", resolved)
		}
	}
	return resolved, nil
}

func normalizeOwnership(root string, values []string) ([]string, error) {
	set := map[string]struct{}{}
	for _, value := range values {
		if value == "" || filepath.IsAbs(value) || strings.ContainsRune(value, 0) {
			return nil, fmt.Errorf("file ownership %q must be a non-empty repository-relative path", value)
		}
		clean := filepath.ToSlash(filepath.Clean(value))
		if clean == "." || clean == ".." || strings.HasPrefix(clean, "../") {
			return nil, fmt.Errorf("file ownership %q escapes or owns the repository root", value)
		}
		resolved, err := resolveOwnershipPath(root, clean)
		if err != nil {
			return nil, err
		}
		set[resolved] = struct{}{}
	}
	out := sortedKeys(set)
	return out, nil
}

func resolveOwnershipPath(root, relative string) (string, error) {
	rootResolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", fmt.Errorf("resolve repository root for ownership: %w", err)
	}
	probe := filepath.Join(rootResolved, filepath.FromSlash(relative))
	var suffix []string
	for {
		if _, err := os.Lstat(probe); err == nil {
			break
		} else if !os.IsNotExist(err) {
			return "", fmt.Errorf("inspect ownership path %q: %w", relative, err)
		}
		parent := filepath.Dir(probe)
		if parent == probe {
			return "", fmt.Errorf("ownership path %q has no existing repository ancestor", relative)
		}
		suffix = append([]string{filepath.Base(probe)}, suffix...)
		probe = parent
	}
	ancestor, err := filepath.EvalSymlinks(probe)
	if err != nil {
		return "", fmt.Errorf("resolve ownership path %q: %w", relative, err)
	}
	canonical := filepath.Join(append([]string{ancestor}, suffix...)...)
	relativeCanonical, err := filepath.Rel(rootResolved, canonical)
	if err != nil || relativeCanonical == ".." || strings.HasPrefix(relativeCanonical, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("ownership path %q resolves outside repository root", relative)
	}
	return filepath.ToSlash(relativeCanonical), nil
}

func ownershipConflicts(left, right []string) bool {
	for _, a := range left {
		for _, b := range right {
			if a == b || strings.HasPrefix(a, b+"/") || strings.HasPrefix(b, a+"/") {
				return true
			}
		}
	}
	return false
}

func composeBrief(route Route, brief string) (string, error) {
	context := struct {
		RunID          string                         `json:"runId"`
		ParentRunID    string                         `json:"parentRunId,omitempty"`
		ParentGoalID   string                         `json:"parentGoalId"`
		CanonicalRole  string                         `json:"canonicalRole"`
		Provider       string                         `json:"provider"`
		Model          string                         `json:"model"`
		Effort         string                         `json:"effort"`
		CapabilityMode CapabilityMode                 `json:"capabilityMode"`
		FileOwnership  []string                       `json:"fileOwnership"`
		Limits         codingfleet.AgentHandoffLimits `json:"limits"`
		Evidence       EvidenceContract               `json:"evidenceContract"`
	}{route.DispatchID, route.ParentDispatchID, route.ParentGoalID, route.CanonicalRoleID, route.Provider, route.ExactModel, route.Effort, route.CapabilityMode, route.FileOwnership, route.Limits, route.Evidence}
	encoded, err := json.Marshal(context)
	if err != nil {
		return "", fmt.Errorf("encode bounded route context: %w", err)
	}
	return "Supervised foreign-harness assignment. Obey the loaded canonical role definition exactly. Do not launch another orchestrator. Return exactly one anvil.agent-handoff/v1 record using the route context identifiers and limits.\nRoute context: " + string(encoded) + "\n\nBounded brief:\n" + brief, nil
}

func contains(values []string, wanted string) bool {
	index := sort.SearchStrings(values, wanted)
	return index < len(values) && values[index] == wanted
}

func containsModelEffort(values []ModelEffort, model, effort string) bool {
	for _, value := range values {
		if value.Model == model && value.Effort == effort && value.Reference != "alias" {
			return true
		}
	}
	return false
}

func validateControlPlaneAdmission(admission ControlPlaneAdmission, route Route, capability Capability, binding roleBinding) error {
	if err := controlplane.ValidateAuthority(admission.Authority); err != nil {
		return err
	}
	document, err := codingfleet.Load()
	if err != nil {
		return err
	}
	if err := codingfleet.ValidateSelection(document, admission.Selection); err != nil {
		return err
	}
	if err := controlplane.ValidateRoute(admission.Route); err != nil {
		return err
	}
	if err := controlplane.ValidateGoal(admission.Goal); err != nil {
		return err
	}
	if err := controlplane.ValidateAssignment(admission.Assignment); err != nil {
		return err
	}
	if err := controlplane.ValidateGeneration(admission.Generation); err != nil {
		return err
	}
	if err := controlplane.ValidateDispatch(admission.Dispatch); err != nil {
		return err
	}
	if err := controlplane.ValidateBudgetReservation(admission.Budget, admission.Authority.EffectiveGrant.Budget); err != nil {
		return err
	}
	if admission.Ownership == nil {
		return fmt.Errorf("ownership claims must be explicit")
	}
	for _, claim := range admission.Ownership {
		if err := controlplane.ValidateOwnership(claim); err != nil {
			return err
		}
	}

	if admission.Authority.RoleID != binding.CanonicalID || admission.Authority.RoleDigest != binding.Digest {
		return fmt.Errorf("authority role identity or digest does not match canonical catalog")
	}
	wantMode, err := controlplaneCapabilityMode(route.CapabilityMode, binding.Authority.CapabilityMode)
	if err != nil {
		return err
	}
	if admission.Authority.CapabilityMode != wantMode {
		return fmt.Errorf("authority capability mode does not match route")
	}
	if !canonicalEqual(admission.Authority.RoleCeiling, binding.Authority.Grant) {
		return fmt.Errorf("authority role ceiling does not match canonical catalog")
	}
	if admission.Selection.CatalogDigest != binding.CatalogDigest || admission.Selection.RoleDigest == "" {
		return fmt.Errorf("selection catalog or workflow role digest is stale")
	}

	cpRoute := admission.Route
	if cpRoute.GoalID != route.ParentGoalID || cpRoute.AssignmentID != route.AssignmentID || cpRoute.GenerationID != route.GenerationID ||
		cpRoute.DispatchID != route.DispatchID || cpRoute.ParentDispatchID != route.ParentDispatchID || cpRoute.CanonicalRoleID != route.CanonicalRoleID {
		return fmt.Errorf("route lifecycle identity does not match compact request")
	}
	if cpRoute.SourceHarness != string(route.SourceHarness) || cpRoute.TargetHarness != string(route.TargetHarness) {
		return fmt.Errorf("route harness identity does not match compact request")
	}
	wantExact := controlplane.ExactRoute{Provider: route.Provider, Family: route.Family, Model: route.ExactModel, Effort: route.Effort}
	if cpRoute.EffectiveRoute != wantExact || cpRoute.RequestedRoute != wantExact {
		return fmt.Errorf("exact provider/family/model/effort tuple does not match compact request")
	}
	if cpRoute.RoleDigest != binding.Digest || cpRoute.AuthorityDigest != admission.Authority.Digest || cpRoute.SelectionDigest != admission.Selection.Digest || cpRoute.RepositoryDigest != route.RepositoryDigest {
		return fmt.Errorf("route evidence references do not match admission bundle")
	}
	if !capabilityContainsExactRoute(capability, wantExact) {
		return fmt.Errorf("exact route is absent from current discovered capability")
	}
	if cpRoute.Capability.HarnessID != string(route.TargetHarness) {
		return fmt.Errorf("capability snapshot harness does not match target")
	}
	observed := capability.ObservedAt
	if observed.IsZero() {
		return fmt.Errorf("current capability lacks an observation timestamp")
	}
	snapshotObserved, _ := time.Parse(time.RFC3339Nano, cpRoute.Capability.ObservedAt)
	if !snapshotObserved.Equal(observed.UTC()) {
		return fmt.Errorf("capability snapshot is not the current observation")
	}

	if admission.Goal.GoalID != route.ParentGoalID || admission.Goal.RepositoryDigest != route.RepositoryDigest ||
		admission.Assignment.AssignmentID != route.AssignmentID || admission.Assignment.GoalID != route.ParentGoalID ||
		admission.Assignment.GenerationID != route.GenerationID || admission.Assignment.RoleID != route.CanonicalRoleID ||
		admission.Generation.GoalID != route.ParentGoalID || admission.Generation.GenerationID != route.GenerationID || admission.Generation.GenerationNumber != route.GenerationNumber ||
		admission.Dispatch.DispatchID != route.DispatchID || admission.Dispatch.ParentDispatchID != route.ParentDispatchID ||
		admission.Dispatch.GoalID != route.ParentGoalID || admission.Dispatch.AssignmentID != route.AssignmentID || admission.Dispatch.GenerationID != route.GenerationID || admission.Dispatch.RoleID != route.CanonicalRoleID {
		return fmt.Errorf("goal, assignment, generation, or dispatch cross-reference mismatch")
	}
	if admission.Budget.GoalID != route.ParentGoalID || admission.Budget.GenerationID != route.GenerationID || admission.Budget.DispatchID != route.DispatchID || admission.Budget.ReservationID != cpRoute.BudgetReservationID {
		return fmt.Errorf("budget reservation cross-reference mismatch")
	}

	claimIDs := make([]string, 0, len(admission.Ownership))
	paths := make([]string, 0)
	symbols := make([]controlplane.SymbolClaim, 0)
	for _, claim := range admission.Ownership {
		if claim.GoalID != route.ParentGoalID || claim.GenerationID != route.GenerationID || claim.DispatchID != route.DispatchID {
			return fmt.Errorf("ownership claim cross-reference mismatch")
		}
		if route.CapabilityMode == ModeWorkspaceWrite && claim.Mode != controlplane.OwnershipWrite {
			return fmt.Errorf("workspace-write route requires write ownership claims")
		}
		claimIDs = append(claimIDs, claim.ClaimID)
		paths = append(paths, claim.Paths...)
		symbols = append(symbols, claim.Symbols...)
	}
	sort.Strings(claimIDs)
	sort.Strings(paths)
	sort.Slice(symbols, func(i, j int) bool {
		return symbols[i].Language+":"+symbols[i].Path+":"+symbols[i].QualifiedName < symbols[j].Language+":"+symbols[j].Path+":"+symbols[j].QualifiedName
	})
	wantPaths := explicitStrings(route.FileOwnership)
	sort.Strings(wantPaths)
	wantSymbols := explicitSymbols(route.SymbolOwnership)
	sort.Slice(wantSymbols, func(i, j int) bool {
		return wantSymbols[i].Language+":"+wantSymbols[i].Path+":"+wantSymbols[i].QualifiedName < wantSymbols[j].Language+":"+wantSymbols[j].Path+":"+wantSymbols[j].QualifiedName
	})
	if !canonicalEqual(claimIDs, cpRoute.OwnershipClaimIDs) || !canonicalEqual(paths, wantPaths) || !canonicalEqual(symbols, wantSymbols) {
		return fmt.Errorf("ownership claims do not match route ownership")
	}
	if !canonicalEqual(cpRoute.Evidence.RequiredChecks, route.Evidence.RequiredChecks) || !canonicalEqual(cpRoute.Evidence.RequiredArtifacts, route.Evidence.RequiredArtifacts) {
		return fmt.Errorf("evidence requirements do not match compact route")
	}
	return nil
}

func controlplaneCapabilityMode(routeMode CapabilityMode, catalogMode codingfleet.CapabilityMode) (controlplane.CapabilityMode, error) {
	switch catalogMode {
	case codingfleet.CapabilityReadOnly:
		if routeMode != ModeReadOnly {
			return "", fmt.Errorf("read-only catalog role has non-read-only route")
		}
		return controlplane.CapabilityReadOnly, nil
	case codingfleet.CapabilityWorkspaceWrite:
		if routeMode != ModeWorkspaceWrite {
			return "", fmt.Errorf("workspace catalog role has non-write route")
		}
		return controlplane.CapabilityWorkspace, nil
	default:
		return "", fmt.Errorf("catalog capability %q is not launchable by run plane", catalogMode)
	}
}

func capabilityContainsExactRoute(capability Capability, route controlplane.ExactRoute) bool {
	for _, pair := range capability.ModelEfforts {
		provider, family := pair.Provider, pair.Family
		if provider == "" || family == "" {
			provider, family = harnessProviderFamily(capability.Harness)
		}
		if pair.Reference != "alias" && provider == route.Provider && family == route.Family && pair.Model == route.Model && pair.Effort == route.Effort {
			return true
		}
	}
	return false
}

func harnessProviderFamily(harness Harness) (string, string) {
	switch harness {
	case HarnessCodex:
		return "openai", "gpt"
	case HarnessClaude:
		return "anthropic", "claude"
	case HarnessAGY:
		return "google", "gemini"
	default:
		return "", ""
	}
}

func canonicalEqual(left, right any) bool {
	leftJSON, leftErr := controlplane.EncodeCanonical(left)
	rightJSON, rightErr := controlplane.EncodeCanonical(right)
	return leftErr == nil && rightErr == nil && string(leftJSON) == string(rightJSON)
}
