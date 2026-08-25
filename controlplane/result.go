package controlplane

import (
	"fmt"
	"sort"
	"time"
)

const WorkflowResultAPIVersion = "anvil.workflow-result/v1"

type WorkflowDisposition string

const (
	DispositionSucceeded         WorkflowDisposition = "succeeded"
	DispositionFailed            WorkflowDisposition = "failed"
	DispositionUncertain         WorkflowDisposition = "uncertain"
	DispositionBlocked           WorkflowDisposition = "blocked"
	DispositionCancelled         WorkflowDisposition = "cancelled"
	DispositionStale             WorkflowDisposition = "stale"
	DispositionMissingSpecialist WorkflowDisposition = "missing-specialist"
	// DispositionUnverified is the only honest outcome for an assurance or
	// evaluation pass that executed nothing.
	DispositionUnverified WorkflowDisposition = "unverified"
)

// These are the lanes whose evidence contract differs from the default.
const (
	laneExecution  = "execution"
	laneAssurance  = "assurance"
	laneEvaluation = "evaluation"
	laneDiscovery  = "discovery"
)

// CommandEvidence stores proof digests, never raw commands, prompts, or output.
type CommandEvidence struct {
	CommandID    string `json:"commandId"`
	ArgvDigest   string `json:"argvDigest"`
	ExitCode     int    `json:"exitCode"`
	StartedAt    string `json:"startedAt"`
	FinishedAt   string `json:"finishedAt"`
	StdoutDigest string `json:"stdoutDigest"`
	StderrDigest string `json:"stderrDigest"`
}

type CheckEvidence struct {
	CheckID        string `json:"checkId"`
	CommandID      string `json:"commandId"`
	Passed         bool   `json:"passed"`
	Current        bool   `json:"current"`
	EvidenceDigest string `json:"evidenceDigest"`
}

type ArtifactEvidence struct {
	ArtifactID string `json:"artifactId"`
	Path       string `json:"path"`
	Digest     string `json:"digest"`
	Current    bool   `json:"current"`
}

type MutationEvidence struct {
	Path         string `json:"path"`
	Symbol       string `json:"symbol"`
	BeforeDigest string `json:"beforeDigest"`
	AfterDigest  string `json:"afterDigest"`
}

type FindingEvidence struct {
	FindingID      string `json:"findingId"`
	Severity       string `json:"severity"`
	Summary        string `json:"summary"`
	EvidenceDigest string `json:"evidenceDigest"`
}

// DiffReview proves the real `git diff HEAD` was read before returning, and
// pins which change was reviewed so a later assurance pass cannot silently
// certify a different one.
type DiffReview struct {
	CommandID  string   `json:"commandId"`
	DiffDigest string   `json:"diffDigest"`
	ReviewedAt string   `json:"reviewedAt"`
	Findings   []string `json:"findings"`
}

// Pointer is what an exploration pass returns instead of file contents: where
// to look, and one line of why it matters.
type Pointer struct {
	Path      string `json:"path"`
	StartLine int    `json:"startLine"`
	EndLine   int    `json:"endLine"`
	Symbol    string `json:"symbol"`
	Why       string `json:"why"`
}

type SpecialistChoice struct {
	RoleID         string `json:"roleId"`
	Action         string `json:"action"`
	Reason         string `json:"reason"`
	EvidenceDigest string `json:"evidenceDigest"`
}

type MissingSpecialist struct {
	Kind               string   `json:"kind"`
	RequiredCapability string   `json:"requiredCapability"`
	EvidenceDigests    []string `json:"evidenceDigests"`
	FactoryRequested   bool     `json:"factoryRequested"`
}

type WorkflowResult struct {
	APIVersion          string              `json:"apiVersion"`
	ResultID            string              `json:"resultId"`
	GoalID              string              `json:"goalId"`
	AssignmentID        string              `json:"assignmentId"`
	GenerationID        string              `json:"generationId"`
	DispatchID          string              `json:"dispatchId"`
	ParentDispatchID    string              `json:"parentDispatchId"`
	Cycle               int                 `json:"cycle"`
	Pass                int                 `json:"pass"`
	RoleID              string              `json:"roleId"`
	Lane                string              `json:"lane"`
	RouteDigest         string              `json:"routeDigest"`
	AuthorityDigest     string              `json:"authorityDigest"`
	SelectionDigest     string              `json:"selectionDigest"`
	RoleDigest          string              `json:"roleDigest"`
	CatalogDigest       string              `json:"catalogDigest"`
	RepositoryBefore    string              `json:"repositoryBefore"`
	RepositoryAfter     string              `json:"repositoryAfter"`
	CapabilityDigest    string              `json:"capabilityDigest"`
	SpecialistChoices   []SpecialistChoice  `json:"specialistChoices"`
	MissingSpecialist   *MissingSpecialist  `json:"missingSpecialist"`
	Files               []string            `json:"files"`
	Pointers            []Pointer           `json:"pointers,omitempty"`
	DiffReview          *DiffReview         `json:"diffReview,omitempty"`
	Symbols             []SymbolClaim       `json:"symbols"`
	Mutations           []MutationEvidence  `json:"mutations"`
	Commands            []CommandEvidence   `json:"commands"`
	Checks              []CheckEvidence     `json:"checks"`
	Artifacts           []ArtifactEvidence  `json:"artifacts"`
	Findings            []FindingEvidence   `json:"findings"`
	Uncertainty         []string            `json:"uncertainty"`
	Decisions           []string            `json:"decisions"`
	Errors              []string            `json:"errors"`
	Assumptions         []string            `json:"assumptions"`
	MissingEvidence     []string            `json:"missingEvidence"`
	ChildResultDigests  []string            `json:"childResultDigests"`
	BudgetReserved      BudgetAmount        `json:"budgetReserved"`
	BudgetConsumed      BudgetAmount        `json:"budgetConsumed"`
	BudgetReleased      BudgetAmount        `json:"budgetReleased"`
	CancellationDigest  string              `json:"cancellationDigest"`
	Stale               bool                `json:"stale"`
	SuggestedNextAction string              `json:"suggestedNextAction"`
	StartedAt           string              `json:"startedAt"`
	FinishedAt          string              `json:"finishedAt"`
	Disposition         WorkflowDisposition `json:"disposition"`
	Digest              string              `json:"digest"`
}

// ResultExpectation is the orchestrator's current dispatch contract. It is
// supplied out-of-band so a worker cannot self-assert freshness or proof.
type ResultExpectation struct {
	GoalID                  string
	AssignmentID            string
	GenerationID            string
	DispatchID              string
	ParentDispatchID        string
	RoleID                  string
	Lane                    string
	RouteDigest             string
	AuthorityDigest         string
	SelectionDigest         string
	RoleDigest              string
	CatalogDigest           string
	RepositoryBefore        string
	CurrentRepositoryDigest string
	CapabilityDigest        string
	RequiredChecks          []string
	RequiredArtifacts       []string
	// Guard is the record set anvil-guard produced for this repository. When
	// present, every cited commandId must resolve inside it.
	Guard *GuardSnapshot
}

func SealWorkflowResult(result *WorkflowResult) error {
	if result == nil {
		return fmt.Errorf("%w: nil workflow result", ErrInvalidContract)
	}
	result.Files = sortedUnique(result.Files)
	result.Uncertainty = sortedUnique(result.Uncertainty)
	result.Decisions = sortedUnique(result.Decisions)
	result.Errors = sortedUnique(result.Errors)
	result.Assumptions = sortedUnique(result.Assumptions)
	result.MissingEvidence = sortedUnique(result.MissingEvidence)
	result.ChildResultDigests = sortedUnique(result.ChildResultDigests)
	sort.Slice(result.Pointers, func(i, j int) bool { return pointerKey(result.Pointers[i]) < pointerKey(result.Pointers[j]) })
	sort.Slice(result.Symbols, func(i, j int) bool { return symbolKey(result.Symbols[i]) < symbolKey(result.Symbols[j]) })
	sort.Slice(result.Checks, func(i, j int) bool { return result.Checks[i].CheckID < result.Checks[j].CheckID })
	sort.Slice(result.Artifacts, func(i, j int) bool { return result.Artifacts[i].ArtifactID < result.Artifacts[j].ArtifactID })
	result.Digest = ""
	digest, err := digestWithoutField(*result, "digest")
	if err != nil {
		return err
	}
	result.Digest = digest
	return validateWorkflowResultShape(*result)
}

// ValidateWorkflowResult reconciles worker-supplied evidence against current
// orchestrator state. A zero exit code never bypasses these checks.
func ValidateWorkflowResult(result WorkflowResult, expected ResultExpectation) error {
	if err := validateWorkflowResultShape(result); err != nil {
		return err
	}
	identity := []struct{ name, got, want string }{
		{"goalId", result.GoalID, expected.GoalID}, {"assignmentId", result.AssignmentID, expected.AssignmentID},
		{"generationId", result.GenerationID, expected.GenerationID}, {"dispatchId", result.DispatchID, expected.DispatchID},
		{"parentDispatchId", result.ParentDispatchID, expected.ParentDispatchID}, {"roleId", result.RoleID, expected.RoleID},
		{"lane", result.Lane, expected.Lane}, {"routeDigest", result.RouteDigest, expected.RouteDigest},
		{"authorityDigest", result.AuthorityDigest, expected.AuthorityDigest}, {"selectionDigest", result.SelectionDigest, expected.SelectionDigest},
		{"roleDigest", result.RoleDigest, expected.RoleDigest}, {"catalogDigest", result.CatalogDigest, expected.CatalogDigest},
		{"repositoryBefore", result.RepositoryBefore, expected.RepositoryBefore}, {"capabilityDigest", result.CapabilityDigest, expected.CapabilityDigest},
	}
	for _, field := range identity {
		if field.got != field.want {
			return fmt.Errorf("%w: result %s does not match current dispatch", ErrInvalidContract, field.name)
		}
	}
	if result.RepositoryAfter != expected.CurrentRepositoryDigest {
		return fmt.Errorf("%w: result repository state is not current", ErrInvalidContract)
	}
	if result.Stale || result.Disposition == DispositionStale {
		return fmt.Errorf("%w: stale workflow result cannot satisfy a current dispatch", ErrInvalidContract)
	}
	// A review that executed nothing interpreted the change rather than
	// checking it, so it cannot carry a pass (succeeded) or a warn (uncertain).
	if (result.Lane == laneAssurance || result.Lane == laneEvaluation) && len(result.Commands) == 0 &&
		(result.Disposition == DispositionSucceeded || result.Disposition == DispositionUncertain) {
		return fmt.Errorf("%w: %s result executed no command and must be unverified", ErrInvalidContract, result.Lane)
	}
	if result.Disposition == DispositionSucceeded {
		if result.Lane == laneExecution && result.DiffReview == nil {
			return fmt.Errorf("%w: execution result lacks a recorded diff review", ErrInvalidContract)
		}
		if result.Lane == laneDiscovery && len(result.Files) > 0 && len(result.Pointers) == 0 {
			return fmt.Errorf("%w: discovery result must return pointers, not file payloads", ErrInvalidContract)
		}
		if result.MissingSpecialist != nil || len(result.Uncertainty) > 0 || len(result.Errors) > 0 || len(result.MissingEvidence) > 0 {
			return fmt.Errorf("%w: successful disposition contains unresolved state", ErrInvalidContract)
		}
		for _, command := range result.Commands {
			if command.ExitCode != 0 {
				return fmt.Errorf("%w: successful disposition contains failed command %q", ErrInvalidContract, command.CommandID)
			}
		}
		if err := requireChecks(result.Checks, expected.RequiredChecks); err != nil {
			return err
		}
		if err := requireArtifacts(result.Artifacts, expected.RequiredArtifacts); err != nil {
			return err
		}
	}
	if result.Disposition == DispositionMissingSpecialist && result.MissingSpecialist == nil {
		return fmt.Errorf("%w: missing-specialist disposition lacks details", ErrInvalidContract)
	}
	if result.Disposition != DispositionMissingSpecialist && result.MissingSpecialist != nil {
		return fmt.Errorf("%w: specialist gap present under disposition %q", ErrInvalidContract, result.Disposition)
	}
	if result.DiffReview != nil {
		if err := RequireGuardRecord(expected.Guard, "diff review", result.DiffReview.CommandID, true, GuardRecordDiffReview); err != nil {
			return err
		}
	}
	return nil
}

func DecodeWorkflowResult(raw []byte, expected ResultExpectation) (WorkflowResult, error) {
	var result WorkflowResult
	if err := DecodeStrict(raw, &result); err != nil {
		return WorkflowResult{}, err
	}
	if err := ValidateWorkflowResult(result, expected); err != nil {
		return WorkflowResult{}, err
	}
	return result, nil
}

func validateWorkflowResultShape(result WorkflowResult) error {
	if result.APIVersion != WorkflowResultAPIVersion {
		return fmt.Errorf("%w: workflow result apiVersion %q", ErrInvalidContractVer, result.APIVersion)
	}
	for _, value := range []string{result.ResultID, result.GoalID, result.AssignmentID, result.GenerationID, result.DispatchID, result.RoleID, result.Lane} {
		if err := ValidateIdentifier(value); err != nil {
			return err
		}
	}
	if result.ParentDispatchID != "" {
		if err := ValidateIdentifier(result.ParentDispatchID); err != nil {
			return err
		}
	}
	if result.Cycle < 1 || result.Pass < 1 || result.Pass > 2 {
		return fmt.Errorf("%w: result cycle/pass is outside the bounded policy", ErrInvalidContract)
	}
	for _, digest := range []string{
		result.RouteDigest, result.AuthorityDigest, result.SelectionDigest, result.RoleDigest,
		result.CatalogDigest, result.RepositoryBefore, result.RepositoryAfter, result.CapabilityDigest,
	} {
		if err := ValidateDigest(digest); err != nil {
			return err
		}
	}
	collections := []any{result.SpecialistChoices, result.Files, result.Symbols, result.Mutations, result.Commands, result.Checks, result.Artifacts, result.Findings, result.Uncertainty, result.Decisions, result.Errors, result.Assumptions, result.MissingEvidence, result.ChildResultDigests}
	for _, collection := range collections {
		if isNilSlice(collection) {
			return fmt.Errorf("%w: workflow result collections must be explicit", ErrInvalidContract)
		}
	}
	if resultCollectionSize(result) > 4096 {
		return fmt.Errorf("%w: workflow result exceeds bounded evidence cardinality", ErrInvalidContract)
	}
	for _, file := range result.Files {
		if !validRelativeScope(file) || file == "." {
			return fmt.Errorf("%w: invalid result path %q", ErrInvalidContract, file)
		}
	}
	for _, symbol := range result.Symbols {
		if err := validateResultSymbol(symbol); err != nil {
			return err
		}
	}
	commandIDs := map[string]struct{}{}
	for _, command := range result.Commands {
		if err := validateCommandEvidence(command); err != nil {
			return err
		}
		if _, duplicate := commandIDs[command.CommandID]; duplicate {
			return fmt.Errorf("%w: duplicate command evidence %q", ErrInvalidContract, command.CommandID)
		}
		commandIDs[command.CommandID] = struct{}{}
	}
	if result.DiffReview != nil {
		if err := validateDiffReview(*result.DiffReview, commandIDs); err != nil {
			return err
		}
	}
	for _, pointer := range result.Pointers {
		if err := validatePointer(pointer); err != nil {
			return err
		}
	}
	checkIDs := map[string]struct{}{}
	for _, check := range result.Checks {
		if err := ValidateIdentifier(check.CheckID); err != nil {
			return err
		}
		if _, ok := commandIDs[check.CommandID]; !ok {
			return fmt.Errorf("%w: check %q references unknown command", ErrInvalidContract, check.CheckID)
		}
		if err := ValidateDigest(check.EvidenceDigest); err != nil {
			return err
		}
		if _, duplicate := checkIDs[check.CheckID]; duplicate {
			return fmt.Errorf("%w: duplicate check %q", ErrInvalidContract, check.CheckID)
		}
		checkIDs[check.CheckID] = struct{}{}
	}
	artifactIDs := map[string]struct{}{}
	for _, artifact := range result.Artifacts {
		if err := ValidateIdentifier(artifact.ArtifactID); err != nil {
			return err
		}
		if !validRelativeScope(artifact.Path) || artifact.Path == "." {
			return fmt.Errorf("%w: invalid artifact path %q", ErrInvalidContract, artifact.Path)
		}
		if err := ValidateDigest(artifact.Digest); err != nil {
			return err
		}
		if _, duplicate := artifactIDs[artifact.ArtifactID]; duplicate {
			return fmt.Errorf("%w: duplicate artifact %q", ErrInvalidContract, artifact.ArtifactID)
		}
		artifactIDs[artifact.ArtifactID] = struct{}{}
	}
	for _, mutation := range result.Mutations {
		if !validRelativeScope(mutation.Path) || mutation.Path == "." {
			return fmt.Errorf("%w: invalid mutation path %q", ErrInvalidContract, mutation.Path)
		}
		if mutation.Symbol != "" && !qualifiedSymbolPattern.MatchString(mutation.Symbol) {
			return fmt.Errorf("%w: invalid mutation symbol %q", ErrInvalidContract, mutation.Symbol)
		}
		for _, digest := range []string{mutation.BeforeDigest, mutation.AfterDigest} {
			if err := ValidateDigest(digest); err != nil {
				return err
			}
		}
	}
	for _, finding := range result.Findings {
		if err := ValidateIdentifier(finding.FindingID); err != nil {
			return err
		}
		if finding.Summary == "" || !containsValue([]string{"info", "low", "medium", "high", "critical"}, finding.Severity) {
			return fmt.Errorf("%w: invalid finding %q", ErrInvalidContract, finding.FindingID)
		}
		if err := ValidateDigest(finding.EvidenceDigest); err != nil {
			return err
		}
	}
	for _, choice := range result.SpecialistChoices {
		if err := ValidateIdentifier(choice.RoleID); err != nil {
			return err
		}
		if choice.Reason == "" || !containsValue([]string{"proposed", "added", "removed", "selected", "declined"}, choice.Action) {
			return fmt.Errorf("%w: invalid specialist choice", ErrInvalidContract)
		}
		if err := ValidateDigest(choice.EvidenceDigest); err != nil {
			return err
		}
	}
	if result.MissingSpecialist != nil {
		if result.MissingSpecialist.RequiredCapability == "" || !containsValue([]string{"technical", "domain"}, result.MissingSpecialist.Kind) || len(result.MissingSpecialist.EvidenceDigests) == 0 {
			return fmt.Errorf("%w: invalid missing-specialist details", ErrInvalidContract)
		}
		for _, digest := range result.MissingSpecialist.EvidenceDigests {
			if err := ValidateDigest(digest); err != nil {
				return err
			}
		}
	}
	for _, digest := range result.ChildResultDigests {
		if err := ValidateDigest(digest); err != nil {
			return err
		}
	}
	for _, amount := range []BudgetAmount{result.BudgetReserved, result.BudgetConsumed, result.BudgetReleased} {
		if err := validateBudgetAmount(amount); err != nil {
			return err
		}
	}
	if exceedsBudget(result.BudgetConsumed, result.BudgetReserved) || exceedsBudget(result.BudgetReleased, result.BudgetReserved) {
		return fmt.Errorf("%w: result budget accounting exceeds reservation", ErrInvalidContract)
	}
	accounted := BudgetAmount{
		Delegates:       result.BudgetConsumed.Delegates + result.BudgetReleased.Delegates,
		Writers:         result.BudgetConsumed.Writers + result.BudgetReleased.Writers,
		Tokens:          result.BudgetConsumed.Tokens + result.BudgetReleased.Tokens,
		DurationSeconds: result.BudgetConsumed.DurationSeconds + result.BudgetReleased.DurationSeconds,
	}
	if exceedsBudget(accounted, result.BudgetReserved) {
		return fmt.Errorf("%w: consumed plus released budget exceeds reservation", ErrInvalidContract)
	}
	if result.CancellationDigest != "" {
		if err := ValidateDigest(result.CancellationDigest); err != nil {
			return err
		}
	}
	started, err := time.Parse(time.RFC3339Nano, result.StartedAt)
	if err != nil || started.IsZero() {
		return fmt.Errorf("%w: invalid result startedAt", ErrInvalidContract)
	}
	finished, err := time.Parse(time.RFC3339Nano, result.FinishedAt)
	if err != nil || finished.Before(started) {
		return fmt.Errorf("%w: invalid result finishedAt", ErrInvalidContract)
	}
	switch result.Disposition {
	case DispositionSucceeded, DispositionFailed, DispositionUncertain, DispositionBlocked, DispositionCancelled, DispositionStale, DispositionMissingSpecialist, DispositionUnverified:
	default:
		return fmt.Errorf("%w: invalid workflow disposition %q", ErrInvalidContract, result.Disposition)
	}
	return validateSelfDigest(result, result.Digest)
}

func validateDiffReview(review DiffReview, commandIDs map[string]struct{}) error {
	if err := ValidateIdentifier(review.CommandID); err != nil {
		return err
	}
	if _, ok := commandIDs[review.CommandID]; !ok {
		return fmt.Errorf("%w: diff review references unknown command %q", ErrInvalidContract, review.CommandID)
	}
	if err := ValidateDigest(review.DiffDigest); err != nil {
		return err
	}
	if err := ValidateTimestamp(review.ReviewedAt); err != nil {
		return err
	}
	if review.Findings == nil {
		return fmt.Errorf("%w: diff review findings must be explicit", ErrInvalidContract)
	}
	return nil
}

func validatePointer(pointer Pointer) error {
	if !validRelativeScope(pointer.Path) || pointer.Path == "." {
		return fmt.Errorf("%w: invalid pointer path %q", ErrInvalidContract, pointer.Path)
	}
	if pointer.StartLine < 1 || pointer.EndLine < pointer.StartLine {
		return fmt.Errorf("%w: pointer %q has an invalid line range", ErrInvalidContract, pointer.Path)
	}
	if pointer.Symbol != "" && !qualifiedSymbolPattern.MatchString(pointer.Symbol) {
		return fmt.Errorf("%w: invalid pointer symbol %q", ErrInvalidContract, pointer.Symbol)
	}
	if pointer.Why == "" {
		return fmt.Errorf("%w: pointer %q lacks the one line explaining why it matters", ErrInvalidContract, pointer.Path)
	}
	return nil
}

// RequireDiffReviewContinuity rejects an assurance pass that reviewed a
// different change than the execution result it certifies.
func RequireDiffReviewContinuity(execution, assurance WorkflowResult) error {
	if execution.DiffReview == nil || assurance.DiffReview == nil {
		return fmt.Errorf("%w: diff-review continuity requires a recorded review on both results", ErrInvalidContract)
	}
	if execution.DiffReview.DiffDigest != assurance.DiffReview.DiffDigest {
		return fmt.Errorf("%w: assurance reviewed a different change than the execution result", ErrInvalidContract)
	}
	return nil
}

func requireChecks(checks []CheckEvidence, required []string) error {
	byID := make(map[string]CheckEvidence, len(checks))
	for _, check := range checks {
		byID[check.CheckID] = check
	}
	for _, checkID := range required {
		check, ok := byID[checkID]
		if !ok || !check.Passed || !check.Current {
			return fmt.Errorf("%w: required check %q is missing, failed, or stale", ErrInvalidContract, checkID)
		}
	}
	return nil
}

func requireArtifacts(artifacts []ArtifactEvidence, required []string) error {
	byID := make(map[string]ArtifactEvidence, len(artifacts))
	for _, artifact := range artifacts {
		byID[artifact.ArtifactID] = artifact
	}
	for _, artifactID := range required {
		artifact, ok := byID[artifactID]
		if !ok || !artifact.Current {
			return fmt.Errorf("%w: required artifact %q is missing or stale", ErrInvalidContract, artifactID)
		}
	}
	return nil
}

func validateCommandEvidence(command CommandEvidence) error {
	if err := ValidateIdentifier(command.CommandID); err != nil {
		return err
	}
	for _, digest := range []string{command.ArgvDigest, command.StdoutDigest, command.StderrDigest} {
		if err := ValidateDigest(digest); err != nil {
			return err
		}
	}
	started, err := time.Parse(time.RFC3339Nano, command.StartedAt)
	if err != nil || started.IsZero() {
		return fmt.Errorf("%w: invalid command start", ErrInvalidContract)
	}
	finished, err := time.Parse(time.RFC3339Nano, command.FinishedAt)
	if err != nil || finished.Before(started) {
		return fmt.Errorf("%w: invalid command finish", ErrInvalidContract)
	}
	return nil
}

func validateResultSymbol(symbol SymbolClaim) error {
	if err := ValidateIdentifier(symbol.Language); err != nil {
		return err
	}
	if !validRelativeScope(symbol.Path) || !qualifiedSymbolPattern.MatchString(symbol.QualifiedName) {
		return fmt.Errorf("%w: invalid result symbol %q", ErrInvalidContract, symbolKey(symbol))
	}
	return nil
}

func pointerKey(pointer Pointer) string {
	return fmt.Sprintf("%s:%09d:%09d:%s", pointer.Path, pointer.StartLine, pointer.EndLine, pointer.Symbol)
}

func resultCollectionSize(result WorkflowResult) int {
	return len(result.Pointers) + len(result.SpecialistChoices) + len(result.Files) + len(result.Symbols) + len(result.Mutations) + len(result.Commands) + len(result.Checks) + len(result.Artifacts) + len(result.Findings) + len(result.Uncertainty) + len(result.Decisions) + len(result.Errors) + len(result.Assumptions) + len(result.MissingEvidence) + len(result.ChildResultDigests)
}

func isNilSlice(value any) bool {
	switch typed := value.(type) {
	case []SpecialistChoice:
		return typed == nil
	case []string:
		return typed == nil
	case []SymbolClaim:
		return typed == nil
	case []MutationEvidence:
		return typed == nil
	case []CommandEvidence:
		return typed == nil
	case []CheckEvidence:
		return typed == nil
	case []ArtifactEvidence:
		return typed == nil
	case []FindingEvidence:
		return typed == nil
	default:
		return true
	}
}

func exceedsBudget(value, ceiling BudgetAmount) bool {
	return value.Delegates > ceiling.Delegates || value.Writers > ceiling.Writers || value.Tokens > ceiling.Tokens || value.DurationSeconds > ceiling.DurationSeconds
}
