package guard

import (
	"encoding/json"
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
)

func (h *harness) statusJSON() Status {
	h.t.Helper()
	code, stdout, stderr := h.run("status", "--json")
	if code != 0 {
		h.t.Fatalf("status --json exit %d: %s", code, stderr)
	}
	var report Status
	if err := json.Unmarshal([]byte(stdout), &report); err != nil {
		h.t.Fatalf("decode status %q: %v", stdout, err)
	}
	return report
}

func recordsByKind(t *testing.T, records []controlplane.GuardRecord) map[string]controlplane.GuardRecord {
	t.Helper()
	byKind := make(map[string]controlplane.GuardRecord, len(records))
	for _, record := range records {
		if _, duplicate := byKind[record.Kind]; duplicate {
			t.Fatalf("duplicate guard record kind %q", record.Kind)
		}
		byKind[record.Kind] = record
	}
	return byKind
}

// The orchestrator has to be able to tell a commandId anvil-guard produced from
// one an agent typed, so `status --json` publishes the records with their
// evidence rather than a bare boolean.
func TestStatusJSONListsTheRecordsGuardProduced(t *testing.T) {
	h := newHarness(t)
	if records := h.statusJSON().Records; len(records) != 0 {
		t.Fatalf("an unsealed repository reported guard records: %+v", records)
	}

	h.seal()
	if code, _, stderr := h.run("verify", "--green-command", "true"); code != 0 {
		t.Fatalf("verify exit %d: %s", code, stderr)
	}
	h.write("findings.txt", "read the real diff\n")
	if code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt"); code != 0 {
		t.Fatalf("diff-review exit %d: %s", code, stderr)
	}

	report := h.statusJSON()
	byKind := recordsByKind(t, report.Records)
	red, ok := byKind[controlplane.GuardRecordSealRed]
	if !ok || red.CommandID != report.Seal.Red.CommandID || red.Evidence.ExitCode == 0 {
		t.Fatalf("seal-red record = %+v", red)
	}
	green, ok := byKind[controlplane.GuardRecordGreen]
	if !ok || green.CommandID != report.Green.CommandID || green.Evidence.ExitCode != 0 {
		t.Fatalf("green record = %+v", green)
	}
	review, ok := byKind[controlplane.GuardRecordDiffReview]
	if !ok || review.CommandID != report.DiffReview.CommandID || review.Evidence.ExitCode != 0 {
		t.Fatalf("diff-review record = %+v", review)
	}
	for _, record := range report.Records {
		if record.Evidence.CommandID != record.CommandID || record.Evidence.ArgvDigest == "" || record.Evidence.StartedAt == "" {
			t.Fatalf("record %q carries no command evidence: %+v", record.Kind, record)
		}
	}
}

// Snapshot is what the run-plane supervisor reads directly out of the state
// directory, so it must agree with what `status --json` prints.
func TestSnapshotMatchesTheStatusRecords(t *testing.T) {
	h := newHarness(t)
	absent, err := Snapshot(h.resolvedRepository())
	if err != nil {
		t.Fatal(err)
	}
	if absent != nil {
		t.Fatalf("an unsealed repository produced a snapshot: %+v", absent)
	}

	h.seal()
	if code, _, stderr := h.run("verify", "--green-command", "true"); code != 0 {
		t.Fatalf("verify exit %d: %s", code, stderr)
	}
	snapshot, err := Snapshot(h.resolvedRepository())
	if err != nil {
		t.Fatal(err)
	}
	if snapshot == nil {
		t.Fatal("a sealed repository produced no snapshot")
	}
	fromStatus := recordsByKind(t, h.statusJSON().Records)
	fromSnapshot := recordsByKind(t, snapshot.Records)
	for kind, record := range fromStatus {
		if fromSnapshot[kind] != record {
			t.Fatalf("snapshot %q = %+v, status = %+v", kind, fromSnapshot[kind], record)
		}
	}
	if len(fromSnapshot) != len(fromStatus) {
		t.Fatalf("snapshot records %+v differ from status records %+v", snapshot.Records, fromStatus)
	}
}
