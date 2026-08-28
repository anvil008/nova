package guard

import (
	"bytes"
	"io/fs"

	"testing"
)

func TestUntrackedDigestStreaming(t *testing.T) {
	h := newHarness(t)

	// Create a large untracked file (15MB)
	// The first 10MB will be 'A's, the rest 5MB will be 'B's.
	const limit = 10 * 1024 * 1024
	const largeSize = 15 * 1024 * 1024

	largeContent := make([]byte, largeSize)
	for i := 0; i < limit; i++ {
		largeContent[i] = 'A'
	}
	for i := limit; i < largeSize; i++ {
		largeContent[i] = 'B'
	}

	h.write("large_untracked.txt", string(largeContent))

	// Get the working diff
	diff, err := workingDiff(h.repository)
	if err != nil {
		t.Fatalf("workingDiff failed: %v", err)
	}

	// The digest should be of the first 10MB ('A's)
	expectedDigest := digestBytes(largeContent[:limit])

	// Since workingDiff formats the combined byte array:
	// combined = tracked + \x00 + name + \x00 + digestBytes(content) + \x00
	// Let's verify that expectedDigest is present in the diff bytes, but the digest of the whole 15MB file is NOT.
	wholeDigest := digestBytes(largeContent)

	if !bytes.Contains(diff, []byte(expectedDigest)) {
		t.Errorf("Expected combined diff to contain capped digest %s", expectedDigest)
	}
	if bytes.Contains(diff, []byte(wholeDigest)) {
		t.Errorf("Combined diff contains digest of entire 15MB file %s, expected capping at 10MB", wholeDigest)
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
