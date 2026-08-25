package controlplane

import (
	"errors"
	"testing"
)

// guardSnapshot is the record set anvil-guard itself produced for a run. The
// forged ids below are shaped exactly like real ones; only their absence from
// this snapshot distinguishes them.
func guardSnapshot() *GuardSnapshot {
	return &GuardSnapshot{
		APIVersion: GuardSnapshotAPIVersion,
		Repository: "/repositories/alpha",
		Records: []GuardRecord{
			{Kind: GuardRecordSealRed, CommandID: "command-red", Evidence: CommandEvidence{
				CommandID: "command-red", ArgvDigest: testDigest("red-argv"), ExitCode: 1,
				StartedAt: "2026-08-23T20:00:10Z", FinishedAt: "2026-08-23T20:00:20Z",
				StdoutDigest: testDigest("red-out"), StderrDigest: testDigest("red-err"),
			}},
			{Kind: GuardRecordGreen, CommandID: "command-green", Evidence: CommandEvidence{
				CommandID: "command-green", ArgvDigest: testDigest("green-argv"), ExitCode: 0,
				StartedAt: "2026-08-23T20:01:00Z", FinishedAt: "2026-08-23T20:01:05Z",
				StdoutDigest: testDigest("green-out"), StderrDigest: testDigest("green-err"),
			}},
			{Kind: GuardRecordDiffReview, CommandID: "command-diff", Evidence: CommandEvidence{
				CommandID: "command-diff", ArgvDigest: testDigest("diff-argv"), ExitCode: 0,
				StartedAt: "2026-08-23T20:00:02Z", FinishedAt: "2026-08-23T20:00:03Z",
				StdoutDigest: testDigest("diff-out"), StderrDigest: testDigest("diff-err"),
			}},
		},
	}
}

func TestGuardRecordResolutionRejectsIdsGuardNeverProduced(t *testing.T) {
	snapshot := guardSnapshot()
	if err := RequireGuardRecord(snapshot, "green run", "command-green", true, GuardRecordGreen); err != nil {
		t.Fatalf("an honest guard-produced id was rejected: %v", err)
	}
	if err := RequireGuardRecord(snapshot, "red run", "command-red", false, GuardRecordSealRed); err != nil {
		t.Fatalf("the red run is guard-produced and failing: %v", err)
	}
	// A well-formed id nothing in the guard state produced.
	if err := RequireGuardRecord(snapshot, "green run", "command-unit", true, GuardRecordGreen); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("a fabricated commandId resolved: %v", err)
	}
	// The record exists, but its exit code contradicts the claim.
	if err := RequireGuardRecord(snapshot, "green run", "command-red", true, GuardRecordGreen, GuardRecordSealRed); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("a passing claim resolved to a failing guard record: %v", err)
	}
	if err := RequireGuardRecord(snapshot, "red run", "command-green", false, GuardRecordGreen, GuardRecordSealRed); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("a failing claim resolved to a passing guard record: %v", err)
	}
	// Without guard state there is nothing to resolve against; the older
	// contracts still apply on their own.
	if err := RequireGuardRecord(nil, "green run", "command-unit", true, GuardRecordGreen); err != nil {
		t.Fatalf("absent guard state rejected an id: %v", err)
	}
}

func TestWorkflowResultDiffReviewMustResolveToAGuardRecord(t *testing.T) {
	result, expected := validWorkflowResult(t)
	// The fixture's diff review already cites `command-diff`, which the guard
	// snapshot records, so an honest result still validates.
	expected.Guard = guardSnapshot()
	if err := ValidateWorkflowResult(result, expected); err != nil {
		t.Fatalf("an honest diff review was rejected: %v", err)
	}

	forged := result
	forged.Commands = append([]CommandEvidence(nil), result.Commands...)
	forged.Commands[1].CommandID = "command-forged"
	review := *result.DiffReview
	review.CommandID = "command-forged"
	forged.DiffReview = &review
	if err := SealWorkflowResult(&forged); err != nil {
		t.Fatal(err)
	}
	// Self-consistent within the agent's own text: the id appears in Commands
	// with exit 0 and in the diff review. Only the guard state disagrees.
	if err := ValidateWorkflowResult(forged, expected); err == nil {
		t.Fatal("a diff review citing a commandId the guard never produced was accepted")
	}
	noGuard := expected
	noGuard.Guard = nil
	if err := ValidateWorkflowResult(forged, noGuard); err != nil {
		t.Fatalf("without guard state the older contract must still pass: %v", err)
	}
}

func TestSealedVerificationResolvesRedAndGreenAgainstGuardRecords(t *testing.T) {
	snapshot := guardSnapshot()
	seal := TestSeal{
		SealedAt:     "2026-08-23T20:00:30Z",
		Tests:        []TestSealTest{{Path: "controlplane/result_test.go", Digest: testDigest("red-test")}},
		RedCommandID: "command-red", Amendments: []TestSealAmendment{},
	}
	state, err := AttachTestSeal(newTestVerification(t), seal, snapshot)
	if err != nil {
		t.Fatalf("an honest red commandId was rejected: %v", err)
	}

	forgedSeal := seal
	forgedSeal.RedCommandID = "command-invented"
	if _, err := AttachTestSeal(newTestVerification(t), forgedSeal, snapshot); err == nil {
		t.Fatal("a seal citing a red commandId the guard never produced was attached")
	}

	observation := greenObservation(seal, "2026-08-23T20:01:00Z")
	observation.Guard = snapshot
	if _, err := acceptWithTests(state, observation); err != nil {
		t.Fatalf("an honest green commandId was rejected: %v", err)
	}

	forgedGreen := greenObservation(seal, "2026-08-23T20:01:00Z")
	forgedGreen.Guard = snapshot
	forgedGreen.Command.CommandID = "command-invented"
	forgedGreen.Green.CommandID = "command-invented"
	if _, err := acceptWithTests(state, forgedGreen); err == nil {
		t.Fatal("a green run citing a commandId the guard never produced was accepted")
	}
}
