package controlplane

import "testing"

func TestGenerationSequenceRejectsStaleParent(t *testing.T) {
	one := GenerationRecord{APIVersion: LifecycleAPIVersion, GoalID: "goal-1", GenerationID: "generation-1", GenerationNumber: 1, RepositoryDigest: testDigest("repo-1"), CreatedAt: "2026-08-23T20:00:00Z"}
	two := GenerationRecord{APIVersion: LifecycleAPIVersion, GoalID: "goal-1", GenerationID: "generation-2", GenerationNumber: 2, ParentGenerationID: "generation-1", RepositoryDigest: testDigest("repo-2"), CreatedAt: "2026-08-23T20:01:00Z"}
	if err := SealGeneration(&one); err != nil {
		t.Fatal(err)
	}
	if err := SealGeneration(&two); err != nil {
		t.Fatal(err)
	}
	if err := ValidateGenerationSequence([]GenerationRecord{two, one}); err != nil {
		t.Fatal(err)
	}
	two.ParentGenerationID = "generation-stale"
	two.Digest, _ = digestWithoutField(two, "digest")
	if err := ValidateGenerationSequence([]GenerationRecord{one, two}); err == nil {
		t.Fatal("stale generation parent accepted")
	}
}

func TestBudgetReservationBalancesAndFitsCeiling(t *testing.T) {
	reservation := BudgetReservation{
		APIVersion: LifecycleAPIVersion, ReservationID: "budget-1", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-1",
		Reserved:  BudgetAmount{Delegates: 2, Writers: 1, Tokens: 1000, DurationSeconds: 60},
		Consumed:  BudgetAmount{Delegates: 1, Writers: 0, Tokens: 400, DurationSeconds: 20},
		Released:  BudgetAmount{Delegates: 0, Writers: 0, Tokens: 100, DurationSeconds: 10},
		Active:    BudgetAmount{Delegates: 1, Writers: 1, Tokens: 500, DurationSeconds: 30},
		UpdatedAt: "2026-08-23T20:00:00Z",
	}
	if err := SealBudgetReservation(&reservation); err != nil {
		t.Fatal(err)
	}
	ceiling := BudgetLimit{MaxDelegates: 2, MaxWriters: 1, MaxTokens: 1000, MaxDurationSeconds: 60}
	if err := ValidateBudgetReservation(reservation, ceiling); err != nil {
		t.Fatal(err)
	}
	reservation.UnknownUsage = true
	reservation.Digest, _ = digestWithoutField(reservation, "digest")
	if err := ValidateBudgetReservation(reservation, ceiling); err == nil {
		t.Fatal("unknown usage accepted as zero")
	}
}

func TestOwnershipConflictAndSyntax(t *testing.T) {
	left := OwnershipClaim{
		APIVersion: LifecycleAPIVersion, ClaimID: "claim-1", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-1", Mode: OwnershipWrite,
		Paths: []string{"controlplane"}, Symbols: []SymbolClaim{}, IssuedAt: "2026-08-23T20:00:00Z", ExpiresAt: "2026-08-23T21:00:00Z",
	}
	right := OwnershipClaim{
		APIVersion: LifecycleAPIVersion, ClaimID: "claim-2", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-2", Mode: OwnershipRead,
		Paths: []string{"controlplane/route.go"}, Symbols: []SymbolClaim{}, IssuedAt: "2026-08-23T20:00:00Z", ExpiresAt: "2026-08-23T21:00:00Z",
	}
	if err := SealOwnership(&left); err != nil {
		t.Fatal(err)
	}
	if err := SealOwnership(&right); err != nil {
		t.Fatal(err)
	}
	if !OwnershipConflicts(left, right) {
		t.Fatal("overlapping writer/read claim did not conflict")
	}
	right.Mode = OwnershipRead
	left.Mode = OwnershipRead
	if OwnershipConflicts(left, right) {
		t.Fatal("two read claims conflict")
	}
	left.Paths = []string{"../escape"}
	left.Digest, _ = digestWithoutField(left, "digest")
	if err := ValidateOwnership(left); err == nil {
		t.Fatal("traversal ownership accepted")
	}
}

func TestCancellationDrainedRequiresNoLiveResources(t *testing.T) {
	fence := CancellationFence{
		APIVersion: LifecycleAPIVersion, FenceID: "fence-1", GoalID: "goal-1", GenerationID: "generation-1", GenerationNumber: 1,
		State: CancellationDrained, CancelledDispatchIDs: []string{"dispatch-1"}, LateEventDisposition: "record-only-stale",
		RequestedAt: "2026-08-23T20:00:00Z", DrainedAt: "2026-08-23T20:01:00Z",
	}
	if err := SealCancellation(&fence); err != nil {
		t.Fatal(err)
	}
	fence.LiveDescendantCount = 1
	fence.Digest, _ = digestWithoutField(fence, "digest")
	if err := ValidateCancellation(fence); err == nil {
		t.Fatal("drained fence with live descendants accepted")
	}
}
