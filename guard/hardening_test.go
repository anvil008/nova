package guard

import (
	"bytes"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
)

func TestUntrackedEditPastTenMiBChangesTreeDigest(t *testing.T) {
	h := newHarness(t)
	const limit = 10 * 1024 * 1024
	content := bytes.Repeat([]byte{'A'}, limit+1)
	h.write("large_untracked.txt", string(content))
	first, _, err := currentBase(h.repository)
	if err != nil {
		t.Fatal(err)
	}
	content[limit] = 'B'
	h.write("large_untracked.txt", string(content))
	second, _, err := currentBase(h.repository)
	if err != nil {
		t.Fatal(err)
	}
	if first.TreeDigest == second.TreeDigest {
		t.Fatal("edit after the first 10 MiB did not invalidate the tree digest")
	}
}

func TestWorkingDiffSkipsNonRegularUntrackedEntries(t *testing.T) {
	h := newHarness(t)
	if err := os.Symlink("missing-target", filepath.Join(h.repository, "untracked-link")); err != nil {
		t.Fatal(err)
	}
	if _, err := workingDiff(h.repository); err != nil {
		t.Fatalf("non-regular untracked entry made workingDiff fail: %v", err)
	}
}

func TestUnsealedSourceChangesUnquotesPorcelainPaths(t *testing.T) {
	h := newHarness(t)
	path := "pkg/odd\tname.go"
	h.write(path, "package pkg\n")
	paths, err := unsealedSourceChanges(h.repository)
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != 1 || paths[0] != path {
		t.Fatalf("unsealed paths = %q, want %q", paths, path)
	}
}

func TestBackslashPathNormalization(t *testing.T) {
	h := newHarness(t)
	h.seal() // Seals pkg/thing_test.go which is in our baseline commit

	// Create a state with our repository and state directories
	loaded, err := loadRepositoryState(h.repository)
	if err != nil {
		t.Fatalf("failed to load state: %v", err)
	}

	// Let's check a backslash path
	candidate := "pkg\\thing_test.go"
	if !isSealedTestPath(loaded, h.repository, candidate) {
		t.Errorf("expected %s to be recognized as a sealed test path", candidate)
	}

	components := pathComponents("pkg\\sub\\thing.go")
	if len(components) != 3 || components[0] != "pkg" || components[1] != "sub" || components[2] != "thing.go" {
		t.Errorf("expected normalized components [pkg sub thing.go], got %v", components)
	}
}

func TestArchCheckGlobCaching(t *testing.T) {
	h := newHarness(t)
	h.fakeAstGrep()

	// Create some files
	h.write("svc/handler.go", "package svc\n\nfunc H() { logger.Info(\"ok\") }\n")
	h.write("pkg/thing.go", "package pkg\n")

	// Write 3 assertions, each having a PathGlob
	h.writeAssertions("arch.json", []ArchAssertion{
		{ID: "logs-through-logger", Description: "handlers log via logger", Pattern: "logger.Info(", Expect: "present", PathGlob: "svc/**"},
		{ID: "no-panic", Description: "handlers never panic", Pattern: "panic(", Expect: "absent", PathGlob: "svc/**"},
		{ID: "pkg-no-panic", Description: "pkg never panic", Pattern: "panic(", Expect: "absent", PathGlob: "pkg/**"},
	})

	// Instrument filepathWalkDir to count walks
	walkCount := 0
	oldWalkDir := filepathWalkDir
	defer func() { filepathWalkDir = oldWalkDir }()
	filepathWalkDir = func(root string, fn fs.WalkDirFunc) error {
		walkCount++
		return oldWalkDir(root, fn)
	}

	// Run arch-check
	code, _, stderr := h.run("arch-check", "--assertions", "arch.json")
	if code != 0 {
		t.Fatalf("arch-check failed with exit %d: %s", code, stderr)
	}

	// If caching is optimized and working correctly, it should only walk the repository once
	// to build the in-memory cache of the repository directory contents.
	if walkCount != 1 {
		t.Errorf("expected exactly 1 repository walk, got %d", walkCount)
	}
}
