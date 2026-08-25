package guard

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// unsealedRepository builds a second, never-sealed git repository so a session
// can sit somewhere the guard has no state for at all.
func unsealedRepository(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	for _, argv := range [][]string{
		{"git", "init", "--initial-branch=main"},
		{"git", "config", "user.email", "guard@example.test"},
		{"git", "config", "user.name", "Guard Test"},
		{"git", "config", "commit.gpgsign", "false"},
	} {
		command := exec.Command(argv[0], argv[1:]...)
		command.Dir = root
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("%v: %v: %s", argv, err, output)
		}
	}
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		t.Fatal(err)
	}
	return resolved
}

// aliasTraversal spells a path the way open(2) reads it: `<alias>/../<name>`
// where `<alias>` is a symlink pointing somewhere other than its own parent.
// The kernel applies `..` to the symlink's target, so the path lands back on
// the sealed tree; any lexical cleanup applies `..` to the link's own parent
// and lands somewhere else entirely. Building the string by hand matters --
// filepath.Join would perform exactly the lexical collapse under test.
func aliasTraversal(linkDirectory, aliasName, repositoryName, relative string) string {
	return linkDirectory + "/" + aliasName + "/../" + repositoryName + "/" + relative
}

// P1: the reproduction. A session sitting in an unrelated, unsealed repository
// names a sealed test through a symlink combined with `..`. Symlinks alone and
// `..` alone were already covered; only their combination makes the lexical and
// the physical resolution disagree, and the lexical answer is the bypass.
func TestPreToolUseResolvesSymlinkTraversalFromAnotherRepository(t *testing.T) {
	h := newHarness(t)
	h.seal()
	sealed := h.resolvedRepository()
	session := unsealedRepository(t)

	links := t.TempDir()
	if err := os.Symlink(sealed, filepath.Join(links, "aliasA")); err != nil {
		t.Fatal(err)
	}
	target := aliasTraversal(links, "aliasA", filepath.Base(sealed), "pkg/thing_test.go")
	if filepath.Clean(target) == filepath.Join(sealed, "pkg", "thing_test.go") {
		t.Fatalf("lexical cleaning already agrees with the kernel for %q; the case proves nothing", target)
	}
	if _, err := os.Stat(target); err != nil {
		t.Fatalf("the reproduction path must be openable, so the guard cannot dismiss it: %v", err)
	}

	_, stdout, _ := h.runStdinFrom(session, claudeEdit(target, session, "s-alias"), "hook", "--harness", "claude", "--event", "PreToolUse")
	denied, reason := claudeDeny(t, stdout)
	if !denied {
		t.Fatalf("a sealed test reached through a symlink plus `..` was allowed: %q", stdout)
	}
	if !strings.Contains(reason, "sealed") {
		t.Fatalf("reason %q", reason)
	}
}

// P2: the same spelling must also attribute the write to the sealed repository,
// so the touch log and the Stop gate see it. Attribution and the seal check
// share one resolver, so a lexical answer blinds both at once.
func TestSymlinkTraversalAttributesTheWriteToTheSealedRepository(t *testing.T) {
	h := newHarness(t)
	h.seal()
	sealed := h.resolvedRepository()
	session := unsealedRepository(t)

	links := t.TempDir()
	if err := os.Symlink(sealed, filepath.Join(links, "aliasA")); err != nil {
		t.Fatal(err)
	}
	// An unsealed file, so PreToolUse allows the write and only the touch log
	// records anything.
	target := aliasTraversal(links, "aliasA", filepath.Base(sealed), "pkg/thing.go")
	if code, stdout, stderr := h.runStdinFrom(session, claudeEdit(target, session, "s-alias"), "hook", "--harness", "claude", "--event", "PreToolUse"); code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("writing an unsealed file was refused: exit %d stdout %q stderr %q", code, stdout, stderr)
	}

	stop := `{"hook_event_name":"Stop","cwd":"` + session + `","session_id":"s-alias"}`
	code, _, stderr := h.runStdinFrom(session, stop, "hook", "--harness", "claude", "--event", "Stop")
	if code != 2 {
		t.Fatalf("Stop was blind to the sealed repository the session wrote to: exit %d stderr %q", code, stderr)
	}
	if !strings.Contains(stderr, sealed) {
		t.Fatalf("stderr %q does not name the sealed repository", stderr)
	}
}

// P3: the same-repository spelling. The session is standing in the sealed tree,
// so nothing about the seal lookup is in doubt; only the path arithmetic is.
func TestPreToolUseResolvesSymlinkTraversalInsideTheSealedRepository(t *testing.T) {
	h := newHarness(t)
	h.seal()
	sealed := h.resolvedRepository()

	links := t.TempDir()
	if err := os.Symlink(sealed, filepath.Join(links, "aliasA")); err != nil {
		t.Fatal(err)
	}
	target := aliasTraversal(links, "aliasA", filepath.Base(sealed), "pkg/thing_test.go")
	_, stdout, _ := h.runStdinFrom(sealed, claudeEdit(target, sealed, "s-same"), "hook", "--harness", "claude", "--event", "PreToolUse")
	if denied, _ := claudeDeny(t, stdout); !denied {
		t.Fatalf("a sealed test reached through a symlink plus `..` from inside the repository was allowed: %q", stdout)
	}
}

// P4: a relative spelling of the same trick. The session directory is joined on
// before resolution, so the join must not clean the traversal away either.
func TestPreToolUseResolvesRelativeSymlinkTraversal(t *testing.T) {
	h := newHarness(t)
	h.seal()
	sealed := h.resolvedRepository()
	session := unsealedRepository(t)

	if err := os.Symlink(sealed, filepath.Join(session, "aliasA")); err != nil {
		t.Fatal(err)
	}
	target := "aliasA/../" + filepath.Base(sealed) + "/pkg/thing_test.go"
	_, stdout, _ := h.runStdinFrom(session, claudeEdit(target, session, "s-relative"), "hook", "--harness", "claude", "--event", "PreToolUse")
	if denied, _ := claudeDeny(t, stdout); !denied {
		t.Fatalf("a relative symlink traversal into a sealed repository was allowed: %q", stdout)
	}
}

// P5: the resolver still has to answer for a file no tool has created yet, or
// the PreToolUse deny that matters most -- a Write that would create the sealed
// path -- resolves to nothing. This is the behaviour the lexical version had
// and must survive the fix.
func TestSealCheckStillResolvesUncreatedFilesUnderASymlinkedParent(t *testing.T) {
	h := newHarness(t)
	h.seal()
	sealed := h.resolvedRepository()

	links := t.TempDir()
	if err := os.Symlink(filepath.Join(sealed, "pkg"), filepath.Join(links, "pkgAlias")); err != nil {
		t.Fatal(err)
	}
	missing := filepath.Join(links, "pkgAlias", "created_later_test.go")
	if _, err := os.Stat(missing); !os.IsNotExist(err) {
		t.Fatalf("the case needs a path that does not exist yet: %v", err)
	}
	resolved := resolveSymlinks(missing)
	if want := filepath.Join(sealed, "pkg", "created_later_test.go"); resolved != want {
		t.Fatalf("resolveSymlinks(%q) = %q, want %q", missing, resolved, want)
	}
}
