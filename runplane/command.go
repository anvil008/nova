package runplane

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

type InputMode string

const (
	InputPlain     InputMode = "plain"
	InputNDJSON    InputMode = "ndjson"
	InputAGYNDJSON InputMode = "agy-ndjson"
)

type CommandSpec struct {
	Name      string
	Args      []string
	Directory string
	InputMode InputMode
}

func buildCommand(admitted admittedRoute, resumeSession string) (CommandSpec, error) {
	route := admitted.Route
	switch route.TargetHarness {
	case HarnessCodex:
		if resumeSession == "" {
			return CommandSpec{Name: "codex", Directory: route.RepositoryRoot, InputMode: InputPlain, Args: []string{
				"exec", "--profile", admitted.Binding.NativeName, "--model", route.ExactModel,
				"-c", "model_reasoning_effort=" + strconv.Quote(route.Effort), "--json", "--cd", route.RepositoryRoot,
				"--sandbox", string(route.CapabilityMode), "-",
			}}, nil
		}
		return CommandSpec{Name: "codex", Directory: route.RepositoryRoot, InputMode: InputPlain, Args: []string{
			"exec", "resume", "--model", route.ExactModel, "-c", "model_reasoning_effort=" + strconv.Quote(route.Effort), "--json", resumeSession, "-",
		}}, nil
	case HarnessClaude:
		agent, err := parseCanonicalClaudeAgent(admitted.DefinitionBytes, admitted.Binding.NativeName)
		if err != nil {
			return CommandSpec{}, err
		}
		agentJSON, err := json.Marshal(map[string]canonicalClaudeAgent{admitted.Binding.NativeName: agent})
		if err != nil {
			return CommandSpec{}, fmt.Errorf("encode exact Claude agent override: %w", err)
		}
		args := []string{"-p", "--agents", string(agentJSON), "--agent", admitted.Binding.NativeName, "--setting-sources", "user", "--model", route.ExactModel, "--effort", route.Effort,
			"--input-format", "stream-json", "--output-format", "stream-json", "--verbose"}
		if route.CapabilityMode == ModeReadOnly {
			args = append(args, "--permission-mode", "plan")
		} else {
			args = append(args, "--permission-mode", "acceptEdits")
		}
		if resumeSession != "" {
			args = append(args, "--resume", resumeSession)
		}
		return CommandSpec{Name: "claude", Args: args, Directory: route.RepositoryRoot, InputMode: InputNDJSON}, nil
	case HarnessAGY:
		args := []string{"--agent", admitted.Binding.NativeName, "--model", route.ExactModel, "--effort", route.Effort,
			"--input-format", "stream-json", "--output-format", "stream-json", "--sandbox"}
		if route.CapabilityMode == ModeWorkspaceWrite {
			args = append(args, "--mode", "accept-edits")
		} else {
			args = append(args, "--mode", "plan")
		}
		if resumeSession != "" {
			args = append(args, "--conversation", resumeSession)
		}
		// agy's --print accepts an optional prompt value. Keep it last so the
		// next option is never mistaken for prompt text; actual input is NDJSON.
		args = append(args, "--print=")
		return CommandSpec{Name: "agy", Args: args, Directory: route.RepositoryRoot, InputMode: InputAGYNDJSON}, nil
	default:
		return CommandSpec{}, fmt.Errorf("unsupported target harness %q", route.TargetHarness)
	}
}

type canonicalClaudeAgent struct {
	Description    string                                `json:"description"`
	Tools          []string                              `json:"tools"`
	Prompt         string                                `json:"prompt"`
	Model          string                                `json:"model"`
	Effort         string                                `json:"effort"`
	PermissionMode string                                `json:"permissionMode"`
	MCPServers     []map[string]canonicalClaudeMCPServer `json:"mcpServers"`
}

type canonicalClaudeMCPServer struct {
	Type    string   `json:"type"`
	Command string   `json:"command"`
	Args    []string `json:"args"`
}

func parseCanonicalClaudeAgent(definition []byte, expectedName string) (canonicalClaudeAgent, error) {
	const opening = "---\n"
	const closing = "\n---\n\n"
	if !bytes.HasPrefix(definition, []byte(opening)) {
		return canonicalClaudeAgent{}, fmt.Errorf("canonical Claude definition lacks frontmatter")
	}
	end := bytes.Index(definition[len(opening):], []byte(closing))
	if end < 0 {
		return canonicalClaudeAgent{}, fmt.Errorf("canonical Claude definition has malformed frontmatter")
	}
	metadata := string(definition[len(opening) : len(opening)+end])
	prompt := string(definition[len(opening)+end+len(closing):])
	values := map[string]string{}
	for _, line := range strings.Split(metadata, "\n") {
		key, value, ok := strings.Cut(line, ": ")
		if !ok || values[key] != "" {
			return canonicalClaudeAgent{}, fmt.Errorf("canonical Claude definition has malformed metadata")
		}
		values[key] = value
	}
	if values["name"] != expectedName {
		return canonicalClaudeAgent{}, fmt.Errorf("canonical Claude definition name %q does not match %q", values["name"], expectedName)
	}
	description, err := strconv.Unquote(values["description"])
	if err != nil {
		return canonicalClaudeAgent{}, fmt.Errorf("decode canonical Claude description: %w", err)
	}
	model, err := strconv.Unquote(values["model"])
	if err != nil {
		return canonicalClaudeAgent{}, fmt.Errorf("decode canonical Claude model: %w", err)
	}
	tools := strings.Split(values["tools"], ", ")
	var mcpServers []map[string]canonicalClaudeMCPServer
	if err := json.Unmarshal([]byte(values["mcpServers"]), &mcpServers); err != nil {
		return canonicalClaudeAgent{}, fmt.Errorf("decode canonical Claude MCP servers: %w", err)
	}
	if len(tools) == 0 || tools[0] == "" || values["effort"] == "" || values["permissionMode"] == "" {
		return canonicalClaudeAgent{}, fmt.Errorf("canonical Claude definition omits required agent metadata")
	}
	if len(values) != 7 {
		return canonicalClaudeAgent{}, fmt.Errorf("canonical Claude definition has unexpected agent metadata")
	}
	return canonicalClaudeAgent{
		Description: description, Tools: tools, Prompt: strings.TrimSuffix(prompt, "\n"),
		Model: model, Effort: values["effort"], PermissionMode: values["permissionMode"], MCPServers: mcpServers,
	}, nil
}

func encodeInput(mode InputMode, message string) ([]byte, error) {
	if mode == InputPlain {
		return []byte(message + "\n"), nil
	}
	if mode == InputAGYNDJSON {
		encoded, err := json.Marshal(map[string]any{
			"event":   "user",
			"message": map[string]any{"content": message},
		})
		if err != nil {
			return nil, fmt.Errorf("encode agy stream input: %w", err)
		}
		return append(encoded, '\n'), nil
	}
	encoded, err := json.Marshal(map[string]any{
		"type":               "user",
		"message":            map[string]any{"role": "user", "content": message},
		"parent_tool_use_id": nil,
	})
	if err != nil {
		return nil, fmt.Errorf("encode stream input: %w", err)
	}
	return append(encoded, '\n'), nil
}
