package main

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestConformanceRequiresExplicitOfflineMode(t *testing.T) {
	if err := runConformance(nil, io.Discard); err == nil {
		t.Fatal("conformance accepted missing --offline")
	}
	if err := runConformance([]string{"--offline", "extra"}, io.Discard); err == nil {
		t.Fatal("conformance accepted positional argument")
	}
}

func TestClientDetectsResponseOverflow(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.WriteHeader(http.StatusOK)
		_, _ = writer.Write(bytes.Repeat([]byte("x"), (4<<20)+1))
	}))
	defer server.Close()
	t.Setenv("SWARM_RUNPLANE_URL", server.URL)
	t.Setenv("SWARM_RUNPLANE_TOKEN", "test-token")
	err := runClient([]string{"health"}, strings.NewReader(""), &bytes.Buffer{})
	if err == nil || !strings.Contains(err.Error(), "response exceeds") {
		t.Fatalf("overflow error = %v", err)
	}
}

func TestServeHerdrConfigRequiresNoPositionalMutation(t *testing.T) {
	t.Setenv("HERDR_ENV", "1")
	err := runServe([]string{
		"--visibility", "auto", "--herdr-bin", "/opt/herdr/bin/herdr",
		"--herdr-socket", "/run/user/1000/herdr.sock", "--herdr-session", "session-1",
		"--herdr-workspace", "workspace-1", "unexpected",
	}, io.Discard)
	if err == nil || !strings.Contains(err.Error(), "no positional") {
		t.Fatalf("serve config error = %v", err)
	}
}

func TestWorkerCommandAcceptsOnlyDurableJobIDArgument(t *testing.T) {
	if err := run([]string{"worker"}, strings.NewReader(""), io.Discard, io.Discard); err == nil {
		t.Fatal("worker accepted missing durable job ID")
	}
	if err := run([]string{"worker", "job-1", "prompt-must-not-be-argv"}, strings.NewReader(""), io.Discard, io.Discard); err == nil {
		t.Fatal("worker accepted provider input on argv")
	}
}

// The checkpoint directive must be executable with no service running and no
// credentials configured, because the orchestrator holds no write authority.
func TestGoalSubcommandPersistsWithoutTheService(t *testing.T) {
	state := t.TempDir()
	t.Setenv("SWARM_RUNPLANE_STATE", state)
	t.Setenv("SWARM_RUNPLANE_TOKEN", "")
	t.Setenv("SWARM_RUNPLANE_TOKEN_FILE", "")

	request := `{"goalId":"goal-cli","checkpoint":{"objective":"repair Phase 1","nextAction":"run the gate"},"plan":"# plan\n"}`
	stdout := &bytes.Buffer{}
	if err := run([]string{"goal", "checkpoint"}, strings.NewReader(request), stdout, io.Discard); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"checkpoint.json", "plan.md"} {
		if _, err := os.Stat(filepath.Join(state, "goals", "goal-cli", name)); err != nil {
			t.Fatalf("goal checkpoint did not write %s: %v", name, err)
		}
	}

	stdout.Reset()
	if err := run([]string{"goal", "show", "goal-cli"}, strings.NewReader(""), stdout, io.Discard); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(stdout.String(), "repair Phase 1") {
		t.Fatalf("goal show = %q", stdout.String())
	}

	for _, arguments := range [][]string{{"goal"}, {"goal", "inspect"}, {"goal", "show"}, {"goal", "show", "../escape"}} {
		if err := run(arguments, strings.NewReader(request), io.Discard, io.Discard); err == nil {
			t.Errorf("swarm-runplane %v was accepted", arguments)
		}
	}
}

func TestStartCommandPropagatesErrors(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		writer.WriteHeader(http.StatusConflict)
		_, _ = writer.Write([]byte(`{"error":"provider and family must both be explicit"}`))
	}))
	defer server.Close()

	t.Setenv("SWARM_RUNPLANE_URL", server.URL)
	t.Setenv("SWARM_RUNPLANE_TOKEN", "test-token")

	reqFile := filepath.Join(t.TempDir(), "request.json")
	if err := os.WriteFile(reqFile, []byte(`{"route":{"canonicalRole":"workflow-executor"}}`), 0o600); err != nil {
		t.Fatal(err)
	}

	err := run([]string{"start", "--request", reqFile}, strings.NewReader(""), io.Discard, io.Discard)
	if err == nil {
		t.Fatal("expected run start to fail with non-nil error on HTTP 409, got nil")
	}
	if !strings.Contains(err.Error(), "409") || !strings.Contains(err.Error(), "provider and family must both be explicit") {
		t.Fatalf("unexpected error message: %v", err)
	}
}

