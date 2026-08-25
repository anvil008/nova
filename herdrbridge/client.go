package herdrbridge

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

type dialFunc func(context.Context, string, string) (net.Conn, error)
type runFunc func(context.Context, []string) ([]byte, []byte, error)

// Client is bound to one explicit Herdr binary, socket, and workspace.
type Client struct {
	config Config
	dial   dialFunc
	run    runFunc
	nextID atomic.Uint64
}

func New(config Config) (*Client, error) {
	validated, err := config.validate()
	if err != nil {
		return nil, err
	}
	c := &Client{config: validated}
	c.dial = (&net.Dialer{}).DialContext
	c.run = c.runBinary
	return c, nil
}

func (c *Client) Config() Config { return c.config }

// Probe verifies both the exact injected executable and the running socket
// protocol before any layout or metadata mutation.
func (c *Client) Probe(ctx context.Context) error {
	if c.config.Mode == ModeOff {
		return ErrDisabled
	}
	stdout, stderr, err := c.run(ctx, []string{"--version"})
	if err != nil {
		return fmt.Errorf("probe herdr binary: %w: %s", err, boundedText(stderr))
	}
	if strings.TrimSpace(string(stdout)) != "herdr "+SupportedVersion {
		return fmt.Errorf("%w: expected herdr %s", ErrIncompatible, SupportedVersion)
	}
	var result struct {
		Type     string `json:"type"`
		Version  string `json:"version"`
		Protocol int    `json:"protocol"`
	}
	if err := c.call(ctx, "ping", map[string]any{}, &result); err != nil {
		return fmt.Errorf("probe herdr socket: %w", err)
	}
	if result.Type != "pong" || result.Version != SupportedVersion || result.Protocol != SupportedProtocol {
		return fmt.Errorf("%w: socket returned type=%q version=%q protocol=%d", ErrIncompatible, result.Type, result.Version, result.Protocol)
	}
	return nil
}

type wireRequest struct {
	ID     string `json:"id"`
	Method string `json:"method"`
	Params any    `json:"params"`
}

type wireResponse struct {
	ID     string          `json:"id"`
	Result json.RawMessage `json:"result"`
	Error  *wireError      `json:"error,omitempty"`
}

type wireError struct {
	Code    string          `json:"code"`
	Message string          `json:"message"`
	Details json.RawMessage `json:"details,omitempty"`
}

func (c *Client) call(ctx context.Context, method string, params any, out any) error {
	if c.config.Mode == ModeOff {
		return ErrDisabled
	}
	ctx, cancel := context.WithTimeout(ctx, c.config.Timeout)
	defer cancel()
	connection, err := c.dial(ctx, "unix", c.config.SocketPath)
	if err != nil {
		return fmt.Errorf("connect explicit herdr socket: %w", err)
	}
	defer connection.Close()
	deadline := time.Now().Add(c.config.Timeout)
	if contextDeadline, ok := ctx.Deadline(); ok && contextDeadline.Before(deadline) {
		deadline = contextDeadline
	}
	if err := connection.SetDeadline(deadline); err != nil {
		return fmt.Errorf("bound herdr socket deadline: %w", err)
	}
	id := "swarm-" + strconv.FormatUint(c.nextID.Add(1), 10)
	if err := json.NewEncoder(connection).Encode(wireRequest{ID: id, Method: method, Params: params}); err != nil {
		return fmt.Errorf("write herdr request: %w", err)
	}
	reader := bufio.NewReader(io.LimitReader(connection, MaxSocketBytes+1))
	line, err := reader.ReadBytes('\n')
	if len(line) > MaxSocketBytes {
		return errors.New("herdr response exceeds bounded size")
	}
	if err != nil {
		return fmt.Errorf("read herdr response: %w", err)
	}
	var response wireResponse
	if err := json.Unmarshal(line, &response); err != nil {
		return fmt.Errorf("decode herdr response: %w", err)
	}
	if response.ID != id {
		return fmt.Errorf("herdr response ID %q does not match request %q", response.ID, id)
	}
	if response.Error != nil {
		return fmt.Errorf("herdr %s error %s: %s", method, response.Error.Code, response.Error.Message)
	}
	if len(response.Result) == 0 || bytes.Equal(response.Result, []byte("null")) {
		return fmt.Errorf("herdr %s returned no result", method)
	}
	if err := json.Unmarshal(response.Result, out); err != nil {
		return fmt.Errorf("decode herdr %s result: %w", method, err)
	}
	return nil
}

func (c *Client) runBinary(ctx context.Context, args []string) ([]byte, []byte, error) {
	ctx, cancel := context.WithTimeout(ctx, c.config.Timeout)
	defer cancel()
	command := exec.CommandContext(ctx, c.config.BinaryPath, args...)
	command.Env = explicitHerdrEnv(os.Environ(), c.config)
	var stdout, stderr limitedBuffer
	stdout.limit, stderr.limit = MaxSocketBytes, MaxSocketBytes
	command.Stdout, command.Stderr = &stdout, &stderr
	err := command.Run()
	if ctx.Err() != nil {
		return stdout.Bytes(), stderr.Bytes(), fmt.Errorf("herdr command timeout: %w", ctx.Err())
	}
	return stdout.Bytes(), stderr.Bytes(), err
}

func explicitHerdrEnv(current []string, config Config) []string {
	result := make([]string, 0, len(current)+4)
	for _, item := range current {
		key, _, _ := strings.Cut(item, "=")
		switch key {
		case "HERDR_ENV", "HERDR_BIN_PATH", "HERDR_SOCKET_PATH", "HERDR_SESSION":
			continue
		default:
			result = append(result, item)
		}
	}
	return append(result,
		"HERDR_ENV=1",
		"HERDR_BIN_PATH="+config.BinaryPath,
		"HERDR_SOCKET_PATH="+config.SocketPath,
		"HERDR_SESSION="+config.SessionID,
	)
}

type limitedBuffer struct {
	buffer bytes.Buffer
	limit  int
}

func (b *limitedBuffer) Write(data []byte) (int, error) {
	if b.buffer.Len()+len(data) > b.limit {
		remaining := b.limit - b.buffer.Len()
		if remaining > 0 {
			_, _ = b.buffer.Write(data[:remaining])
		}
		return len(data), errors.New("command output exceeds bounded size")
	}
	return b.buffer.Write(data)
}

func (b *limitedBuffer) Bytes() []byte { return b.buffer.Bytes() }

func boundedText(data []byte) string {
	text := strings.TrimSpace(string(data))
	if len(text) > 512 {
		return text[:512]
	}
	return text
}
