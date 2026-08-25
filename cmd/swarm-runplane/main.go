package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/anvil008/swarm-coder/runplane"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func main() {
	if err := run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr); err != nil {
		fmt.Fprintln(os.Stderr, "swarm-runplane:", err)
		os.Exit(1)
	}
}

func run(arguments []string, stdin io.Reader, stdout, _ io.Writer) error {
	if len(arguments) == 0 {
		return errors.New("usage: swarm-runplane <serve|worker|mcp|conformance|health|capabilities|start|list|status|events|send|resume|cancel|evidence>")
	}
	if arguments[0] == "serve" {
		return runServe(arguments[1:], stdout)
	}
	if arguments[0] == "worker" {
		if len(arguments) != 2 {
			return errors.New("worker requires exactly one job ID")
		}
		return runplane.RunWorker(context.Background(), defaultStateDir(), arguments[1])
	}
	if arguments[0] == "mcp" {
		if len(arguments) != 1 {
			return errors.New("mcp accepts no arguments; configure the loopback supervisor through SWARM_RUNPLANE_URL and token environment variables")
		}
		return runMCP(context.Background())
	}
	if arguments[0] == "conformance" {
		return runConformance(arguments[1:], stdout)
	}
	return runClient(arguments, stdin, stdout)
}

func runConformance(arguments []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("conformance", flag.ContinueOnError)
	offline := flags.Bool("offline", false, "run provider-free conformance only")
	definitions := flags.String("definitions", "harness-agents/rendered", "rendered definition root")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if flags.NArg() != 0 || !*offline {
		return errors.New("conformance usage: conformance --offline [--definitions harness-agents/rendered]")
	}
	report, err := runplane.RunOfflineConformance(context.Background(), *definitions)
	if err != nil {
		return err
	}
	data, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	_, err = fmt.Fprintln(stdout, string(data))
	return err
}

func runMCP(ctx context.Context) error {
	base, token, err := clientCredentials()
	if err != nil {
		return err
	}
	client, err := runplane.NewClient(runplane.ClientOptions{BaseURL: base, Token: token})
	if err != nil {
		return err
	}
	server, err := runplane.NewMCPServer(client)
	if err != nil {
		return err
	}
	return server.Run(ctx, &mcp.StdioTransport{})
}

func runServe(arguments []string, stdout io.Writer) error {
	flags := flag.NewFlagSet("serve", flag.ContinueOnError)
	listen := flags.String("listen", "127.0.0.1:8083", "loopback listen address")
	state := flags.String("state", defaultStateDir(), "absolute state directory")
	maximum := flags.Int("max-concurrent", runplane.DefaultMaxConcurrent, "hard maximum concurrent supervised jobs")
	visibility := flags.String("visibility", "off", "foreign-job visibility mode: off, auto, or required")
	herdrBinary := flags.String("herdr-bin", os.Getenv("HERDR_BIN_PATH"), "explicit absolute Herdr 0.8.2 binary")
	herdrSocket := flags.String("herdr-socket", os.Getenv("HERDR_SOCKET_PATH"), "explicit absolute Herdr socket")
	herdrSession := flags.String("herdr-session", os.Getenv("HERDR_SESSION"), "explicit Herdr session identity")
	herdrWorkspace := flags.String("herdr-workspace", os.Getenv("HERDR_WORKSPACE_ID"), "explicit Herdr workspace identity")
	herdrTimeout := flags.Duration("herdr-timeout", 5*time.Second, "bounded Herdr operation timeout")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return errors.New("serve accepts no positional arguments")
	}
	absolute, err := filepath.Abs(*state)
	if err != nil {
		return err
	}
	workerBinary, err := os.Executable()
	if err != nil {
		return fmt.Errorf("resolve stable worker binary: %w", err)
	}
	supervisor, err := runplane.NewSupervisor(runplane.Options{
		StateDir: absolute, MaxConcurrent: *maximum,
		Visibility: runplane.VisibilityConfig{
			Mode: runplane.VisibilityMode(*visibility), HerdrEnv: os.Getenv("HERDR_ENV") == "1",
			BinaryPath: *herdrBinary, SocketPath: *herdrSocket, SessionID: *herdrSession,
			WorkspaceID: *herdrWorkspace, WorkerBinary: workerBinary, Timeout: *herdrTimeout,
		},
	})
	if err != nil {
		return err
	}
	defer supervisor.Close()
	listener, err := runplane.ListenLoopback(*listen)
	if err != nil {
		return err
	}
	fmt.Fprintf(stdout, "swarm-runplane listening on http://%s\n", listener.Addr())
	fmt.Fprintf(stdout, "authentication token file: %s\n", filepath.Join(absolute, "auth.token"))
	server := supervisor.HTTPServer()
	return server.Serve(listener)
}

func runClient(arguments []string, stdin io.Reader, stdout io.Writer) error {
	base, token, err := clientCredentials()
	if err != nil {
		return err
	}
	client, err := runplane.NewClient(runplane.ClientOptions{BaseURL: base, Token: token})
	if err != nil {
		return err
	}
	command := arguments[0]
	args := arguments[1:]
	ctx := context.Background()
	var output any
	switch command {
	case "health":
		if len(args) != 0 {
			return errors.New("health accepts no arguments")
		}
		output, err = client.Health(ctx)
	case "capabilities":
		if len(args) != 0 {
			return errors.New("capabilities accepts no arguments")
		}
		output, err = client.Capabilities(ctx)
	case "list":
		if len(args) != 0 {
			return errors.New("list accepts no arguments")
		}
		output, err = client.List(ctx)
	case "start":
		flags := flag.NewFlagSet("start", flag.ContinueOnError)
		requestPath := flags.String("request", "-", "request JSON path or - for stdin")
		if err := flags.Parse(args); err != nil || flags.NArg() != 0 {
			return errors.New("start usage: start --request <path|->")
		}
		data, err := readInput(*requestPath, stdin)
		if err != nil {
			return err
		}
		var input runplane.StartRequest
		if err := json.Unmarshal(data, &input); err != nil {
			return fmt.Errorf("decode start request: %w", err)
		}
		output, err = client.Start(ctx, input)
	case "status", "cancel", "evidence":
		if len(args) != 1 {
			return fmt.Errorf("%s requires one job ID", command)
		}
		switch command {
		case "status":
			output, err = client.Status(ctx, args[0])
		case "cancel":
			err = client.Cancel(ctx, args[0])
			output = map[string]bool{"accepted": err == nil}
		case "evidence":
			output, err = client.Evidence(ctx, args[0])
		}
	case "events":
		flags := flag.NewFlagSet("events", flag.ContinueOnError)
		after := flags.Uint64("after", 0, "replay events after sequence")
		if err := flags.Parse(args); err != nil || flags.NArg() != 1 {
			return errors.New("events usage: events [--after N] <job-id>")
		}
		output, err = client.Events(ctx, flags.Arg(0), *after)
	case "send", "resume":
		if len(args) != 1 {
			return fmt.Errorf("%s requires one job ID; message text is read from stdin", command)
		}
		limit := int64(64 << 10)
		if command == "resume" {
			limit = 256 << 10
		}
		data, readErr := io.ReadAll(io.LimitReader(stdin, limit+1))
		if readErr != nil {
			return readErr
		}
		if int64(len(data)) > limit {
			return fmt.Errorf("stdin %s exceeds %d bytes", command, limit)
		}
		if command == "send" {
			err = client.Send(ctx, args[0], string(data))
			output = map[string]bool{"accepted": err == nil}
		} else {
			output, err = client.Resume(ctx, args[0], string(data))
		}
	default:
		return fmt.Errorf("unknown command %q", command)
	}
	if err != nil {
		return err
	}
	pretty, err := json.MarshalIndent(output, "", "  ")
	if err != nil {
		return err
	}
	_, err = fmt.Fprintln(stdout, string(pretty))
	return err
}

func clientCredentials() (string, string, error) {
	base := os.Getenv("SWARM_RUNPLANE_URL")
	if base == "" {
		base = "http://127.0.0.1:8083"
	}
	token := os.Getenv("SWARM_RUNPLANE_TOKEN")
	if token == "" {
		if tokenFile := os.Getenv("SWARM_RUNPLANE_TOKEN_FILE"); tokenFile != "" {
			if data, readErr := os.ReadFile(tokenFile); readErr == nil {
				token = strings.TrimSpace(string(data))
			} else {
				return "", "", fmt.Errorf("read SWARM_RUNPLANE_TOKEN_FILE: %w", readErr)
			}
		}
	}
	if token == "" {
		if data, readErr := os.ReadFile(filepath.Join(defaultStateDir(), "auth.token")); readErr == nil {
			token = strings.TrimSpace(string(data))
		}
	}
	if token == "" {
		return "", "", errors.New("set SWARM_RUNPLANE_TOKEN or use the default state token")
	}
	return base, token, nil
}

func defaultStateDir() string {
	if value := os.Getenv("SWARM_RUNPLANE_STATE"); value != "" {
		return value
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".local", "state", "swarm-runplane")
}

func readInput(path string, stdin io.Reader) ([]byte, error) {
	if path == "-" {
		return io.ReadAll(io.LimitReader(stdin, 256<<10))
	}
	return os.ReadFile(path)
}
