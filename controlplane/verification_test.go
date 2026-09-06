package controlplane

import "testing"

func newTestVerification(t *testing.T) VerificationState {
	t.Helper()
	state, err := NewVerificationState(
		"verification-1", "goal-1", "generation-1", "assignment-1", "workflow-executor",
		testDigest("writer-result"), testDigest("repo-1"), testDigest("writer-evidence"),
		"2026-08-23T20:00:00Z", VerificationUsage{Tokens: 10_000, DurationSeconds: 600},
	)
	if err != nil {
		t.Fatal(err)
	}
	return state
}

func TestVerificationAcceptsOnFirstIndependentPass(t *testing.T) {
	state := newTestVerification(t)
	next, err := ApplyVerification(state, VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: VerificationAccept,
		RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("review-1"), ResultDigest: testDigest("review-result-1"),
		Reason: "all required proof is current", Usage: VerificationUsage{Tokens: 1000, DurationSeconds: 30}, At: "2026-08-23T20:01:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	if next.Outcome != VerificationAccepted || next.Passes != 1 || next.Phase != VerificationTerminal {
		t.Fatalf("unexpected state: %+v", next)
	}
}

func TestVerificationAllowsOneRepairAndSecondPass(t *testing.T) {
	state := newTestVerification(t)
	state, err := ApplyVerification(state, VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: VerificationReject, Repairable: true,
		RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("review-1"), ResultDigest: testDigest("review-result-1"),
		Reason: "one focused correction is required", Usage: VerificationUsage{Tokens: 1000, DurationSeconds: 30}, At: "2026-08-23T20:01:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	state, err = ApplyRepair(state, RepairObservation{
		WriterRoleID: "workflow-executor", RepositoryDigest: testDigest("repo-2"), EvidenceDigest: testDigest("repair-evidence"),
		ResultDigest: testDigest("repair-result"), Reason: "applied focused correction", Usage: VerificationUsage{Tokens: 1000, DurationSeconds: 30}, At: "2026-08-23T20:02:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	state, err = ApplyVerification(state, VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: VerificationAccept,
		RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("review-2"), ResultDigest: testDigest("review-result-2"),
		Reason: "correction verified", Usage: VerificationUsage{Tokens: 1000, DurationSeconds: 30}, At: "2026-08-23T20:03:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	if state.Outcome != VerificationAccepted || state.Passes != 2 || state.Repairs != 1 || len(state.Events) != 3 {
		t.Fatalf("unexpected bounded loop result: %+v", state)
	}
}

func TestVerificationStopsOnNoProgressBeforeSecondModelPass(t *testing.T) {
	state := newTestVerification(t)
	state, err := ApplyVerification(state, VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: VerificationReject, Repairable: true,
		RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("review-1"), ResultDigest: testDigest("review-result-1"),
		Reason: "repair requested", Usage: VerificationUsage{Tokens: 100, DurationSeconds: 10}, At: "2026-08-23T20:01:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	state, err = ApplyRepair(state, RepairObservation{
		WriterRoleID: state.WriterRoleID, RepositoryDigest: state.RepositoryDigest, EvidenceDigest: state.EvidenceDigest,
		ResultDigest: testDigest("unchanged-result"), Reason: "no change was possible", At: "2026-08-23T20:02:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	if state.Outcome != VerificationNoProgress || state.Passes != 1 {
		t.Fatalf("no-progress did not stop before pass two: %+v", state)
	}
}

func TestVerificationRejectsWriterSelfCertificationAndBudgetOverflow(t *testing.T) {
	state := newTestVerification(t)
	observation := VerificationObservation{
		VerifierRoleID: state.WriterRoleID, Decision: VerificationAccept,
		RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("review"), ResultDigest: testDigest("review-result"),
		Reason: "self-certified", At: "2026-08-23T20:01:00Z",
	}
	if _, err := ApplyVerification(state, observation); err == nil {
		t.Fatal("writer self-certification accepted")
	}
	observation.VerifierRoleID = "workflow-code-review"
	observation.Usage = VerificationUsage{Tokens: 20_000}
	if _, err := ApplyVerification(state, observation); err == nil {
		t.Fatal("verification budget overflow accepted")
	}
}

func TestVerificationTerminatesBlockedCancelledAndExhausted(t *testing.T) {
	for _, decision := range []VerificationDecision{VerificationBlock, VerificationCancel, VerificationReject} {
		state := newTestVerification(t)
		next, err := ApplyVerification(state, VerificationObservation{
			VerifierRoleID: "workflow-code-review", Decision: decision, Repairable: false,
			RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest(string(decision)), ResultDigest: testDigest("review-result-" + string(decision)),
			Reason: "terminal path", At: "2026-08-23T20:01:00Z",
		})
		if err != nil {
			t.Fatal(err)
		}
		if next.Phase != VerificationTerminal || next.Outcome == VerificationPending {
			t.Fatalf("decision %s did not terminate: %+v", decision, next)
		}
	}
}

func sealedVerification(t *testing.T) (VerificationState, TestSeal) {
	t.Helper()
	seal := TestSeal{
		SealedAt:     "2026-08-23T20:00:30Z",
		Tests:        []TestSealTest{{Path: "controlplane/result_test.go", Digest: testDigest("red-test")}},
		RedCommandID: "command-red", Amendments: []TestSealAmendment{},
	}
	state, err := AttachTestSeal(newTestVerification(t), seal, nil)
	if err != nil {
		t.Fatal(err)
	}
	return state, seal
}

func greenObservation(seal TestSeal, startedAt string) *TestObservation {
	command := CommandEvidence{
		CommandID: "command-green", ArgvDigest: testDigest("green-argv"), ExitCode: 0,
		StartedAt: startedAt, FinishedAt: startedAt, StdoutDigest: testDigest("green-out"), StderrDigest: testDigest("green-err"),
	}
	return &TestObservation{
		Tests:   append([]TestSealTest(nil), seal.Tests...),
		Green:   CheckEvidence{CheckID: "green", CommandID: command.CommandID, Passed: true, Current: true, EvidenceDigest: testDigest("green-proof")},
		Command: command,
	}
}

func acceptWithTests(state VerificationState, tests *TestObservation) (VerificationState, error) {
	return ApplyVerification(state, VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: VerificationAccept,
		RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("review-1"), ResultDigest: testDigest("review-result-1"),
		Reason: "sealed tests intact and green", Usage: VerificationUsage{Tokens: 1000, DurationSeconds: 30},
		At: "2026-08-23T20:03:00Z", Tests: tests,
	})
}

func TestVerificationAcceptsAnIntactSealWithGreenEvidence(t *testing.T) {
	state, seal := sealedVerification(t)
	next, err := acceptWithTests(state, greenObservation(seal, "2026-08-23T20:01:00Z"))
	if err != nil {
		t.Fatal(err)
	}
	if next.Outcome != VerificationAccepted || next.TestSeal == nil {
		t.Fatalf("unexpected state: %+v", next)
	}
}

func TestVerificationRejectsObservedTestDigestDrift(t *testing.T) {
	state, seal := sealedVerification(t)
	observation := greenObservation(seal, "2026-08-23T20:01:00Z")
	observation.Tests[0].Digest = testDigest("weakened-test")
	if _, err := acceptWithTests(state, observation); err == nil {
		t.Fatal("verification accepted tests that no longer match the seal")
	}
}

func TestVerificationAcceptsDriftCoveredByARecordedAmendment(t *testing.T) {
	state, seal := sealedVerification(t)
	amended := seal
	amended.Amendments = []TestSealAmendment{{
		At: "2026-08-23T20:00:45Z", Reason: "extend the reproduction case",
		Before: seal.Tests, After: []TestSealTest{{Path: seal.Tests[0].Path, Digest: testDigest("amended-test")}},
	}}
	state, err := AttachTestSeal(newTestVerification(t), amended, nil)
	if err != nil {
		t.Fatal(err)
	}
	observation := greenObservation(amended, "2026-08-23T20:01:00Z")
	observation.Tests = amended.Amendments[0].After
	if _, err := acceptWithTests(state, observation); err != nil {
		t.Fatal(err)
	}
}

func TestVerificationRequiresGreenEvidenceThatPostdatesTheSeal(t *testing.T) {
	state, seal := sealedVerification(t)
	if _, err := acceptWithTests(state, greenObservation(seal, "2026-08-23T19:59:00Z")); err == nil {
		t.Fatal("verification accepted green evidence recorded before the seal")
	}
	stale := greenObservation(seal, "2026-08-23T20:01:00Z")
	stale.Green.Current = false
	if _, err := acceptWithTests(state, stale); err == nil {
		t.Fatal("verification accepted a stale green check")
	}
	failed := greenObservation(seal, "2026-08-23T20:01:00Z")
	failed.Command.ExitCode = 1
	if _, err := acceptWithTests(state, failed); err == nil {
		t.Fatal("verification accepted a non-zero green command")
	}
}

func TestVerificationRequiresATestObservationWhenSealed(t *testing.T) {
	state, _ := sealedVerification(t)
	if _, err := acceptWithTests(state, nil); err == nil {
		t.Fatal("sealed verification accepted an observation with no sealed-test evidence")
	}
}

func TestVerificationRejectsPartiallyObservedSealedTests(t *testing.T) {
	seal := TestSeal{
		SealedAt: "2026-08-23T20:00:30Z", RedCommandID: "command-red", Amendments: []TestSealAmendment{},
		Tests: []TestSealTest{
			{Path: "controlplane/result_test.go", Digest: testDigest("red-one")},
			{Path: "controlplane/verification_test.go", Digest: testDigest("red-two")},
		},
	}
	state, err := AttachTestSeal(newTestVerification(t), seal, nil)
	if err != nil {
		t.Fatal(err)
	}
	observation := greenObservation(seal, "2026-08-23T20:01:00Z")
	// Same cardinality, but one sealed file was never actually observed.
	observation.Tests = []TestSealTest{seal.Tests[0], seal.Tests[0]}
	if _, err := acceptWithTests(state, observation); err == nil {
		t.Fatal("verification accepted an observation that skipped a sealed test")
	}
}

func TestVerificationDoesNotDemandGreenForNonAcceptance(t *testing.T) {
	state, _ := sealedVerification(t)
	blocked, err := ApplyVerification(state, VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: VerificationBlock,
		RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("blocked"), ResultDigest: testDigest("blocked-result"),
		Reason: "the verifier lacked authority to run the suite", At: "2026-08-23T20:03:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	if blocked.Outcome != VerificationBlocked {
		t.Fatalf("outcome = %q", blocked.Outcome)
	}
}

// A rejection releases another implementation pass, so the seal must be
// reconciled before the writer starts again. Block and cancel are terminal and
// may honestly report that nothing could be run.
func TestVerificationRejectionUnderASealRequiresObservedDigests(t *testing.T) {
	state, seal := sealedVerification(t)
	reject := func(tests *TestObservation) error {
		_, err := ApplyVerification(state, VerificationObservation{
			VerifierRoleID: "workflow-code-review", Decision: VerificationReject,
			RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("rejected"), ResultDigest: testDigest("rejected-result"),
			Reason: "the change does not satisfy the contract", Repairable: true,
			Usage: VerificationUsage{Tokens: 1000, DurationSeconds: 30}, At: "2026-08-23T20:03:00Z", Tests: tests,
		})
		return err
	}
	if err := reject(nil); err == nil {
		t.Fatal("a sealed rejection with no observed sealed-test digests was accepted")
	}
	observed := greenObservation(seal, "2026-08-23T20:01:00Z")
	if err := reject(observed); err != nil {
		t.Fatalf("a sealed rejection reporting intact digests was refused: %v", err)
	}
	drifted := greenObservation(seal, "2026-08-23T20:01:00Z")
	drifted.Tests[0].Digest = testDigest("weakened-test")
	if err := reject(drifted); err == nil {
		t.Fatal("a sealed rejection over drifted tests was accepted")
	}
}

func TestTestSealRejectsDuplicateSealedPaths(t *testing.T) {
	duplicate := TestSeal{
		SealedAt: "2026-08-23T20:00:30Z", RedCommandID: "command-red", Amendments: []TestSealAmendment{},
		Tests: []TestSealTest{
			{Path: "controlplane/result_test.go", Digest: testDigest("red-one")},
			{Path: "controlplane/result_test.go", Digest: testDigest("red-two")},
		},
	}
	if _, err := AttachTestSeal(newTestVerification(t), duplicate, nil); err == nil {
		t.Fatal("a seal listing the same path twice was accepted")
	}
	amended := TestSeal{
		SealedAt: "2026-08-23T20:00:30Z", RedCommandID: "command-red",
		Tests: []TestSealTest{{Path: "controlplane/result_test.go", Digest: testDigest("red-one")}},
		Amendments: []TestSealAmendment{{
			At: "2026-08-23T20:00:45Z", Reason: "extend the reproduction case",
			Before: []TestSealTest{{Path: "controlplane/result_test.go", Digest: testDigest("red-one")}},
			After: []TestSealTest{
				{Path: "controlplane/result_test.go", Digest: testDigest("amended-one")},
				{Path: "controlplane/result_test.go", Digest: testDigest("amended-two")},
			},
		}},
	}
	if _, err := AttachTestSeal(newTestVerification(t), amended, nil); err == nil {
		t.Fatal("an amendment listing the same path twice was accepted")
	}
}

// A useful correction must not be rejected solely because a former default
// capped the loop at two reviews. Explicit caller limits still terminate it.
func TestVerificationUsesCallerLimitsWithoutDefaultAttemptQuota(t *testing.T) {
	for _, limited := range []bool{false, true} {
		state := newTestVerification(t)
		if limited {
			state.Policy = VerificationPolicy{MaxPasses: 3, MaxRepairs: 2}
			if err := SealVerification(&state); err != nil {
				t.Fatal(err)
			}
		}
		for step := 0; step < 5; step++ {
			next, err := ApplyVerification(state, VerificationObservation{
				VerifierRoleID: "independent-reviewer", Decision: VerificationReject, Repairable: true,
				RepositoryDigest: state.RepositoryDigest, EvidenceDigest: testDigest("review"), ResultDigest: testDigest("review-result"),
				Reason: "a further correction is warranted", At: "2026-08-23T20:01:00Z",
			})
			if err != nil {
				t.Fatal(err)
			}
			if limited && step == 2 {
				if next.Outcome != VerificationExhausted {
					t.Fatalf("explicit limit ignored: %+v", next)
				}
				break
			}
			if next.Phase != VerificationAwaitingRepair {
				t.Fatalf("unexpected automatic stop: %+v", next)
			}
			state, err = ApplyRepair(next, RepairObservation{
				WriterRoleID: state.WriterRoleID, RepositoryDigest: testDigest(string(rune('a' + step))),
				EvidenceDigest: testDigest("repair-evidence"), ResultDigest: testDigest("repair-result"),
				Reason: "changed the implementation", At: "2026-08-23T20:02:00Z",
			})
			if err != nil {
				t.Fatal(err)
			}
		}
		if !limited && (state.Passes != 5 || state.Repairs != 5) {
			t.Fatalf("work was capped: %+v", state)
		}
	}
}
