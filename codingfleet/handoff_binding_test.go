package codingfleet

import (
	"strings"
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
)

// honestRun is what a truthful reporter produces for one guard-recorded run:
// the agent's own CommandEvidence repeats the guard record verbatim.
func honestRun(record controlplane.GuardRecord, name string) (AgentHandoff, controlplane.WorkflowResult) {
	handoff := AgentHandoff{
		Tests: []AgentHandoffTest{{Name: name, Passed: record.Evidence.ExitCode == 0, CommandID: record.CommandID}},
	}
	result := controlplane.WorkflowResult{
		Commands: []controlplane.CommandEvidence{record.Evidence},
		Checks: []controlplane.CheckEvidence{{
			CheckID: "unit", CommandID: record.CommandID, Passed: true, Current: true, EvidenceDigest: "sha256:proof",
		}},
	}
	return handoff, result
}

func guardRecordOfKind(t *testing.T, kind string) controlplane.GuardRecord {
	t.Helper()
	for _, record := range guardSnapshot().Records {
		if record.Kind == kind {
			return record
		}
	}
	t.Fatalf("the fixture carries no %q record", kind)
	return controlplane.GuardRecord{}
}

// B1: the exploit. `diff-review` is a real, guard-produced, exit-zero record of
// `git diff HEAD`. Citing it as the command that proved the test suite passed
// used to validate, because only the exit code was ever compared.
func TestReconcileHandoffTestsRejectsADiffReviewCitedAsATestRun(t *testing.T) {
	record := guardRecordOfKind(t, controlplane.GuardRecordDiffReview)
	handoff, result := honestRun(record, "go test -race ./...")
	err := ReconcileHandoffTests(handoff, result, guardSnapshot())
	if err == nil {
		t.Fatal("the diff-review record was accepted as proof that the test suite passed")
	}
	if !strings.Contains(err.Error(), record.CommandID) {
		t.Fatalf("error %v does not name the misused commandId", err)
	}
}

// B2: the claim has to be bound to the record. One honest run backed an
// unlimited number of named checks with invented argv digests, because the
// agent's own CommandEvidence was never compared against the guard's.
func TestReconcileHandoffTestsRejectsEvidenceThatContradictsTheGuardRecord(t *testing.T) {
	record := guardRecordOfKind(t, controlplane.GuardRecordGreen)

	forgedArgv := func() (AgentHandoff, controlplane.WorkflowResult) {
		handoff, result := honestRun(record, "go test -race ./...")
		result.Commands[0].ArgvDigest = "sha256:golangci-lint-argv"
		return handoff, result
	}
	handoff, result := forgedArgv()
	if err := ReconcileHandoffTests(handoff, result, guardSnapshot()); err == nil {
		t.Fatal("an agent-invented argv digest was accepted against a guard record with a different one")
	}

	handoff, result = honestRun(record, "go test -race ./...")
	result.Commands[0].StdoutDigest = "sha256:invented-out"
	if err := ReconcileHandoffTests(handoff, result, guardSnapshot()); err == nil {
		t.Fatal("an agent-invented stdout digest was accepted against a guard record with a different one")
	}

	// The exit code that decides the claim must come from the guard record.
	failing := guardRecordOfKind(t, controlplane.GuardRecordSealRed)
	handoff, result = honestRun(failing, "go test -race ./...")
	handoff.Tests[0].Passed = true
	result.Commands[0].ExitCode = 0
	if err := ReconcileHandoffTests(handoff, result, guardSnapshot()); err == nil {
		t.Fatal("the agent's own exit code overrode the guard record's")
	}
}

// B3: one run, one named check. Otherwise a single honest `anvil-guard verify`
// satisfies every entry in RequiredChecks at once.
func TestReconcileHandoffTestsRejectsOneRunBackingSeveralNamedChecks(t *testing.T) {
	record := guardRecordOfKind(t, controlplane.GuardRecordGreen)
	handoff, result := honestRun(record, "go test -race ./...")
	handoff.Tests = append(handoff.Tests, AgentHandoffTest{
		Name: "golangci-lint run", Passed: true, CommandID: record.CommandID,
	})
	err := ReconcileHandoffTests(handoff, result, guardSnapshot())
	if err == nil {
		t.Fatal("one guard record satisfied two unrelated named checks")
	}
	if !strings.Contains(err.Error(), "golangci-lint run") {
		t.Fatalf("error %v does not name the second claim", err)
	}
}

// B4: the honest path still validates, including a failing claim resolved
// against the sealed red run.
func TestReconcileHandoffTestsAcceptsRunsBoundToTheirGuardRecords(t *testing.T) {
	handoff, result := honestRun(guardRecordOfKind(t, controlplane.GuardRecordGreen), "go test -race ./...")
	if err := ReconcileHandoffTests(handoff, result, guardSnapshot()); err != nil {
		t.Fatalf("an honest green run was rejected: %v", err)
	}

	red := guardRecordOfKind(t, controlplane.GuardRecordSealRed)
	handoff, result = honestRun(red, "go test -race ./... (red)")
	if handoff.Tests[0].Passed {
		t.Fatal("the sealed red run must be a failing claim")
	}
	if err := ReconcileHandoffTests(handoff, result, guardSnapshot()); err != nil {
		t.Fatalf("an honest red run was rejected: %v", err)
	}
}
