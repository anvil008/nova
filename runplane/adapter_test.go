package runplane

import (
	"strings"
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
)

func adapterRequestFixture() AdapterRequest {
	return AdapterRequest{
		APIVersion: AdapterAPIVersion, AttemptID: "attempt-1", OuterAttempt: 1, GoalID: "goal-1",
		GenerationID: "generation-1", AssignmentID: "assignment-1", WriterRoleID: "workflow-executor",
		WriterResult: factoryDigest([]byte("writer")), RepositoryDigest: factoryDigest([]byte("repo")), EvidenceDigest: factoryDigest([]byte("evidence")),
		Inputs: []EvaluationInput{{Kind: InputTask, Digest: factoryDigest([]byte("task"))}, {Kind: InputRepository, Digest: factoryDigest([]byte("repo-input"))}},
		Budget: controlplane.VerificationUsage{Tokens: 10_000, DurationSeconds: 600},
	}
}

func TestAdapterOneAttemptOneFinalPatch(t *testing.T) {
	state, err := StartAdapter(adapterRequestFixture(), "2026-08-23T20:00:00Z")
	if err != nil {
		t.Fatal(err)
	}
	state, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationAccept,
		RepositoryDigest: state.Verification.RepositoryDigest, EvidenceDigest: factoryDigest([]byte("review")), ResultDigest: factoryDigest([]byte("review-result")),
		Reason: "all required evidence is current", At: "2026-08-23T20:01:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	state, err = EmitAdapterFinal(state, "diff --git a/a b/a\n", "verified patch", "2026-08-23T20:02:00Z")
	if err != nil {
		t.Fatal(err)
	}
	if state.FinalEmissions != 1 || state.Final.Disposition != controlplane.DispositionSucceeded || state.Final.PatchDigest == "" {
		t.Fatalf("final state=%+v", state)
	}
	if _, err := EmitAdapterFinal(state, "another", "another", "2026-08-23T20:03:00Z"); err == nil {
		t.Fatal("second final output accepted")
	}
}

func TestAdapterContainsTwoInternalPassesAndOneRepair(t *testing.T) {
	state, err := StartAdapter(adapterRequestFixture(), "2026-08-23T20:00:00Z")
	if err != nil {
		t.Fatal(err)
	}
	state, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationReject, Repairable: true,
		RepositoryDigest: state.Verification.RepositoryDigest, EvidenceDigest: factoryDigest([]byte("review-1")), ResultDigest: factoryDigest([]byte("result-1")), Reason: "focused repair", At: "2026-08-23T20:01:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	state, err = ApplyAdapterRepair(state, controlplane.RepairObservation{
		WriterRoleID: state.Verification.WriterRoleID, RepositoryDigest: factoryDigest([]byte("repo-2")), EvidenceDigest: factoryDigest([]byte("repair")), ResultDigest: factoryDigest([]byte("repair-result")), Reason: "repaired", At: "2026-08-23T20:02:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	state, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationReject,
		RepositoryDigest: state.Verification.RepositoryDigest, EvidenceDigest: factoryDigest([]byte("review-2")), ResultDigest: factoryDigest([]byte("result-2")), Reason: "still incomplete", At: "2026-08-23T20:03:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	if state.Verification.Outcome != controlplane.VerificationExhausted || state.Verification.Passes != 2 || state.Verification.Repairs != 1 {
		t.Fatalf("bounded state=%+v", state.Verification)
	}
	if _, err := ApplyAdapterVerification(state, controlplane.VerificationObservation{}); err == nil {
		t.Fatal("third pass accepted")
	}
	state, err = EmitAdapterFinal(state, "", "verification exhausted without a verified patch", "2026-08-23T20:04:00Z")
	if err != nil || state.Final.Disposition != controlplane.DispositionFailed {
		t.Fatalf("final=%+v err=%v", state.Final, err)
	}
}

func TestAdapterRejectsForbiddenDataBeforeWork(t *testing.T) {
	for _, kind := range []EvaluationInputKind{InputScorerOutput, InputHiddenTests, InputReferencePatch, InputOracle, InputPriorSolution} {
		request := adapterRequestFixture()
		request.Inputs = append(request.Inputs, EvaluationInput{Kind: kind, Digest: factoryDigest([]byte(kind))})
		if _, err := StartAdapter(request, "2026-08-23T20:00:00Z"); err == nil || !strings.Contains(err.Error(), "forbidden") {
			t.Fatalf("input %q error=%v", kind, err)
		}
	}
	request := adapterRequestFixture()
	request.OuterAttempt = 2
	if _, err := StartAdapter(request, "2026-08-23T20:00:00Z"); err == nil {
		t.Fatal("second outer attempt accepted")
	}
}

func TestAdapterMissingProofAndNoProgressAreTruthfulNonSuccess(t *testing.T) {
	state, err := StartAdapter(adapterRequestFixture(), "2026-08-23T20:00:00Z")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ApplyAdapterVerification(state, controlplane.VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationAccept,
		RepositoryDigest: state.Verification.RepositoryDigest, ResultDigest: factoryDigest([]byte("result")), Reason: "missing proof", At: "2026-08-23T20:01:00Z",
	}); err == nil {
		t.Fatal("missing verification evidence accepted")
	}
	state, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
		VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationReject, Repairable: true,
		RepositoryDigest: state.Verification.RepositoryDigest, EvidenceDigest: factoryDigest([]byte("review")), ResultDigest: factoryDigest([]byte("result")), Reason: "repair", At: "2026-08-23T20:01:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	state, err = ApplyAdapterRepair(state, controlplane.RepairObservation{
		WriterRoleID: state.Verification.WriterRoleID, RepositoryDigest: state.Verification.RepositoryDigest,
		EvidenceDigest: state.Verification.EvidenceDigest, ResultDigest: factoryDigest([]byte("same")), Reason: "no change", At: "2026-08-23T20:02:00Z",
	})
	if err != nil {
		t.Fatal(err)
	}
	if state.Verification.Outcome != controlplane.VerificationNoProgress {
		t.Fatal("no-progress not terminal")
	}
	if _, err := EmitAdapterFinal(state, "unexpected patch", "uncertain", "2026-08-23T20:03:00Z"); err == nil {
		t.Fatal("non-success patch accepted")
	}
}
