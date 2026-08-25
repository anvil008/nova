package main

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
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
