package guard

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/anvil008/workcell/controlplane"
)

func (h *harness) baselineSeal(command ...string) {
	h.t.Helper()
	args := append([]string{"seal", "--tests", "**/*_test.go", "--green-baseline"}, command...)
	if code, _, stderr := h.run(args...); code != 0 {
		h.t.Fatalf("baseline seal exit %d: %s", code, stderr)
	}
}

func TestBaselineSealRequiresGreenAndCommandsAreExclusive(t *testing.T) {
	failing := newHarness(t)
	code, _, stderr := failing.run("seal", "--tests", "**/*_test.go", "--green-baseline", "false")
	if code == 0 || !strings.Contains(stderr, "requires exit 0") {
		t.Fatalf("baseline seal accepted a failing command: exit %d stderr %q", code, stderr)
	}
	if _, err := os.Stat(filepath.Join(failing.stateDirectory(), sealFileName)); !os.IsNotExist(err) {
		t.Fatalf("a rejected baseline seal still wrote state: %v", err)
	}

	passing := newHarness(t)
	passing.baselineSeal("true")
	status := passing.statusJSON()
	if status.SealKind != SealKindBaseline || status.Seal == nil || status.Seal.Kind != SealKindBaseline {
		t.Fatalf("baseline kind not reported: %+v", status)
	}
	if status.Seal.Red.ExitCode != 0 {
		t.Fatalf("baseline evidence = %+v", status.Seal.Red)
	}
	records := recordsByKind(t, status.Records)
	if record := records[controlplane.GuardRecordSealBaseline]; record.CommandID != status.Seal.Red.CommandID || record.Evidence.ExitCode != 0 {
		t.Fatalf("seal-baseline record = %+v", record)
	}

	exclusive := newHarness(t)
	code, _, stderr = exclusive.run("seal", "--tests", "**/*_test.go", "--red-command", "false", "--green-baseline", "true")
	if code == 0 || !strings.Contains(stderr, "exactly one") {
		t.Fatalf("seal accepted both command kinds: exit %d stderr %q", code, stderr)
	}
}

func TestRedSealStillRejectsGreenAndReportsItsKind(t *testing.T) {
	h := newHarness(t)
	code, _, stderr := h.run("seal", "--tests", "**/*_test.go", "--red-command", "true")
	if code == 0 || !strings.Contains(stderr, "non-zero") {
		t.Fatalf("red seal accepted a green command: exit %d stderr %q", code, stderr)
	}

	h.seal()
	status := h.statusJSON()
	if status.SealKind != SealKindRed || status.Seal == nil || status.Seal.Kind != SealKindRed {
		t.Fatalf("red kind not reported: %+v", status)
	}
}

func TestLegacySealWithoutKindBehavesAsRed(t *testing.T) {
	h := newHarness(t)
	h.seal()
	sealPath := filepath.Join(h.stateDirectory(), sealFileName)
	raw, err := os.ReadFile(sealPath)
	if err != nil {
		t.Fatal(err)
	}
	var legacy map[string]any
	if err := json.Unmarshal(raw, &legacy); err != nil {
		t.Fatal(err)
	}
	delete(legacy, "kind")
	encoded, err := json.Marshal(legacy)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(sealPath, encoded, 0o600); err != nil {
		t.Fatal(err)
	}

	if status := h.statusJSON(); status.SealKind != SealKindRed {
		t.Fatalf("legacy seal kind = %q, want %q", status.SealKind, SealKindRed)
	}
	h.write("pkg/thing_test.go", "package pkg\n\n// amended legacy red test\n")
	if code, _, stderr := h.run("reseal", "--reason", "strengthen the legacy red test"); code != 0 {
		t.Fatalf("legacy red reseal exit %d: %s", code, stderr)
	}
	if code, _, stderr := h.stop(); code == 0 || !strings.Contains(stderr, "no green evidence") {
		t.Fatalf("legacy red Stop before verify: exit %d stderr %q", code, stderr)
	}

	h.verify()
	h.write("findings.txt", "reviewed legacy red seal\n")
	if code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt"); code != 0 {
		t.Fatalf("diff-review exit %d: %s", code, stderr)
	}
	if code, stdout, stderr := h.stop(); code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("verified legacy red seal refused Stop: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
}

func TestBaselineFlowRefusesHandoffAndStopBeforeSeal(t *testing.T) {
	h := newHarness(t)
	if code, _, stderr := h.run("handoff", "--to", "builder"); code == 0 || !strings.Contains(stderr, "nothing to hand off: seal the tests first") {
		t.Fatalf("handoff without baseline seal: exit %d stderr %q", code, stderr)
	}
	if code, _, stderr := h.stop(); code == 0 || !strings.Contains(stderr, "no seal; run `tdd-guard seal --tests <globs> --red-command <argv...>` (or `--green-baseline <argv...>` for a refactor) first") {
		t.Fatalf("Stop without baseline seal or green: exit %d stderr %q", code, stderr)
	}
}

func TestBaselineSealUsesTheOrdinaryVerifyAndStopGate(t *testing.T) {
	h := newHarness(t)
	h.baselineSeal("true")
	if code, _, stderr := h.run("handoff", "--to", "builder"); code != 0 {
		t.Fatalf("baseline handoff exit %d: %s", code, stderr)
	}

	h.write("pkg/thing.go", "package pkg\n\nfunc Thing() int { return 1 }\n")
	if code, _, stderr := h.run("verify", "--green-command", "true"); code != 0 {
		t.Fatalf("baseline verify exit %d: %s", code, stderr)
	}
	h.write("findings.txt", "reviewed baseline-sealed refactor\n")
	if code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt"); code != 0 {
		t.Fatalf("diff-review exit %d: %s", code, stderr)
	}
	if code, stdout, stderr := h.stop(); code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("satisfied baseline contract refused Stop: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
	if status := h.statusJSON(); !status.Ready || status.Green == nil {
		t.Fatalf("baseline state not ready after GREEN and diff review: %+v", status)
	}
}

func TestBaselineSealedPathIsDeniedBeforeAnEdit(t *testing.T) {
	h := newHarness(t)
	h.baselineSeal("true")
	payload := `{"hook_event_name":"PreToolUse","tool_name":"apply_patch","tool_input":{"input":"*** Begin Patch\n*** Update File: pkg/thing_test.go\n*** End Patch\n"},"cwd":"` + h.repository + `","turn_id":"baseline"}`
	code, stdout, stderr := h.runStdin(payload, "hook", "--harness", "codex", "--event", "PreToolUse")
	if code != 0 || stderr != "" || !strings.Contains(stdout, "block") || !strings.Contains(stdout, "sealed") {
		t.Fatalf("baseline-sealed edit was not denied: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
}

func TestBaselineSealCannotBeResealed(t *testing.T) {
	h := newHarness(t)
	h.baselineSeal("true")
	h.write("pkg/thing_test.go", "package pkg\n\n// amended by the refactor\n")
	code, _, stderr := h.run("reseal", "--reason", "make the refactor easier")
	if code == 0 || !strings.Contains(stderr, "a refactor never amends its tests") {
		t.Fatalf("baseline reseal was not refused: exit %d stderr %q", code, stderr)
	}
	if status := h.statusJSON(); len(status.ChangedTests) != 1 {
		t.Fatalf("refused reseal adopted the changed test: %+v", status.ChangedTests)
	}
}
