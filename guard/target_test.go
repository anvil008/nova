package guard

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// runStdinFrom drives the hook from a session working directory that is not the
// sealed repository. That is the configuration a cwd-keyed seal lookup misses:
// the session lives somewhere harmless while the write lands in a sealed tree.
func (h *harness) runStdinFrom(dir, payload string, args ...string) (int, string, string) {
	h.t.Helper()
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	code := Run(Options{Dir: dir, Stdin: strings.NewReader(payload), Stdout: stdout, Stderr: stderr}, args)
	return code, stdout.String(), stderr.String()
}

func claudeEdit(target, workingDirectory, session string) string {
	return `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"` +
		target + `"},"cwd":"` + workingDirectory + `","session_id":"` + session + `"}`
}

// T1: the seal that governs a write is the seal of the repository being
// written, never the seal of the directory the session happens to sit in.
func TestPreToolUseResolvesTheSealFromTheEditTarget(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := t.TempDir()
	payload := claudeEdit(filepath.Join(h.repository, "pkg", "thing_test.go"), outside, "s-1")
	_, stdout, _ := h.runStdinFrom(outside, payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	denied, reason := claudeDeny(t, stdout)
	if !denied {
		t.Fatalf("an absolute path into a sealed repository was allowed from a cwd outside it: %q", stdout)
	}
	if !strings.Contains(reason, "sealed") {
		t.Fatalf("reason %q", reason)
	}
}

// T2: `../` out of the session directory is the same write by another spelling.
func TestPreToolUseResolvesTraversalOutOfTheSessionCwd(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := t.TempDir()
	relative, err := filepath.Rel(outside, filepath.Join(h.resolvedRepository(), "pkg", "thing_test.go"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(relative, "..") {
		t.Fatalf("relative path %q does not leave the session directory; the case proves nothing", relative)
	}
	_, stdout, _ := h.runStdinFrom(outside, claudeEdit(relative, outside, "s-1"), "hook", "--harness", "claude", "--event", "PreToolUse")
	if denied, _ := claudeDeny(t, stdout); !denied {
		t.Fatalf("a traversal into a sealed repository was allowed: %q", stdout)
	}
}

// T3: an alias to the repository root still resolves onto the sealed tree when
// the session cwd offers no help at all.
func TestPreToolUseResolvesSymlinkedTargetsFromAnOutsideCwd(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := t.TempDir()
	link := filepath.Join(outside, "checkout")
	if err := os.Symlink(h.resolvedRepository(), link); err != nil {
		t.Fatal(err)
	}
	payload := claudeEdit(filepath.Join(link, "pkg", "thing_test.go"), outside, "s-1")
	_, stdout, _ := h.runStdinFrom(outside, payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if denied, _ := claudeDeny(t, stdout); !denied {
		t.Fatalf("a symlinked path into a sealed repository was allowed: %q", stdout)
	}
}

// T4: a path in no repository at all stays allowed even while a seal exists;
// failing closed there would block every unrelated session on the machine.
func TestPreToolUseAllowsNonRepositoryTargetsFromAnOutsideCwd(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := t.TempDir()
	payload := claudeEdit(filepath.Join(outside, "scratch", "notes.txt"), outside, "s-1")
	code, stdout, stderr := h.runStdinFrom(outside, payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("a path outside every repository was refused: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
}

// T5: the Stop gate must judge every repository the session actually wrote to,
// not only the one it is standing in when it tries to finish.
func TestStopCoversRepositoriesTouchedOutsideTheSessionCwd(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := t.TempDir()

	edit := claudeEdit(filepath.Join(h.repository, "pkg", "thing.go"), outside, "s-1")
	if code, stdout, stderr := h.runStdinFrom(outside, edit, "hook", "--harness", "claude", "--event", "PreToolUse"); code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("writing an unsealed file was refused: exit %d stdout %q stderr %q", code, stdout, stderr)
	}

	stop := `{"hook_event_name":"Stop","cwd":"` + outside + `","session_id":"s-1"}`
	code, _, stderr := h.runStdinFrom(outside, stop, "hook", "--harness", "claude", "--event", "Stop")
	if code != 2 {
		t.Fatalf("Stop ignored the sealed repository this session wrote to: exit %d stderr %q", code, stderr)
	}
	if !strings.Contains(stderr, "green") || !strings.Contains(stderr, h.resolvedRepository()) {
		t.Fatalf("stderr %q does not name the touched repository and its blocker", stderr)
	}

	untouched := `{"hook_event_name":"Stop","cwd":"` + outside + `","session_id":"s-2"}`
	if code, stdout, stderr := h.runStdinFrom(outside, untouched, "hook", "--harness", "claude", "--event", "Stop"); code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("a session that touched nothing was blocked: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
}

// T6: Antigravity keys its session on conversationId, so its touch log has to
// work from the same write-then-stop sequence.
func TestAntigravityStopCoversTouchedRepositories(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := t.TempDir()
	edit := `{"toolCall":{"name":"write_to_file","args":{"TargetFile":"` +
		filepath.Join(h.repository, "pkg", "thing.go") + `"}},"workspacePaths":["` + outside + `"],"conversationId":"c-1"}`
	if code, stdout, stderr := h.runStdinFrom(outside, edit, "hook", "--harness", "agy", "--event", "PreToolUse"); code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("agy write refused: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
	stop := `{"terminationReason":"idle","fullyIdle":true,"workspacePaths":["` + outside + `"],"conversationId":"c-1"}`
	code, stdout, _ := h.runStdinFrom(outside, stop, "hook", "--harness", "agy", "--event", "Stop")
	if code != 0 || !strings.Contains(stdout, `"decision":"continue"`) {
		t.Fatalf("agy Stop ignored the touched repository: exit %d stdout %q", code, stdout)
	}
}

// T7: PostToolUse shell checks re-digest the touched repositories too, so an
// in-place rewrite of a sealed test from a foreign cwd is still reported.
func TestPostToolUseShellCoversTouchedRepositories(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := t.TempDir()
	edit := claudeEdit(filepath.Join(h.repository, "pkg", "thing.go"), outside, "s-1")
	if code, _, _ := h.runStdinFrom(outside, edit, "hook", "--harness", "claude", "--event", "PreToolUse"); code != 0 {
		t.Fatalf("write refused: exit %d", code)
	}
	h.write("pkg/thing_test.go", "package pkg\n\n// rewritten by a shell command\n")
	shell := `{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"sed -i s/x/y/ pkg/thing_test.go"},"cwd":"` +
		outside + `","session_id":"s-1"}`
	code, stdout, stderr := h.runStdinFrom(outside, shell, "hook", "--harness", "claude", "--event", "PostToolUse")
	if code != 2 || stdout != "" || !strings.Contains(stderr, "pkg/thing_test.go") {
		t.Fatalf("shell check missed the touched repository: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
}

// T8: the M1 refusal must not be skippable by sitting outside the sealed
// repository. With no seal anywhere the fast path still stays silent.
func TestUnreadablePayloadFailsClosedFromAnOutsideCwd(t *testing.T) {
	h := newHarness(t)
	truncated := `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"pkg/thing_te`
	outside := t.TempDir()

	if code, stdout, stderr := h.runStdinFrom(outside, truncated, "hook", "--harness", "claude", "--event", "PreToolUse"); code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("no seal anywhere must stay silent: exit %d stdout %q stderr %q", code, stdout, stderr)
	}

	h.seal()
	_, stdout, _ := h.runStdinFrom(outside, truncated, "hook", "--harness", "claude", "--event", "PreToolUse")
	denied, reason := claudeDeny(t, stdout)
	if !denied {
		t.Fatalf("an unreadable payload was allowed because the session cwd was outside the sealed repository: %q", stdout)
	}
	if !strings.Contains(reason, "payload") {
		t.Fatalf("reason %q does not explain the refusal", reason)
	}
}
