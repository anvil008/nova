package guard

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// claudeDeny decodes the Claude PreToolUse dialect and reports whether the edit
// was refused.
func claudeDeny(t *testing.T, stdout string) (bool, string) {
	t.Helper()
	if strings.TrimSpace(stdout) == "" {
		return false, ""
	}
	var decoded struct {
		HookSpecificOutput struct {
			PermissionDecision       string `json:"permissionDecision"`
			PermissionDecisionReason string `json:"permissionDecisionReason"`
		} `json:"hookSpecificOutput"`
	}
	if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
		t.Fatalf("decode %q: %v", stdout, err)
	}
	return decoded.HookSpecificOutput.PermissionDecision == "deny", decoded.HookSpecificOutput.PermissionDecisionReason
}

func (h *harness) resolvedRepository() string {
	h.t.Helper()
	resolved, err := filepath.EvalSymlinks(h.repository)
	if err != nil {
		h.t.Fatal(err)
	}
	return resolved
}

// M1: a payload the guard cannot parse must not be read as permission. The
// no-seal fast path stays silent, but a decode failure under a live seal means
// the guard cannot tell what the tool would write.
func TestHookFailsClosedOnAnUnreadablePayload(t *testing.T) {
	h := newHarness(t)
	truncated := `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"pkg/thing_te`

	code, stdout, stderr := h.runStdin(truncated, "hook", "--harness", "claude", "--event", "PreToolUse")
	if code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("unsealed repository must stay silent: exit %d stdout %q stderr %q", code, stdout, stderr)
	}

	h.seal()
	_, stdout, _ = h.runStdin(truncated, "hook", "--harness", "claude", "--event", "PreToolUse")
	denied, reason := claudeDeny(t, stdout)
	if !denied {
		t.Fatalf("an unreadable payload was allowed while sealed: %q", stdout)
	}
	if !strings.Contains(reason, "payload") {
		t.Fatalf("reason %q does not explain the refusal", reason)
	}
}

// M1: an oversized payload must not silently disable the guard. A large Write
// or apply_patch envelope is ordinary traffic.
func TestHookDeniesAnOversizedSealedTestEdit(t *testing.T) {
	h := newHarness(t)
	h.seal()
	payload := `{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"pkg/thing_test.go","content":"` +
		strings.Repeat("x", 2<<20) + `"},"cwd":"` + h.repository + `"}`
	_, stdout, _ := h.runStdin(payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if denied, _ := claudeDeny(t, stdout); !denied {
		t.Fatalf("a 2 MiB edit of a sealed test was allowed: %q", stdout)
	}
}

// M2: harness payloads carry paths relative to the tool's own cwd, which is
// routinely a subdirectory of the repository.
func TestPreToolUseResolvesRelativePathsAgainstTheToolCwd(t *testing.T) {
	h := newHarness(t)
	h.seal()
	payload := `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"thing_test.go"},"cwd":"` +
		filepath.Join(h.repository, "pkg") + `"}`
	_, stdout, _ := h.runStdin(payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	denied, reason := claudeDeny(t, stdout)
	if !denied {
		t.Fatalf("editing a sealed test from a subdirectory was allowed: %q", stdout)
	}
	if !strings.Contains(reason, "sealed") {
		t.Fatalf("reason %q", reason)
	}
}

// M3: an alias to a sealed test is the sealed test. The symlink is not itself
// sealed, because the seal walk only digests regular files.
func TestPreToolUseResolvesSymlinkedEditTargets(t *testing.T) {
	h := newHarness(t)
	if err := os.Symlink("thing_test.go", filepath.Join(h.repository, "pkg", "alias_test.go")); err != nil {
		t.Fatal(err)
	}
	h.seal()
	for _, test := range h.readSeal().Tests {
		if test.Path == "pkg/alias_test.go" {
			t.Fatal("the symlink itself was sealed; this case no longer proves alias resolution")
		}
	}

	aliasPayload := `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"pkg/alias_test.go"},"cwd":"` + h.repository + `"}`
	_, stdout, _ := h.runStdin(aliasPayload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if denied, _ := claudeDeny(t, stdout); !denied {
		t.Fatalf("an in-repository alias to a sealed test was allowed: %q", stdout)
	}

	linkedRoot := filepath.Join(t.TempDir(), "checkout")
	if err := os.Symlink(h.resolvedRepository(), linkedRoot); err != nil {
		t.Fatal(err)
	}
	rootPayload := `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"` +
		filepath.Join(linkedRoot, "pkg", "thing_test.go") + `"},"cwd":"` + h.repository + `"}`
	_, stdout, _ = h.runStdin(rootPayload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if denied, _ := claudeDeny(t, stdout); !denied {
		t.Fatalf("an absolute path through a symlinked repository root was allowed: %q", stdout)
	}
}

func TestPreToolUseAllowsPathsOutsideTheRepository(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := filepath.Join(t.TempDir(), "pkg", "thing_test.go")
	payload := `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"` + outside + `"},"cwd":"` + h.repository + `"}`
	code, stdout, stderr := h.runStdin(payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("an out-of-repository path was refused: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
}

// M4: an amendment must invalidate the evidence taken over the earlier tests,
// otherwise seal -> verify -> gut the tests -> reseal passes the Stop gate on a
// green run that never executed the amended tests.
func TestResealInvalidatesEarlierGreenEvidence(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.verify()
	h.write("findings.txt", "reviewed\n")
	if code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt"); code != 0 {
		t.Fatalf("diff-review exit %d: %s", code, stderr)
	}
	stopPayload := `{"hook_event_name":"Stop","cwd":"` + h.repository + `"}`
	if code, _, stderr := h.runStdin(stopPayload, "hook", "--harness", "claude", "--event", "Stop"); code != 0 {
		t.Fatalf("satisfied contract refused before the amendment: exit %d stderr %q", code, stderr)
	}

	h.write("pkg/thing_test.go", "package pkg\n\n// the assertion is gone\n")
	if code, _, stderr := h.run("reseal", "--reason", "gut the reproduction"); code != 0 {
		t.Fatalf("reseal exit %d: %s", code, stderr)
	}
	// Re-record the review so the only remaining question is whether the green
	// run that never executed the amended tests still counts.
	if code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt"); code != 0 {
		t.Fatalf("diff-review exit %d: %s", code, stderr)
	}
	code, _, stderr := h.runStdin(stopPayload, "hook", "--harness", "claude", "--event", "Stop")
	if code != 2 {
		t.Fatalf("Stop accepted a green run that predates the amendment: exit %d stderr %q", code, stderr)
	}
	if !strings.Contains(stderr, "green") {
		t.Fatalf("stderr %q does not name the stale green evidence", stderr)
	}
	if status := h.status(); status.Ready {
		t.Fatalf("status reported ready after an amendment invalidated the evidence: %+v", status)
	}
}

// M5: untracked files are exactly the new code a change adds, so their content
// belongs in the digest the Stop gate compares.
func TestDiffReviewDetectsUntrackedContentRewrites(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.write("pkg/added.go", "package pkg\n\nfunc Added() {}\n")
	h.write("findings.txt", "reviewed the new file\n")
	if code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt"); code != 0 {
		t.Fatalf("diff-review exit %d: %s", code, stderr)
	}
	if h.status().DiffStale {
		t.Fatal("a freshly recorded review is not stale")
	}
	h.write("pkg/added.go", "package pkg\n\nfunc Added() int { return 1 }\n")
	if !h.status().DiffStale {
		t.Fatal("rewriting an untracked file left the recorded review current")
	}
}

func TestDispatchRejectsMalformedInvocations(t *testing.T) {
	h := newHarness(t)
	cases := [][]string{
		{},
		{"nonsense"},
		{"hook"},
		{"hook", "--harness", "vim"},
		{"hook", "--harness"},
		{"seal", "--tests"},
		{"seal", "--tests", "**/*_test.go"},
		{"verify"},
		{"reseal", "--reason", "   "},
		{"diff-review"},
		{"diff-review", "list"},
		{"diff-review", "record"},
		{"diff-review", "record", "--findings", "absent.txt"},
		{"status", "--unexpected", "1"},
	}
	for _, args := range cases {
		if code, _, stderr := h.run(args...); code == 0 {
			t.Errorf("anvil-guard %v exited 0; stderr %q", args, stderr)
		}
	}
}

func TestDiffReviewRejectsAnEmptyFindingsFile(t *testing.T) {
	h := newHarness(t)
	h.write("findings.txt", "\n   \n")
	code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt")
	if code == 0 || !strings.Contains(stderr, "empty") {
		t.Fatalf("exit %d stderr %q", code, stderr)
	}
}

func TestDecodePayloadRejectsUnreadableInput(t *testing.T) {
	if _, err := decodePayload(strings.NewReader("{not json")); err == nil {
		t.Fatal("malformed JSON decoded without error")
	}
	if _, err := decodePayload(strings.NewReader(strings.Repeat("x", maxPayloadBytes+1))); err == nil {
		t.Fatal("an oversized payload decoded without error")
	}
	decoded, err := decodePayload(strings.NewReader("   "))
	if err != nil || decoded.ToolName != "" {
		t.Fatalf("blank payload = %+v %v", decoded, err)
	}
	if _, err := decodePayload(nil); err != nil {
		t.Fatalf("absent stdin = %v", err)
	}
}
