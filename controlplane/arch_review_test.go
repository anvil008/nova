package controlplane

import (
	"errors"
	"testing"
)

// archReviewSnapshot is the record set anvil-guard produced when it ran the
// structural architecture-conformance check itself.
func archReviewSnapshot() *GuardSnapshot {
	snapshot := guardSnapshot()
	snapshot.Records = append(snapshot.Records, GuardRecord{
		Kind: GuardRecordArchReview, CommandID: "command-arch", Evidence: CommandEvidence{
			CommandID: "command-arch", ArgvDigest: testDigest("arch-argv"), ExitCode: 0,
			StartedAt: "2026-08-23T20:02:00Z", FinishedAt: "2026-08-23T20:02:05Z",
			StdoutDigest: testDigest("arch-out"), StderrDigest: testDigest("arch-err"),
		},
	})
	return snapshot
}

// resultWithArchReview extends the valid execution result with an executable
// architecture-conformance record tied to the arch command it ran.
func resultWithArchReview(t *testing.T) (WorkflowResult, ResultExpectation) {
	t.Helper()
	result, expected := validWorkflowResult(t)
	archCommand := CommandEvidence{
		CommandID: "command-arch", ArgvDigest: testDigest("arch-argv"), ExitCode: 0,
		StartedAt: "2026-08-23T20:02:00Z", FinishedAt: "2026-08-23T20:02:05Z",
		StdoutDigest: testDigest("arch-out"), StderrDigest: testDigest("arch-err"),
	}
	result.Commands = append(append([]CommandEvidence(nil), result.Commands...), archCommand)
	result.ArchReview = &ArchReview{
		CheckID: "arch", CommandID: archCommand.CommandID, Digest: testDigest("arch-assertions"),
		Assertions: 3, Passed: 3, Current: true,
	}
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	return result, expected
}

// The executable architecture check is a structural design gate, so its cited
// command must resolve to an arch-review run anvil-guard actually performed.
func TestWorkflowResultArchReviewMustResolveToAGuardRecord(t *testing.T) {
	result, expected := resultWithArchReview(t)
	expected.Guard = archReviewSnapshot()
	if err := ValidateWorkflowResult(result, expected); err != nil {
		t.Fatalf("an honest arch review was rejected: %v", err)
	}

	forged := result
	forged.Commands = append([]CommandEvidence(nil), result.Commands...)
	forged.Commands[len(forged.Commands)-1].CommandID = "command-forged-arch"
	review := *result.ArchReview
	review.CommandID = "command-forged-arch"
	forged.ArchReview = &review
	if err := SealWorkflowResult(&forged); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(forged, expected); err == nil {
		t.Fatal("an arch review citing a commandId the guard never produced was accepted")
	}

	noGuard := expected
	noGuard.Guard = nil
	if err := ValidateWorkflowResult(forged, noGuard); err != nil {
		t.Fatalf("without guard state the older contract must still pass: %v", err)
	}
}

// An arch review may not borrow the green or diff-review run: those are not
// structural design checks, so on kind alone the citation must be rejected.
func TestWorkflowResultArchReviewRejectsANonArchRecord(t *testing.T) {
	result, expected := resultWithArchReview(t)
	expected.Guard = archReviewSnapshot()

	// command-diff is already in the result (its diff-review run); point the arch
	// review at it so only the record's kind, not its presence, is at issue.
	forged := result
	review := *result.ArchReview
	review.CommandID = "command-diff"
	forged.ArchReview = &review
	if err := SealWorkflowResult(&forged); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(forged, expected); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("an arch review citing the diff-review run was accepted: %v", err)
	}
}

// Shape validation runs at seal time and stands on its own, independent of
// guard resolution.
func TestArchReviewShapeIsValidated(t *testing.T) {
	result, _ := resultWithArchReview(t)

	broken := result
	tooMany := *result.ArchReview
	tooMany.Passed = tooMany.Assertions + 1 // more passing than exist
	broken.ArchReview = &tooMany
	if err := SealWorkflowResult(&broken); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("an arch review claiming more passes than assertions was accepted: %v", err)
	}

	unknown := result
	orphan := *result.ArchReview
	orphan.CommandID = "command-not-in-commands"
	unknown.ArchReview = &orphan
	if err := SealWorkflowResult(&unknown); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("an arch review citing a command absent from the result was accepted: %v", err)
	}
}
