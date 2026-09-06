package guard

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func (h *harness) review() {
	h.t.Helper()
	findings := filepath.Join(h.t.TempDir(), "findings.txt")
	if err := os.WriteFile(findings, []byte("Read the current diff and checked the behavior.\n"), 0o600); err != nil {
		h.t.Fatal(err)
	}
	if code, _, stderr := h.run("diff-review", "record", "--findings", findings); code != 0 {
		h.t.Fatalf("review: %s", stderr)
	}
}

func TestGreenCannotBeRefreshedByReviewingARegression(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.verify()
	h.review()
	if !h.status().Ready {
		t.Fatal("initial passing implementation was not ready")
	}
	h.write("pkg/thing.go", "package pkg\n// regression after GREEN\n")
	h.review()
	status := h.status()
	if status.Ready || !status.GreenStale || status.DiffStale {
		t.Fatalf("a fresh review revived stale GREEN: %+v", status)
	}
	if code, _, stderr := h.stop(); code != 2 || !strings.Contains(stderr, "green evidence is stale") {
		t.Fatalf("Stop accepted the regression: %d %s", code, stderr)
	}
	h.verify()
	if !h.status().Ready {
		t.Fatal("reverification of the unchanged reviewed tree should recover readiness")
	}
}

func TestFailedVerificationDiscardsPreviousGreenEvenOnTheSameTree(t *testing.T) {
	h := newHarness(t)
	argv := []string{"sh", "-c", `test "$WORKCELL_VERIFY_RESULT" = pass`}
	t.Setenv("WORKCELL_VERIFY_RESULT", "fail")
	if code, _, stderr := h.run(append([]string{"seal", "--tests", "**/*_test.go", "--red-command"}, argv...)...); code != 0 {
		t.Fatal(stderr)
	}
	t.Setenv("WORKCELL_VERIFY_RESULT", "pass")
	if code, _, stderr := h.run(append([]string{"verify", "--green-command"}, argv...)...); code != 0 {
		t.Fatal(stderr)
	}
	h.review()
	t.Setenv("WORKCELL_VERIFY_RESULT", "fail")
	if code, _, _ := h.run(append([]string{"verify", "--green-command"}, argv...)...); code == 0 {
		t.Fatal("failing rerun was accepted")
	}
	if status := h.status(); status.Ready || status.Green != nil {
		t.Fatalf("failed attempt retained an earlier success: %+v", status)
	}
	if code, _, _ := h.stop(); code != 2 {
		t.Fatal("failed verification inherited the specifier Stop relaxation")
	}
}

func TestFailedFirstVerificationEndsSpecifierStopRelaxation(t *testing.T) {
	h := newHarness(t)
	h.seal()
	if code, _, stderr := h.run("handoff", "--to", "builder"); code != 0 {
		t.Fatal(stderr)
	}
	if code, _, _ := h.stop(); code != 0 {
		t.Fatal("specifier cannot hand off an unchanged sealed tree")
	}
	if code, _, _ := h.run(append([]string{"verify", "--green-command"}, boundArgv...)...); code == 0 {
		t.Fatal("expected first verification to fail")
	}
	if code, _, _ := h.stop(); code != 2 {
		t.Fatal("failed verification inherited the specifier Stop relaxation")
	}
}

func TestVerificationRejectsSourceChangesDuringTheCommand(t *testing.T) {
	h := newHarness(t)
	argv := []string{"sh", "-c", "test -f .green || exit 1; printf changed > pkg/thing.go"}
	if code, _, stderr := h.run(append([]string{"seal", "--tests", "**/*_test.go", "--red-command"}, argv...)...); code != 0 {
		t.Fatal(stderr)
	}
	h.write(".green", "")
	if code, _, stderr := h.run(append([]string{"verify", "--green-command"}, argv...)...); code == 0 || !strings.Contains(stderr, "implementation changed") {
		t.Fatalf("mutating command was accepted: %d %s", code, stderr)
	}
	if h.status().Green != nil {
		t.Fatal("mutating command left GREEN")
	}
}

func TestLegacyGreenAndMovedBaseRequireReverification(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.verify()
	h.review()
	legacy := h.greenRecord()
	delete(legacy, "base")
	if err := writeJSON(filepath.Join(h.stateDirectory(), greenFileName), legacy); err != nil {
		t.Fatal(err)
	}
	if status := h.status(); status.Ready || !status.GreenStale {
		t.Fatal("unbound legacy GREEN was trusted")
	}
	h.verify()
	h.commit("same content, different base")
	if status := h.status(); status.Ready || !status.GreenStale || !status.DiffStale {
		t.Fatal("moved base retained old evidence")
	}
}
