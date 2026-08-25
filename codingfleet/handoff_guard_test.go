package codingfleet

import (
	"strings"
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
)

// forgedEvidence is the attack the reconciliation used to pass: one well-formed
// commandId, invented by the agent, repeated consistently across the handoff's
// tests, the result's commands, and the result's checks. Both records are
// parsed from text the same agent wrote, so nothing inside them disagrees.
func forgedEvidence(commandID string) (AgentHandoff, controlplane.WorkflowResult) {
	handoff := AgentHandoff{
		Tests: []AgentHandoffTest{{Name: "go test -race ./...", Passed: true, CommandID: commandID}},
	}
	result := controlplane.WorkflowResult{
		Commands: []controlplane.CommandEvidence{{
			CommandID: commandID, ArgvDigest: "sha256:argv", ExitCode: 0,
			StartedAt: "2026-08-23T20:00:00Z", FinishedAt: "2026-08-23T20:00:01Z",
			StdoutDigest: "sha256:out", StderrDigest: "sha256:err",
		}},
		Checks: []controlplane.CheckEvidence{{
			CheckID: "unit", CommandID: commandID, Passed: true, Current: true, EvidenceDigest: "sha256:proof",
		}},
	}
	return handoff, result
}

func guardSnapshot() *controlplane.GuardSnapshot {
	return &controlplane.GuardSnapshot{
		APIVersion: controlplane.GuardSnapshotAPIVersion,
		Repository: "/repositories/alpha",
		Records: []controlplane.GuardRecord{
			{Kind: controlplane.GuardRecordSealRed, CommandID: "cmd-red", Evidence: controlplane.CommandEvidence{
				CommandID: "cmd-red", ArgvDigest: "sha256:red-argv", ExitCode: 1,
				StartedAt: "2026-08-23T19:59:00Z", FinishedAt: "2026-08-23T19:59:10Z",
				StdoutDigest: "sha256:red-out", StderrDigest: "sha256:red-err",
			}},
			{Kind: controlplane.GuardRecordGreen, CommandID: "cmd-green", Evidence: controlplane.CommandEvidence{
				CommandID: "cmd-green", ArgvDigest: "sha256:green-argv", ExitCode: 0,
				StartedAt: "2026-08-23T20:00:00Z", FinishedAt: "2026-08-23T20:00:01Z",
				StdoutDigest: "sha256:green-out", StderrDigest: "sha256:green-err",
			}},
			{Kind: controlplane.GuardRecordDiffReview, CommandID: "cmd-diff", Evidence: controlplane.CommandEvidence{
				CommandID: "cmd-diff", ArgvDigest: "sha256:diff-argv", ExitCode: 0,
				StartedAt: "2026-08-23T20:00:02Z", FinishedAt: "2026-08-23T20:00:03Z",
				StdoutDigest: "sha256:diff-out", StderrDigest: "sha256:diff-err",
			}},
		},
	}
}

func TestReconcileHandoffTestsRejectsAForgedCommandID(t *testing.T) {
	handoff, result := forgedEvidence("cmd-invented")

	// Without guard state there is nothing to resolve against, which is exactly
	// the single-author problem: the forgery is internally consistent.
	if err := ReconcileHandoffTests(handoff, result, nil); err != nil {
		t.Fatalf("the pre-guard contract changed behaviour: %v", err)
	}

	err := ReconcileHandoffTests(handoff, result, guardSnapshot())
	if err == nil {
		t.Fatal("a fabricated commandId with no guard record satisfied the test contract")
	}
	if !strings.Contains(err.Error(), "cmd-invented") {
		t.Fatalf("error %v does not name the unresolved commandId", err)
	}
}

func TestReconcileHandoffTestsAcceptsAGuardProducedCommandID(t *testing.T) {
	// An honest reporter's CommandEvidence repeats the guard record, so the id
	// resolves and the run behind it is the one the guard actually performed.
	handoff, result := honestRun(guardRecordOfKind(t, controlplane.GuardRecordGreen), "go test -race ./...")
	if err := ReconcileHandoffTests(handoff, result, guardSnapshot()); err != nil {
		t.Fatalf("a commandId anvil-guard produced was rejected: %v", err)
	}
}

func TestReconcileHandoffTestsRejectsAClaimThatContradictsTheGuardRecord(t *testing.T) {
	// The red run is real, and it failed. Citing it as a pass is the same lie
	// with a real identifier attached -- and every digest still matches, so the
	// guard record's exit code is the only thing that catches it.
	handoff, result := honestRun(guardRecordOfKind(t, controlplane.GuardRecordSealRed), "go test")
	handoff.Tests[0].Passed = true
	if err := ReconcileHandoffTests(handoff, result, guardSnapshot()); err == nil {
		t.Fatal("a passing claim resolved to a failing guard record")
	}

	// The symmetric case: a cited record that passed cannot back a failure.
	handoff, result = honestRun(guardRecordOfKind(t, controlplane.GuardRecordGreen), "go test")
	handoff.Tests[0].Passed = false
	if err := ReconcileHandoffTests(handoff, result, guardSnapshot()); err == nil {
		t.Fatal("a failing claim resolved to a passing guard record")
	}
}
