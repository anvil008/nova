package controlplane

import (
	"errors"
	"testing"
)

// K1: every guard record carries a kind, and the exit code alone cannot tell
// them apart. `diff-review` and `green` both exit 0, so a claim about a test
// suite that cites the `git diff HEAD` run is indistinguishable from an honest
// one until the kind is required.
func TestGuardRecordResolutionRequiresTheExpectedKind(t *testing.T) {
	snapshot := guardSnapshot()
	if err := RequireGuardRecord(snapshot, "green run", "command-green", true, GuardRecordGreen); err != nil {
		t.Fatalf("an honest green record was rejected: %v", err)
	}
	if err := RequireGuardRecord(snapshot, "green run", "command-diff", true, GuardRecordGreen); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("the diff-review record stood in for a passing test suite: %v", err)
	}
	if err := RequireGuardRecord(snapshot, "diff review", "command-green", true, GuardRecordDiffReview); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("the green record stood in for a diff review: %v", err)
	}
	if err := RequireGuardRecord(snapshot, "test seal red run", "command-diff", false, GuardRecordSealRed); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("a seal red run resolved to a diff review: %v", err)
	}
	// A handoff test may legitimately cite either the green run or the sealed
	// red run; the exit code then decides which claim it can back.
	if err := RequireGuardRecord(snapshot, "handoff test", "command-red", false, GuardRecordGreen, GuardRecordSealRed); err != nil {
		t.Fatalf("a failing claim against the sealed red run was rejected: %v", err)
	}
	// Requiring no kind at all is the defect itself, so it must not be
	// expressible as a silent allow-anything.
	if err := RequireGuardRecord(snapshot, "green run", "command-diff", true); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("resolution without a required kind was permitted: %v", err)
	}
	if err := RequireGuardRecord(nil, "green run", "command-diff", true); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("a missing kind must fail closed even without guard state: %v", err)
	}
}

// K2: the kind requirement has to reach the shipped call sites, not just the
// helper. A diff review that cites the green run is reviewing nothing.
func TestWorkflowResultDiffReviewRejectsANonDiffReviewRecord(t *testing.T) {
	result, expected := validWorkflowResult(t)
	expected.Guard = guardSnapshot()

	forged := result
	forged.Commands = append([]CommandEvidence(nil), result.Commands...)
	forged.Commands[1].CommandID = "command-green"
	review := *result.DiffReview
	review.CommandID = "command-green"
	forged.DiffReview = &review
	if err := SealWorkflowResult(&forged); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(forged, expected); err == nil {
		t.Fatal("a diff review citing the green test run was accepted")
	}
}

// K3: the same for the green gate. The diff review runs `git diff HEAD`; it is
// not evidence that any test passed.
func TestGreenObservationRejectsADiffReviewRecord(t *testing.T) {
	snapshot := guardSnapshot()
	seal := TestSeal{
		SealedAt:     "2026-08-23T20:00:30Z",
		Tests:        []TestSealTest{{Path: "controlplane/result_test.go", Digest: testDigest("red-test")}},
		RedCommandID: "command-red", Amendments: []TestSealAmendment{},
	}
	state, err := AttachTestSeal(newTestVerification(t), seal, snapshot)
	if err != nil {
		t.Fatal(err)
	}
	observation := greenObservation(seal, "2026-08-23T20:01:00Z")
	observation.Guard = snapshot
	observation.Command.CommandID = "command-diff"
	observation.Green.CommandID = "command-diff"
	if _, err := acceptWithTests(state, observation); err == nil {
		t.Fatal("the diff-review record was accepted as the green run")
	}
}
