package guard

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
)

// fakeAstGrep installs a stand-in for the ast-grep binary that counts literal
// matches of the pattern across the paths it is handed, in the JSON shape the
// real tool emits. It lets the pass/fail semantics be exercised on a host that
// has not installed the structural verifier.
func (h *harness) fakeAstGrep() {
	h.t.Helper()
	binDir := h.t.TempDir()
	script := filepath.Join(binDir, "ast-grep")
	body := `#!/usr/bin/env bash
pattern=""
mode=""
declare -a paths
for a in "$@"; do
  if [ "$take" = "1" ]; then pattern="$a"; take=""; continue; fi
  case "$a" in
    --pattern) take="1";;
    --json*) mode="paths";;
    run) ;;
    *) if [ "$mode" = "paths" ]; then paths+=("$a"); fi;;
  esac
done
count=0
for p in "${paths[@]}"; do
  if [ -f "$p" ]; then
    c=$(grep -c -F -- "$pattern" "$p" 2>/dev/null); c=${c:-0}
    count=$((count + c))
  elif [ -d "$p" ]; then
    c=$(grep -rc -F -- "$pattern" "$p" 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}'); c=${c:-0}
    count=$((count + c))
  fi
done
printf '['
for ((j=0;j<count;j++)); do
  if [ $j -gt 0 ]; then printf ','; fi
  printf '{"text":"match"}'
done
printf ']\n'
`
	if err := os.WriteFile(script, []byte(body), 0o755); err != nil {
		h.t.Fatal(err)
	}
	h.t.Setenv(AstGrepEnv, script)
}

func (h *harness) writeAssertions(relative string, assertions []ArchAssertion) {
	h.t.Helper()
	raw, err := json.Marshal(map[string]any{"assertions": assertions})
	if err != nil {
		h.t.Fatal(err)
	}
	h.write(relative, string(raw))
}

func (h *harness) readArchReview() ArchReview {
	h.t.Helper()
	raw, err := os.ReadFile(filepath.Join(h.stateDirectory(), archReviewFileName))
	if err != nil {
		h.t.Fatal(err)
	}
	var review ArchReview
	if err := json.Unmarshal(raw, &review); err != nil {
		h.t.Fatal(err)
	}
	return review
}

func TestArchCheckPassesWhenAssertionsHold(t *testing.T) {
	h := newHarness(t)
	h.fakeAstGrep()
	h.write("svc/handler.go", "package svc\n\nfunc H() { logger.Info(\"ok\") }\n")
	h.writeAssertions("arch.json", []ArchAssertion{
		{ID: "logs-through-logger", Description: "handlers log via logger", Pattern: "logger.Info(", Expect: "present", PathGlob: "svc/**"},
		{ID: "no-panic", Description: "handlers never panic", Pattern: "panic(", Expect: "absent", PathGlob: "svc/**"},
	})
	if code, _, stderr := h.run("arch-check", "--assertions", "arch.json"); code != 0 {
		t.Fatalf("arch-check exit %d: %s", code, stderr)
	}
	review := h.readArchReview()
	if !review.Verified {
		t.Fatalf("arch-check with ast-grep present must be verified: %+v", review)
	}
	if !review.Passed || len(review.Results) != 2 {
		t.Fatalf("arch review = %+v", review)
	}
	for _, r := range review.Results {
		if !r.Passed {
			t.Fatalf("assertion %q did not pass: %+v", r.ID, r)
		}
	}
	if review.Digest == "" || review.CommandID == "" || review.Command == nil {
		t.Fatalf("verified review lacks digest/command: %+v", review)
	}

	byKind := recordsByKind(t, h.statusJSON().Records)
	arch, ok := byKind[controlplane.GuardRecordArchReview]
	if !ok || arch.CommandID != review.CommandID || arch.Evidence.ExitCode != 0 {
		t.Fatalf("arch-review record = %+v (ok=%v)", arch, ok)
	}
}

func TestArchCheckFailsWhenAnAssertionIsViolated(t *testing.T) {
	h := newHarness(t)
	h.fakeAstGrep()
	h.write("svc/handler.go", "package svc\n\nfunc H() { panic(\"boom\") }\n")
	h.writeAssertions("arch.json", []ArchAssertion{
		// Required structure that is absent -> present assertion fails.
		{ID: "logs-through-logger", Description: "handlers log via logger", Pattern: "logger.Info(", Expect: "present", PathGlob: "svc/**"},
		// Forbidden structure that is present -> absent assertion fails.
		{ID: "no-panic", Description: "handlers never panic", Pattern: "panic(", Expect: "absent", PathGlob: "svc/**"},
	})
	// A violated architecture check is reported (exit 2), never a hard error.
	code, _, stderr := h.run("arch-check", "--assertions", "arch.json")
	if code != 2 {
		t.Fatalf("violated arch-check exit %d (stderr %q), want the advisory code 2", code, stderr)
	}
	review := h.readArchReview()
	if !review.Verified || review.Passed {
		t.Fatalf("a violated arch review must be verified and not passed: %+v", review)
	}
	failing := 0
	for _, r := range review.Results {
		if !r.Passed {
			failing++
		}
	}
	if failing != 2 {
		t.Fatalf("expected both assertions to fail: %+v", review.Results)
	}
	byKind := recordsByKind(t, h.statusJSON().Records)
	arch, ok := byKind[controlplane.GuardRecordArchReview]
	if !ok || arch.Evidence.ExitCode == 0 {
		t.Fatalf("a failing arch-review record must carry a non-zero exit: %+v (ok=%v)", arch, ok)
	}
}

func TestArchCheckIsUnverifiedWhenAstGrepIsAbsent(t *testing.T) {
	h := newHarness(t)
	// Pin the binary to a name that does not resolve, standing in for a host
	// that never installed ast-grep.
	h.t.Setenv(AstGrepEnv, filepath.Join(h.t.TempDir(), "definitely-not-installed"))
	h.write("svc/handler.go", "package svc\n")
	h.writeAssertions("arch.json", []ArchAssertion{
		{ID: "logs-through-logger", Description: "handlers log via logger", Pattern: "logger.Info(", Expect: "present", PathGlob: "svc/**"},
	})
	// A missing verifier is not a failure of the check; the command still exits 0.
	if code, _, stderr := h.run("arch-check", "--assertions", "arch.json"); code != 0 {
		t.Fatalf("arch-check with ast-grep absent exit %d: %s", code, stderr)
	}
	review := h.readArchReview()
	if review.Verified {
		t.Fatalf("arch-check without ast-grep must be unverified: %+v", review)
	}
	if review.Passed {
		t.Fatal("an unverified arch review must never report passed")
	}
	if review.CommandID != "" || review.Command != nil {
		t.Fatalf("an unverified review must record no command evidence: %+v", review)
	}
	// A tool that never ran proves nothing, so it must not appear as a citeable
	// guard record.
	if byKind := recordsByKind(t, h.statusJSON().Records); func() bool {
		_, ok := byKind[controlplane.GuardRecordArchReview]
		return ok
	}() {
		t.Fatal("an unverified arch review leaked into the citeable guard records")
	}
	// It is still surfaced in status so the orchestrator can see it went unrun.
	if status := h.statusJSON(); status.ArchReview == nil || status.ArchReview.Verified {
		t.Fatalf("status must surface the unverified arch review: %+v", status.ArchReview)
	}
}

func TestArchCheckRejectsAMalformedAssertion(t *testing.T) {
	h := newHarness(t)
	h.fakeAstGrep()
	h.writeAssertions("arch.json", []ArchAssertion{
		{ID: "bad-expect", Description: "nonsense expectation", Pattern: "x", Expect: "maybe"},
	})
	if code, _, stderr := h.run("arch-check", "--assertions", "arch.json"); code == 0 {
		t.Fatalf("arch-check accepted an invalid expect value: %s", stderr)
	}
	if _, err := os.Stat(filepath.Join(h.stateDirectory(), archReviewFileName)); !os.IsNotExist(err) {
		t.Fatalf("a rejected arch-check still wrote state: %v", err)
	}
}
