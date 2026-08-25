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
