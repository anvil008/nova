package controlplane

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"time"
)

const LifecycleAPIVersion = "anvil.lifecycle/v1"

type GoalRecord struct {
	APIVersion       string `json:"apiVersion"`
	GoalID           string `json:"goalId"`
	RepositoryDigest string `json:"repositoryDigest"`
	CreatedAt        string `json:"createdAt"`
	Digest           string `json:"digest"`
}

type AssignmentRecord struct {
	APIVersion   string `json:"apiVersion"`
	AssignmentID string `json:"assignmentId"`
	GoalID       string `json:"goalId"`
	GenerationID string `json:"generationId"`
	RoleID       string `json:"roleId"`
	Lane         string `json:"lane"`
	CreatedAt    string `json:"createdAt"`
	Digest       string `json:"digest"`
}

// GenerationRecord provides a durable, monotonically increasing fence within
// one goal. GenerationNumber starts at one.
type GenerationRecord struct {
	APIVersion         string `json:"apiVersion"`
	GoalID             string `json:"goalId"`
	GenerationID       string `json:"generationId"`
	GenerationNumber   uint64 `json:"generationNumber"`
	ParentGenerationID string `json:"parentGenerationId"`
	RepositoryDigest   string `json:"repositoryDigest"`
	CreatedAt          string `json:"createdAt"`
	Digest             string `json:"digest"`
}

type DispatchRecord struct {
	APIVersion       string `json:"apiVersion"`
	DispatchID       string `json:"dispatchId"`
	ParentDispatchID string `json:"parentDispatchId"`
	GoalID           string `json:"goalId"`
	AssignmentID     string `json:"assignmentId"`
	GenerationID     string `json:"generationId"`
	RoleID           string `json:"roleId"`
	CreatedAt        string `json:"createdAt"`
	Digest           string `json:"digest"`
}

// BudgetAmount is used for reservations and accounting. Duration is an
// aggregate of child wall-clock reservations, not elapsed goal time.
type BudgetAmount struct {
	Delegates       int   `json:"delegates"`
	Writers         int   `json:"writers"`
	Tokens          int64 `json:"tokens"`
	DurationSeconds int64 `json:"durationSeconds"`
}

type BudgetReservation struct {
	APIVersion    string       `json:"apiVersion"`
	ReservationID string       `json:"reservationId"`
	GoalID        string       `json:"goalId"`
	GenerationID  string       `json:"generationId"`
	DispatchID    string       `json:"dispatchId"`
	Reserved      BudgetAmount `json:"reserved"`
	Consumed      BudgetAmount `json:"consumed"`
	Released      BudgetAmount `json:"released"`
	Active        BudgetAmount `json:"active"`
	UnknownUsage  bool         `json:"unknownUsage"`
	UpdatedAt     string       `json:"updatedAt"`
	Digest        string       `json:"digest"`
}

type OwnershipMode string

const (
	OwnershipRead  OwnershipMode = "read"
	OwnershipWrite OwnershipMode = "write"
)

type SymbolClaim struct {
	Language      string `json:"language"`
	Path          string `json:"path"`
	QualifiedName string `json:"qualifiedName"`
}

type OwnershipClaim struct {
	APIVersion   string        `json:"apiVersion"`
	ClaimID      string        `json:"claimId"`
	GoalID       string        `json:"goalId"`
	GenerationID string        `json:"generationId"`
	DispatchID   string        `json:"dispatchId"`
	Mode         OwnershipMode `json:"mode"`
	Paths        []string      `json:"paths"`
	Symbols      []SymbolClaim `json:"symbols"`
	IssuedAt     string        `json:"issuedAt"`
	ExpiresAt    string        `json:"expiresAt"`
	Digest       string        `json:"digest"`
}

type CancellationState string

const (
	CancellationRequested CancellationState = "requested"
	CancellationDraining  CancellationState = "draining"
	CancellationDrained   CancellationState = "drained"
)

type CancellationFence struct {
	APIVersion             string            `json:"apiVersion"`
	FenceID                string            `json:"fenceId"`
	GoalID                 string            `json:"goalId"`
	GenerationID           string            `json:"generationId"`
	GenerationNumber       uint64            `json:"generationNumber"`
	State                  CancellationState `json:"state"`
	CancelledDispatchIDs   []string          `json:"cancelledDispatchIds"`
	LiveDescendantCount    int               `json:"liveDescendantCount"`
	ActiveLeaseCount       int               `json:"activeLeaseCount"`
	ActiveReservationCount int               `json:"activeReservationCount"`
	LateEventDisposition   string            `json:"lateEventDisposition"`
	RequestedAt            string            `json:"requestedAt"`
	DrainedAt              string            `json:"drainedAt"`
	Digest                 string            `json:"digest"`
}

var qualifiedSymbolPattern = regexp.MustCompile(`^[A-Za-z_$][A-Za-z0-9_$]*(?:[.:/#][A-Za-z_$][A-Za-z0-9_$]*)*$`)

func SealGoal(record *GoalRecord) error {
	if record == nil {
		return fmt.Errorf("%w: nil goal", ErrInvalidContract)
	}
	record.Digest = ""
	digest, err := digestWithoutField(*record, "digest")
	if err != nil {
		return err
	}
	record.Digest = digest
	return ValidateGoal(*record)
}

func ValidateGoal(record GoalRecord) error {
	if record.APIVersion != LifecycleAPIVersion {
		return fmt.Errorf("%w: goal apiVersion %q", ErrInvalidContractVer, record.APIVersion)
	}
	if err := ValidateIdentifier(record.GoalID); err != nil {
		return err
	}
	if err := ValidateDigest(record.RepositoryDigest); err != nil {
		return err
	}
	if err := ValidateTimestamp(record.CreatedAt); err != nil {
		return err
	}
	return validateSelfDigest(record, record.Digest)
}

func SealAssignment(record *AssignmentRecord) error {
	if record == nil {
		return fmt.Errorf("%w: nil assignment", ErrInvalidContract)
	}
	record.Digest = ""
	digest, err := digestWithoutField(*record, "digest")
	if err != nil {
		return err
	}
	record.Digest = digest
	return ValidateAssignment(*record)
}

func ValidateAssignment(record AssignmentRecord) error {
	if record.APIVersion != LifecycleAPIVersion {
		return fmt.Errorf("%w: assignment apiVersion %q", ErrInvalidContractVer, record.APIVersion)
	}
	for _, value := range []string{record.AssignmentID, record.GoalID, record.GenerationID, record.RoleID, record.Lane} {
		if err := ValidateIdentifier(value); err != nil {
			return err
		}
	}
	if err := ValidateTimestamp(record.CreatedAt); err != nil {
		return err
	}
	return validateSelfDigest(record, record.Digest)
}

func SealGeneration(record *GenerationRecord) error {
	if record == nil {
		return fmt.Errorf("%w: nil generation", ErrInvalidContract)
	}
	record.Digest = ""
	digest, err := digestWithoutField(*record, "digest")
	if err != nil {
		return err
	}
	record.Digest = digest
	return ValidateGeneration(*record)
}

func ValidateGeneration(record GenerationRecord) error {
	if record.APIVersion != LifecycleAPIVersion {
		return fmt.Errorf("%w: generation apiVersion %q", ErrInvalidContractVer, record.APIVersion)
	}
	for _, value := range []string{record.GoalID, record.GenerationID} {
		if err := ValidateIdentifier(value); err != nil {
			return err
		}
	}
	if record.GenerationNumber == 0 {
		return fmt.Errorf("%w: generation number starts at one", ErrInvalidContract)
	}
	if record.GenerationNumber == 1 && record.ParentGenerationID != "" {
		return fmt.Errorf("%w: first generation cannot have a parent", ErrInvalidContract)
	}
	if record.GenerationNumber > 1 {
		if err := ValidateIdentifier(record.ParentGenerationID); err != nil {
			return fmt.Errorf("%w: later generation requires parent: %v", ErrInvalidContract, err)
		}
	}
	if err := ValidateDigest(record.RepositoryDigest); err != nil {
		return err
	}
	if err := ValidateTimestamp(record.CreatedAt); err != nil {
		return err
	}
	return validateSelfDigest(record, record.Digest)
}

// ValidateGenerationSequence requires an exact, gap-free lineage for one goal.
func ValidateGenerationSequence(records []GenerationRecord) error {
	if len(records) == 0 {
		return fmt.Errorf("%w: generation sequence is empty", ErrInvalidContract)
	}
	ordered := append([]GenerationRecord(nil), records...)
	sort.Slice(ordered, func(i, j int) bool { return ordered[i].GenerationNumber < ordered[j].GenerationNumber })
	goalID := ordered[0].GoalID
	seenIDs := make(map[string]struct{}, len(ordered))
	for index, record := range ordered {
		if err := ValidateGeneration(record); err != nil {
			return err
		}
		if record.GoalID != goalID || record.GenerationNumber != uint64(index+1) {
			return fmt.Errorf("%w: generation sequence is non-monotonic or crosses goals", ErrInvalidContract)
		}
		if _, duplicate := seenIDs[record.GenerationID]; duplicate {
			return fmt.Errorf("%w: duplicate generation id %q", ErrInvalidContract, record.GenerationID)
		}
		seenIDs[record.GenerationID] = struct{}{}
		if index > 0 && record.ParentGenerationID != ordered[index-1].GenerationID {
			return fmt.Errorf("%w: generation %q has stale parent", ErrInvalidContract, record.GenerationID)
		}
	}
	return nil
}

func SealDispatch(record *DispatchRecord) error {
	if record == nil {
		return fmt.Errorf("%w: nil dispatch", ErrInvalidContract)
	}
	record.Digest = ""
	digest, err := digestWithoutField(*record, "digest")
	if err != nil {
		return err
	}
	record.Digest = digest
	return ValidateDispatch(*record)
}

func ValidateDispatch(record DispatchRecord) error {
	if record.APIVersion != LifecycleAPIVersion {
		return fmt.Errorf("%w: dispatch apiVersion %q", ErrInvalidContractVer, record.APIVersion)
	}
	for _, value := range []string{record.DispatchID, record.GoalID, record.AssignmentID, record.GenerationID, record.RoleID} {
		if err := ValidateIdentifier(value); err != nil {
			return err
		}
	}
	if record.ParentDispatchID != "" {
		if err := ValidateIdentifier(record.ParentDispatchID); err != nil {
			return err
		}
		if record.ParentDispatchID == record.DispatchID {
			return fmt.Errorf("%w: dispatch cannot parent itself", ErrInvalidContract)
		}
	}
	if err := ValidateTimestamp(record.CreatedAt); err != nil {
		return err
	}
	return validateSelfDigest(record, record.Digest)
}

func SealBudgetReservation(reservation *BudgetReservation) error {
	if reservation == nil {
		return fmt.Errorf("%w: nil budget reservation", ErrInvalidContract)
	}
	reservation.Digest = ""
	digest, err := digestWithoutField(*reservation, "digest")
	if err != nil {
		return err
	}
	reservation.Digest = digest
	return ValidateBudgetReservation(*reservation, BudgetLimit{
		MaxDelegates: reservation.Reserved.Delegates, MaxWriters: reservation.Reserved.Writers,
		MaxTokens: reservation.Reserved.Tokens, MaxDurationSeconds: reservation.Reserved.DurationSeconds,
	})
}

// ValidateBudgetReservation checks both the parent ceiling and the accounting
// identity reserved = consumed + released + active for every dimension.
func ValidateBudgetReservation(reservation BudgetReservation, ceiling BudgetLimit) error {
	if reservation.APIVersion != LifecycleAPIVersion {
		return fmt.Errorf("%w: budget apiVersion %q", ErrInvalidContractVer, reservation.APIVersion)
	}
	for _, value := range []string{reservation.ReservationID, reservation.GoalID, reservation.GenerationID, reservation.DispatchID} {
		if err := ValidateIdentifier(value); err != nil {
			return err
		}
	}
	if err := validateBudgetAmount(reservation.Reserved); err != nil {
		return err
	}
	for _, amount := range []BudgetAmount{reservation.Consumed, reservation.Released, reservation.Active} {
		if err := validateBudgetAmount(amount); err != nil {
			return err
		}
	}
	if reservation.UnknownUsage {
		return fmt.Errorf("%w: unknown usage cannot be admitted as zero", ErrInvalidContract)
	}
	if !budgetEqual(reservation.Reserved, addBudget(reservation.Consumed, reservation.Released, reservation.Active)) {
		return fmt.Errorf("%w: budget accounting identity does not balance", ErrInvalidContract)
	}
	if reservation.Reserved.Delegates > ceiling.MaxDelegates || reservation.Reserved.Writers > ceiling.MaxWriters ||
		reservation.Reserved.Tokens > ceiling.MaxTokens || reservation.Reserved.DurationSeconds > ceiling.MaxDurationSeconds {
		return fmt.Errorf("%w: aggregate budget exceeds authority ceiling", ErrInvalidContract)
	}
	if err := ValidateTimestamp(reservation.UpdatedAt); err != nil {
		return err
	}
	return validateSelfDigest(reservation, reservation.Digest)
}

func SealOwnership(claim *OwnershipClaim) error {
	if claim == nil {
		return fmt.Errorf("%w: nil ownership claim", ErrInvalidContract)
	}
	claim.Paths = sortedUnique(claim.Paths)
	sort.Slice(claim.Symbols, func(i, j int) bool { return symbolKey(claim.Symbols[i]) < symbolKey(claim.Symbols[j]) })
	claim.Digest = ""
	digest, err := digestWithoutField(*claim, "digest")
	if err != nil {
		return err
	}
	claim.Digest = digest
	return ValidateOwnership(*claim)
}

func ValidateOwnership(claim OwnershipClaim) error {
	if claim.APIVersion != LifecycleAPIVersion {
		return fmt.Errorf("%w: ownership apiVersion %q", ErrInvalidContractVer, claim.APIVersion)
	}
	for _, value := range []string{claim.ClaimID, claim.GoalID, claim.GenerationID, claim.DispatchID} {
		if err := ValidateIdentifier(value); err != nil {
			return err
		}
	}
	if claim.Mode != OwnershipRead && claim.Mode != OwnershipWrite {
		return fmt.Errorf("%w: invalid ownership mode %q", ErrInvalidContract, claim.Mode)
	}
	if claim.Paths == nil || claim.Symbols == nil || len(claim.Paths)+len(claim.Symbols) == 0 {
		return fmt.Errorf("%w: ownership requires explicit path or symbol claims", ErrInvalidContract)
	}
	if len(claim.Paths)+len(claim.Symbols) > 512 {
		return fmt.Errorf("%w: ownership exceeds 512 claims", ErrInvalidContract)
	}
	seenPaths := map[string]struct{}{}
	for _, pathname := range claim.Paths {
		if !validRelativeScope(pathname) || pathname == "." {
			return fmt.Errorf("%w: invalid ownership path %q", ErrInvalidContract, pathname)
		}
		if _, duplicate := seenPaths[pathname]; duplicate {
			return fmt.Errorf("%w: duplicate ownership path %q", ErrInvalidContract, pathname)
		}
		seenPaths[pathname] = struct{}{}
	}
	seenSymbols := map[string]struct{}{}
	for _, symbol := range claim.Symbols {
		if err := ValidateIdentifier(symbol.Language); err != nil {
			return err
		}
		if !validRelativeScope(symbol.Path) || symbol.Path == "." || !qualifiedSymbolPattern.MatchString(symbol.QualifiedName) {
			return fmt.Errorf("%w: invalid symbol claim %q", ErrInvalidContract, symbolKey(symbol))
		}
		key := symbolKey(symbol)
		if _, duplicate := seenSymbols[key]; duplicate {
			return fmt.Errorf("%w: duplicate symbol claim %q", ErrInvalidContract, key)
		}
		seenSymbols[key] = struct{}{}
	}
	issued, err := time.Parse(time.RFC3339Nano, claim.IssuedAt)
	if err != nil || issued.IsZero() {
		return fmt.Errorf("%w: invalid ownership issuedAt", ErrInvalidContract)
	}
	expires, err := time.Parse(time.RFC3339Nano, claim.ExpiresAt)
	if err != nil || !expires.After(issued) {
		return fmt.Errorf("%w: ownership expiresAt must follow issuedAt", ErrInvalidContract)
	}
	return validateSelfDigest(claim, claim.Digest)
}

func OwnershipConflicts(left, right OwnershipClaim) bool {
	if left.Mode != OwnershipWrite && right.Mode != OwnershipWrite {
		return false
	}
	for _, a := range left.Paths {
		for _, b := range right.Paths {
			if a == b || strings.HasPrefix(a, b+"/") || strings.HasPrefix(b, a+"/") {
				return true
			}
		}
	}
	for _, a := range left.Symbols {
		for _, b := range right.Symbols {
			if symbolKey(a) == symbolKey(b) {
				return true
			}
		}
	}
	return false
}

func SealCancellation(fence *CancellationFence) error {
	if fence == nil {
		return fmt.Errorf("%w: nil cancellation fence", ErrInvalidContract)
	}
	fence.CancelledDispatchIDs = sortedUnique(fence.CancelledDispatchIDs)
	fence.Digest = ""
	digest, err := digestWithoutField(*fence, "digest")
	if err != nil {
		return err
	}
	fence.Digest = digest
	return ValidateCancellation(*fence)
}

func ValidateCancellation(fence CancellationFence) error {
	if fence.APIVersion != LifecycleAPIVersion {
		return fmt.Errorf("%w: cancellation apiVersion %q", ErrInvalidContractVer, fence.APIVersion)
	}
	for _, value := range []string{fence.FenceID, fence.GoalID, fence.GenerationID} {
		if err := ValidateIdentifier(value); err != nil {
			return err
		}
	}
	if fence.GenerationNumber == 0 || fence.CancelledDispatchIDs == nil {
		return fmt.Errorf("%w: cancellation fence lacks generation or dispatch set", ErrInvalidContract)
	}
	for _, dispatchID := range fence.CancelledDispatchIDs {
		if err := ValidateIdentifier(dispatchID); err != nil {
			return err
		}
	}
	if fence.LiveDescendantCount < 0 || fence.ActiveLeaseCount < 0 || fence.ActiveReservationCount < 0 {
		return fmt.Errorf("%w: cancellation counts cannot be negative", ErrInvalidContract)
	}
	if fence.LateEventDisposition != "record-only-stale" {
		return fmt.Errorf("%w: late events must be record-only-stale", ErrInvalidContract)
	}
	if err := ValidateTimestamp(fence.RequestedAt); err != nil {
		return err
	}
	switch fence.State {
	case CancellationRequested, CancellationDraining:
		if fence.DrainedAt != "" {
			return fmt.Errorf("%w: undrained cancellation has drainedAt", ErrInvalidContract)
		}
	case CancellationDrained:
		if fence.LiveDescendantCount != 0 || fence.ActiveLeaseCount != 0 || fence.ActiveReservationCount != 0 {
			return fmt.Errorf("%w: drained cancellation retains live resources", ErrInvalidContract)
		}
		if err := ValidateTimestamp(fence.DrainedAt); err != nil {
			return err
		}
	default:
		return fmt.Errorf("%w: invalid cancellation state %q", ErrInvalidContract, fence.State)
	}
	return validateSelfDigest(fence, fence.Digest)
}

func validateSelfDigest(value any, digest string) error {
	if err := ValidateDigest(digest); err != nil {
		return err
	}
	expected, err := digestWithoutField(value, "digest")
	if err != nil {
		return err
	}
	if digest != expected {
		return fmt.Errorf("%w: lifecycle digest mismatch", ErrInvalidDigest)
	}
	return nil
}

func validateBudgetAmount(amount BudgetAmount) error {
	if amount.Delegates < 0 || amount.Writers < 0 || amount.Tokens < 0 || amount.DurationSeconds < 0 {
		return fmt.Errorf("%w: budget amount cannot be negative", ErrInvalidContract)
	}
	return nil
}

func addBudget(values ...BudgetAmount) BudgetAmount {
	var total BudgetAmount
	for _, value := range values {
		total.Delegates += value.Delegates
		total.Writers += value.Writers
		total.Tokens += value.Tokens
		total.DurationSeconds += value.DurationSeconds
	}
	return total
}

func budgetEqual(left, right BudgetAmount) bool {
	return left == right
}

func symbolKey(symbol SymbolClaim) string {
	return symbol.Language + ":" + symbol.Path + ":" + symbol.QualifiedName
}
