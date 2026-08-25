package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRunRejectsUnknownAndConflictingModes(t *testing.T) {
	if err := run([]string{"unknown"}); err == nil {
		t.Fatal("run(unknown) returned nil error")
	}
	if err := run([]string{"install", "--dry-run", "--check"}); err == nil {
		t.Fatal("run(install conflicting modes) returned nil error")
	}
}

func TestResolveRepositoryRootExplicitAndDiscovery(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "go.mod"), []byte("module github.com/anvil008/swarm-coder\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	nested := filepath.Join(root, "a", "b")
	if err := os.MkdirAll(nested, 0o755); err != nil {
		t.Fatal(err)
	}
	original, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(nested); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(original) })
	if got, err := resolveRepositoryRoot(""); err != nil || got != root {
		t.Fatalf("resolveRepositoryRoot() = %q, %v; want %q", got, err, root)
	}
	if _, err := resolveRepositoryRoot("relative"); err == nil {
		t.Fatal("relative explicit root returned nil error")
	}
}
