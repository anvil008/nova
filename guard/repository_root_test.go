package guard

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// jjInstalled gates the jj half of this file the way scripts/tests/test_workcell_ws.sh
// gates its own: a CI image without jj still runs the git cases rather than failing.
func jjInstalled() bool {
	_, err := exec.LookPath("jj")
	return err == nil
}

func mustRun(t *testing.T, dir string, argv ...string) string {
	t.Helper()
	command := exec.Command(argv[0], argv[1:]...)
	command.Dir = dir
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("%v in %s: %v: %s", argv, dir, err, output)
	}
	return string(output)
}

// seedGitRepo builds a git repository with one commit, configured entirely
// per-repository so the developer's real git config is never read or written.
func seedGitRepo(t *testing.T, dir string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	mustRun(t, dir, "git", "init", "--initial-branch=main")
	mustRun(t, dir, "git", "config", "user.email", "guard@example.test")
	mustRun(t, dir, "git", "config", "user.name", "Guard Test")
	mustRun(t, dir, "git", "config", "commit.gpgsign", "false")
	if err := os.WriteFile(filepath.Join(dir, "a.txt"), []byte("hi\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	mustRun(t, dir, "git", "add", "-A")
	mustRun(t, dir, "git", "commit", "-m", "baseline")
}

// seedJJConfig points jj at a throwaway config so it never reads or writes the
// developer's own, matching what scripts/tests/test_workcell_ws.sh does.
func seedJJConfig(t *testing.T) {
	t.Helper()
	config := filepath.Join(t.TempDir(), "jj.toml")
	if err := os.WriteFile(config, []byte("[user]\nname = \"t\"\nemail = \"t@example.invalid\"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("JJ_CONFIG", config)
}

// resolved is what repositoryRoot promises to return: the symlink-resolved path.
func resolved(t *testing.T, path string) string {
	t.Helper()
	value, err := filepath.EvalSymlinks(path)
	if err != nil {
		t.Fatal(err)
	}
	return value
}

// TestRepositoryRootAcrossVCSLayouts pins the four layouts the guard is run in.
// The jj secondary workspace is the one this test exists for: it has a `.jj` and
// no `.git` at all, so `git rev-parse --show-toplevel` cannot find it from
// anywhere and every guard entry point used to fail there.
func TestRepositoryRootAcrossVCSLayouts(t *testing.T) {
	for _, testCase := range []struct {
		name string
		// build returns the directory to resolve from, the root expected back,
		// and whether that root must be driven through jj.
		build  func(t *testing.T) (from string, want string, wantJJ bool)
		needJJ bool
	}{
		{
			name:   "colocated primary resolves through git and keeps the git backend",
			needJJ: true,
			build: func(t *testing.T) (string, string, bool) {
				root := filepath.Join(t.TempDir(), "prim")
				seedGitRepo(t, root)
				mustRun(t, root, "jj", "git", "init", "--colocate")
				// Both `.jj` and `.git` are present, and git can still answer, so
				// nothing about an existing colocated repository changes.
				return root, resolved(t, root), false
			},
		},
		{
			name:   "jj secondary workspace resolves to the workspace root",
			needJJ: true,
			build: func(t *testing.T) (string, string, bool) {
				base := t.TempDir()
				primary := filepath.Join(base, "prim")
				seedGitRepo(t, primary)
				mustRun(t, primary, "jj", "git", "init", "--colocate")
				secondary := filepath.Join(base, "sec")
				mustRun(t, primary, "jj", "workspace", "add", secondary)
				// The indirection this used to be blamed on: in a secondary
				// workspace `.jj/repo` is a file naming the primary's store.
				info, err := os.Stat(filepath.Join(secondary, ".jj", "repo"))
				if err != nil || info.IsDir() {
					t.Fatalf("expected .jj/repo to be a plain file in a secondary workspace: %v", err)
				}
				if _, err := os.Stat(filepath.Join(secondary, ".git")); !os.IsNotExist(err) {
					t.Fatalf("expected no .git in a secondary workspace, got %v", err)
				}
				return secondary, resolved(t, secondary), true
			},
		},
		{
			name:   "jj secondary workspace resolves from a subdirectory",
			needJJ: true,
			build: func(t *testing.T) (string, string, bool) {
				base := t.TempDir()
				primary := filepath.Join(base, "prim")
				seedGitRepo(t, primary)
				mustRun(t, primary, "jj", "git", "init", "--colocate")
				secondary := filepath.Join(base, "sec")
				mustRun(t, primary, "jj", "workspace", "add", secondary)
				nested := filepath.Join(secondary, "pkg", "deep")
				if err := os.MkdirAll(nested, 0o755); err != nil {
					t.Fatal(err)
				}
				return nested, resolved(t, secondary), true
			},
		},
		{
			name: "plain git worktree resolves to the worktree root",
			build: func(t *testing.T) (string, string, bool) {
				base := t.TempDir()
				primary := filepath.Join(base, "prim")
				seedGitRepo(t, primary)
				worktree := filepath.Join(base, "wt")
				mustRun(t, primary, "git", "worktree", "add", "-b", "side", worktree)
				// A linked worktree already resolves to itself, which is the
				// precedent the jj workspace choice follows.
				return worktree, resolved(t, worktree), false
			},
		},
		{
			name: "plain git repository still resolves through git",
			build: func(t *testing.T) (string, string, bool) {
				root := filepath.Join(t.TempDir(), "plain")
				seedGitRepo(t, root)
				return root, resolved(t, root), false
			},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			if testCase.needJJ {
				if !jjInstalled() {
					t.Skip("jj is not installed")
				}
				seedJJConfig(t)
			}
			from, want, wantJJ := testCase.build(t)

			got, err := repositoryRoot(from)
			if err != nil {
				t.Fatalf("repositoryRoot(%s): %v", from, err)
			}
			if got != want {
				t.Fatalf("repositoryRoot(%s) = %s, want %s", from, got, want)
			}
			if usesJJ(got) != wantJJ {
				t.Fatalf("usesJJ(%s) = %v, want %v", got, usesJJ(got), wantJJ)
			}

			// Whatever the backend, the base a change is measured against has to
			// resolve -- this is what every guard action calls first.
			base, digest, err := currentBase(got)
			if err != nil {
				t.Fatalf("currentBase(%s): %v", got, err)
			}
			if len(base.HeadCommit) != 40 {
				t.Fatalf("expected a 40-character commit id, got %q", base.HeadCommit)
			}
			if digest == "" {
				t.Fatal("expected a non-empty tree digest")
			}
		})
	}
}

// TestRepositoryRootRejectsNonRepository keeps the failure a failure: a plain
// directory is not a repository under either VCS.
func TestRepositoryRootRejectsNonRepository(t *testing.T) {
	directory := t.TempDir()
	if _, err := repositoryRoot(directory); err == nil {
		t.Fatal("expected an error for a directory that is not a repository")
	}
	if usesJJ(directory) {
		t.Fatal("a plain directory is not a jj workspace")
	}
}

// TestJJBackendSeesWorkingCopyChanges proves the jj backend answers the two
// questions the git backend cannot answer in a secondary workspace: a modified
// tracked file, and a file git would have called untracked. jj snapshots the
// working copy, so the second needs no separate untracked pass.
func TestJJBackendSeesWorkingCopyChanges(t *testing.T) {
	if !jjInstalled() {
		t.Skip("jj is not installed")
	}
	seedJJConfig(t)
	base := t.TempDir()
	primary := filepath.Join(base, "prim")
	seedGitRepo(t, primary)
	mustRun(t, primary, "jj", "git", "init", "--colocate")
	secondary := filepath.Join(base, "sec")
	mustRun(t, primary, "jj", "workspace", "add", secondary)

	root, err := repositoryRoot(secondary)
	if err != nil {
		t.Fatal(err)
	}
	clean, cleanDigest, err := currentBase(root)
	if err != nil {
		t.Fatal(err)
	}

	// A modification to a tracked file must move the digest.
	if err := os.WriteFile(filepath.Join(root, "a.txt"), []byte("changed\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	modified, modifiedDigest, err := currentBase(root)
	if err != nil {
		t.Fatal(err)
	}
	if modifiedDigest == cleanDigest {
		t.Fatal("expected a modified tracked file to change the tree digest")
	}
	if modified.HeadCommit != clean.HeadCommit {
		t.Fatalf("editing the working copy must not move the base commit: %s -> %s", clean.HeadCommit, modified.HeadCommit)
	}

	// A brand-new file -- git's "untracked" -- must move it too, content and all.
	if err := os.WriteFile(filepath.Join(root, "new.txt"), []byte("one\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, addedDigest, err := currentBase(root)
	if err != nil {
		t.Fatal(err)
	}
	if addedDigest == modifiedDigest {
		t.Fatal("expected a new file to change the tree digest")
	}
	if err := os.WriteFile(filepath.Join(root, "new.txt"), []byte("two\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, rewrittenDigest, err := currentBase(root)
	if err != nil {
		t.Fatal(err)
	}
	if rewrittenDigest == addedDigest {
		t.Fatal("expected rewriting a new file's content to change the tree digest")
	}

	// And the path-level question the PostToolUse notifier asks.
	changed, err := changedWorkingPaths(root)
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(changed, ",")
	for _, want := range []string{"a.txt", "new.txt"} {
		if !strings.Contains(joined, want) {
			t.Fatalf("changedWorkingPaths = %v, want it to include %s", changed, want)
		}
	}
}
