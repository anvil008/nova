package herdrbridge

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"net"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"
)

func testConfig() Config {
	return Config{
		Mode: ModeAuto, HerdrEnv: true, BinaryPath: "/opt/herdr-0.8.2/bin/herdr",
		SocketPath: "/run/user/1000/herdr.sock", SessionID: "swarm-session", WorkspaceID: "opaque-workspace", Timeout: time.Second,
	}
}

func TestClientRequiresExplicitInjectedRuntime(t *testing.T) {
	for name, mutate := range map[string]func(*Config){
		"marker":    func(config *Config) { config.HerdrEnv = false },
		"binary":    func(config *Config) { config.BinaryPath = "herdr" },
		"socket":    func(config *Config) { config.SocketPath = "herdr.sock" },
		"session":   func(config *Config) { config.SessionID = "" },
		"workspace": func(config *Config) { config.WorkspaceID = "" },
	} {
		t.Run(name, func(t *testing.T) {
			config := testConfig()
			mutate(&config)
			if _, err := New(config); err == nil {
				t.Fatal("unsafe ambient configuration was accepted")
			}
		})
	}
	off, err := New(Config{Mode: ModeOff})
	if err != nil || off.Config().Mode != ModeOff {
		t.Fatalf("off mode should not target a runtime: client=%#v err=%v", off, err)
	}
}

func TestClientProbePinsVersionAndProtocol(t *testing.T) {
	client := scriptedClient(t, []func(wireRequest) any{
		func(request wireRequest) any {
			if request.Method != "ping" {
				t.Fatalf("method = %q, want ping", request.Method)
			}
			return map[string]any{"type": "pong", "version": SupportedVersion, "protocol": SupportedProtocol}
		},
	})
	client.run = func(_ context.Context, args []string) ([]byte, []byte, error) {
		if !reflect.DeepEqual(args, []string{"--version"}) {
			t.Fatalf("version argv = %#v", args)
		}
		return []byte("herdr 0.8.2\n"), nil, nil
	}
	if err := client.Probe(context.Background()); err != nil {
		t.Fatal(err)
	}

	bad := scriptedClient(t, []func(wireRequest) any{
		func(wireRequest) any { return map[string]any{"type": "pong", "version": "0.8.3", "protocol": 21} },
	})
	bad.run = client.run
	if err := bad.Probe(context.Background()); !errors.Is(err, ErrIncompatible) {
		t.Fatalf("Probe error = %v, want incompatible", err)
	}
}

func TestClientUsesOnlyExplicitSocketAndBoundedResponse(t *testing.T) {
	client, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	client.dial = func(_ context.Context, network, address string) (net.Conn, error) {
		if network != "unix" || address != testConfig().SocketPath {
			t.Fatalf("dialed %s %s", network, address)
		}
		server, peer := net.Pipe()
		go func() {
			defer peer.Close()
			var request wireRequest
			_ = json.NewDecoder(peer).Decode(&request)
			_, _ = peer.Write(append(make([]byte, MaxSocketBytes+1), '\n'))
		}()
		return server, nil
	}
	var output any
	if err := client.call(context.Background(), "ping", map[string]any{}, &output); err == nil || !strings.Contains(err.Error(), "bounded") {
		t.Fatalf("oversized response error = %v", err)
	}
}

func TestClientSocketLossIsNotSuccess(t *testing.T) {
	client, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	lost := errors.New("socket lost")
	client.dial = func(context.Context, string, string) (net.Conn, error) { return nil, lost }
	var result any
	err = client.call(context.Background(), "session.snapshot", map[string]any{}, &result)
	if err == nil || !strings.Contains(err.Error(), lost.Error()) {
		t.Fatalf("socket loss error = %v", err)
	}
	outcome := Outcome(ModeAuto, err)
	if outcome.Visible || outcome.Error == nil {
		t.Fatalf("socket loss was treated as success: %#v", outcome)
	}
}

func TestClientSocketTimeoutIsBounded(t *testing.T) {
	config := testConfig()
	config.Timeout = 20 * time.Millisecond
	client, err := New(config)
	if err != nil {
		t.Fatal(err)
	}
	client.dial = func(context.Context, string, string) (net.Conn, error) {
		local, peer := net.Pipe()
		go func() {
			time.Sleep(100 * time.Millisecond)
			_ = peer.Close()
		}()
		return local, nil
	}
	started := time.Now()
	var result any
	err = client.call(context.Background(), "session.snapshot", map[string]any{}, &result)
	if err == nil || time.Since(started) > 500*time.Millisecond {
		t.Fatalf("bounded timeout error=%v elapsed=%s", err, time.Since(started))
	}
}

func TestClientEnvironmentRejectsAmbientSession(t *testing.T) {
	env := explicitHerdrEnv([]string{
		"PATH=/usr/bin", "HERDR_SESSION=focused", "HERDR_SOCKET_PATH=/wrong", "HERDR_BIN_PATH=/wrong", "HERDR_ENV=0",
	}, testConfig())
	joined := strings.Join(env, "\n")
	for _, forbidden := range []string{"HERDR_SESSION=focused", "HERDR_SOCKET_PATH=/wrong", "HERDR_BIN_PATH=/wrong", "HERDR_ENV=0"} {
		if strings.Contains(joined, forbidden) {
			t.Fatalf("ambient selector survived: %s in %q", forbidden, joined)
		}
	}
	for _, expected := range []string{"HERDR_ENV=1", "HERDR_SESSION=swarm-session", "HERDR_SOCKET_PATH=/run/user/1000/herdr.sock", "HERDR_BIN_PATH=/opt/herdr-0.8.2/bin/herdr"} {
		if !strings.Contains(joined, expected) {
			t.Fatalf("missing explicit selector %s in %q", expected, joined)
		}
	}
}

func scriptedClient(t *testing.T, handlers []func(wireRequest) any) *Client {
	t.Helper()
	client, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	var mu sync.Mutex
	index := 0
	client.dial = func(_ context.Context, _, _ string) (net.Conn, error) {
		mu.Lock()
		if index >= len(handlers) {
			mu.Unlock()
			return nil, errors.New("unexpected socket call")
		}
		handler := handlers[index]
		index++
		mu.Unlock()
		clientConn, serverConn := net.Pipe()
		go func() {
			defer serverConn.Close()
			reader := bufio.NewReader(serverConn)
			line, readErr := reader.ReadBytes('\n')
			if readErr != nil {
				return
			}
			var request wireRequest
			if json.Unmarshal(line, &request) != nil {
				return
			}
			result := handler(request)
			_ = json.NewEncoder(serverConn).Encode(map[string]any{"id": request.ID, "result": result})
		}()
		return clientConn, nil
	}
	return client
}
