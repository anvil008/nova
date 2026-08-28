package guard

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// statusJSONMap reads `status` as a raw document so the assertions do not
// depend on the typed Status growing fields before the contract is in force.
func (h *harness) statusJSONMap() map[string]any {
	h.t.Helper()
	code, stdout, stderr := h.run("status", "--json")
	if code != 0 {
		h.t.Fatalf("status exit %d: %s", code, stderr)
	}
	var report map[string]any
	if err := json.Unmarshal([]byte(stdout), &report); err != nil {
		h.t.Fatalf("decode status %q: %v", stdout, err)
	}
	return report
}

func (h *harness) greenRecorded() bool {
	h.t.Helper()
	_, err := os.Stat(filepath.Join(h.stateDirectory(), greenFileName))
	return err == nil
}

// verify-rejects-mismatched-green-argv: `false` then `true` is the original
// hole. The seal binds the red argv; a green argv with a different digest is
// refused, naming both digests, and no green evidence is written.
func TestVerifyRejectsMismatchedGreenArgv(t *testing.T) {
	h := newHarness(t)
	h.seal()
	code, _, stderr := h.run("verify", "--green-command", "true")
	if code == 0 {
		t.Fatal("verify accepted a green argv that differs from the sealed red argv")
	}
	seal := h.readSeal()
	greenDigest := argvDigest([]string{"true"})
	if !strings.Contains(stderr, seal.Red.ArgvDigest) || !strings.Contains(stderr, greenDigest) {
		t.Fatalf("stderr %q does not name both the sealed digest %s and the offered digest %s", stderr, seal.Red.ArgvDigest, greenDigest)
	}
	if h.greenRecorded() {
		t.Fatal("a refused verify wrote green evidence")
	}
	if ready, _ := h.statusJSONMap()["ready"].(bool); ready {
		t.Fatal("status reports ready after a refused verify")
	}
}

// verify-accepts-same-argv: the bound argv fails at seal time and passes at
// verify time; status reports green and the digest the seal bound.
func TestVerifyAcceptsSameArgv(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.verify()
	seal := h.readSeal()
	if seal.Red.ArgvDigest != argvDigest(boundArgv) {
		t.Fatalf("seal red argv digest %s != %s", seal.Red.ArgvDigest, argvDigest(boundArgv))
	}
	report := h.statusJSONMap()
	green, _ := report["green"].(map[string]any)
	if green == nil || green["exitCode"].(float64) != 0 || green["argvDigest"] != seal.Red.ArgvDigest {
		t.Fatalf("status green = %v, want exit 0 bound to %s", green, seal.Red.ArgvDigest)
	}
	bound, _ := report["boundArgv"].(map[string]any)
	if bound == nil || bound["digest"] != seal.Red.ArgvDigest {
		t.Fatalf("status boundArgv = %v, want digest %s", bound, seal.Red.ArgvDigest)
	}
	argv, _ := bound["argv"].([]any)
	if len(argv) != len(boundArgv) || argv[len(argv)-1] != boundArgv[len(boundArgv)-1] {
		t.Fatalf("status boundArgv.argv = %v, want %v", argv, boundArgv)
	}
}

// verify-detects-sealed-test-edit-during-green: a green command that rewrites a
// sealed test and restores it byte for byte before exiting leaves the digest
// intact, so the pre-run check alone would pass it. The run itself must be
// observed.
func TestVerifyDetectsSealedTestEditDuringGreen(t *testing.T) {
	h := newHarness(t)
	h.write("tamper.sh", strings.Join([]string{
		"#!/bin/sh",
		"test -f .green || exit 1",
		"cp pkg/thing_test.go saved",
		"echo '// weakened' >> pkg/thing_test.go",
		"cp saved pkg/thing_test.go",
		"exit 0",
	}, "\n")+"\n")
	argv := []string{"sh", "tamper.sh"}
	if code, _, stderr := h.run(append([]string{"seal", "--tests", "**/*_test.go", "--red-command"}, argv...)...); code != 0 {
		t.Fatalf("seal exit %d: %s", code, stderr)
	}
	h.write(".green", "")
	code, _, stderr := h.run(append([]string{"verify", "--green-command"}, argv...)...)
	if code == 0 {
		t.Fatal("verify accepted a green run that rewrote a sealed test")
	}
	if !strings.Contains(stderr, "pkg/thing_test.go") || !strings.Contains(stderr, "during") {
		t.Fatalf("stderr %q does not name the test changed during the run", stderr)
	}
	if h.greenRecorded() {
		t.Fatal("a tampering green run still wrote green evidence")
	}
}

// A seal written before the binding existed carries no boundArgv; verify then
// binds to the red evidence's argvDigest, which every seal has always recorded.
func TestVerifyBindsLegacySealsToTheRedArgvDigest(t *testing.T) {
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
	delete(legacy, "boundArgv")
	encoded, err := json.Marshal(legacy)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(sealPath, encoded, 0o600); err != nil {
		t.Fatal(err)
	}
	if code, _, stderr := h.run("verify", "--green-command", "true"); code == 0 {
		t.Fatalf("legacy seal accepted a mismatched green argv: %s", stderr)
	}
	h.verify()
	bound, _ := h.statusJSONMap()["boundArgv"].(map[string]any)
	if bound == nil || bound["digest"] != h.readSeal().Red.ArgvDigest {
		t.Fatalf("legacy seal status boundArgv = %v", bound)
	}
}

// An amendment moves the tests, not the command: the binding survives reseal.
func TestResealKeepsTheBoundArgv(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.write("pkg/thing_test.go", "package pkg\n\nfunc TestThing(t *testing.T) { t.Log(\"amended\") }\n")
	if code, _, stderr := h.run("reseal", "--reason", "sharpen the assertion"); code != 0 {
		t.Fatalf("reseal exit %d: %s", code, stderr)
	}
	if code, _, stderr := h.run("verify", "--green-command", "true"); code == 0 {
		t.Fatalf("resealed seal accepted a mismatched green argv: %s", stderr)
	}
	h.verify()
}
