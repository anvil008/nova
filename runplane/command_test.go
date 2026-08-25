package runplane

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"slices"
	"strings"
	"testing"
)

func TestCommandConstructionUsesExactNativeRoleAndNeverPromptArgv(t *testing.T) {
	promptMarker := "PROMPT-MUST-STAY-OFF-ARGV"
	for _, test := range []struct {
		harness Harness
		resume  string
		want    []string
		mode    InputMode
	}{
		{HarnessCodex, "", []string{"exec", "--profile", "anvil-wf-executor", "--model", "gpt-exact", "--json", "--cd", "/repo", "--sandbox", "workspace-write", "-"}, InputPlain},
		{HarnessCodex, "thread-1", []string{"exec", "resume", "--model", "gpt-exact", "--json", "thread-1", "-"}, InputPlain},
		{HarnessClaude, "session-1", []string{"-p", "--agent", "anvil-wf-executor", "--model", "claude-exact", "--input-format", "stream-json", "--output-format", "stream-json", "--resume", "session-1"}, InputNDJSON},
		{HarnessAGY, "conversation-1", []string{"--print=", "--agent", "anvil-wf-executor", "--model", "gemini-exact", "--input-format", "stream-json", "--output-format", "stream-json", "--sandbox", "--conversation", "conversation-1"}, InputAGYNDJSON},
	} {
		t.Run(string(test.harness)+test.resume, func(t *testing.T) {
			definition, err := expectedDefinition(test.harness, "anvil-wf-executor")
			if err != nil {
				t.Fatal(err)
			}
			admitted := admittedRoute{Route: Route{TargetHarness: test.harness, ExactModel: test.want[4], Effort: "high", RepositoryRoot: "/repo", CapabilityMode: ModeWorkspaceWrite}, Binding: roleBinding{NativeName: "anvil-wf-executor"}, DefinitionBytes: definition, Prompt: promptMarker}
			// Correct model positions differ on resume, set explicitly after construction input.
			if test.harness == HarnessCodex {
				admitted.Route.ExactModel = "gpt-exact"
			} else if test.harness == HarnessClaude {
				admitted.Route.ExactModel = "claude-exact"
			} else {
				admitted.Route.ExactModel = "gemini-exact"
			}
			spec, err := buildCommand(admitted, test.resume)
			if err != nil {
				t.Fatal(err)
			}
			if spec.InputMode != test.mode {
				t.Fatalf("input mode = %q, want %q", spec.InputMode, test.mode)
			}
			joined := strings.Join(spec.Args, "\x00")
			if strings.Contains(joined, promptMarker) {
				t.Fatalf("prompt leaked into argv: %q", spec.Args)
			}
			for _, wanted := range test.want {
				if !slices.Contains(spec.Args, wanted) {
					t.Errorf("argv %q missing %q", spec.Args, wanted)
				}
			}
			input, err := encodeInput(spec.InputMode, promptMarker)
			if err != nil {
				t.Fatal(err)
			}
			if !strings.Contains(string(input), promptMarker) {
				t.Fatalf("stdin input does not contain prompt: %q", input)
			}
			if spec.InputMode != InputPlain {
				var message map[string]any
				if err := json.Unmarshal(input, &message); err != nil {
					t.Fatalf("NDJSON input: %v", err)
				}
				if spec.InputMode == InputNDJSON && message["type"] != "user" {
					t.Fatalf("message type = %v", message["type"])
				}
				if spec.InputMode == InputAGYNDJSON && message["event"] != "user" {
					t.Fatalf("message event = %v", message["event"])
				}
			}
		})
	}
}

func TestClaudeInvocationOverridesConflictingProjectAgentWithCanonicalDefinition(t *testing.T) {
	binding, err := loadRoleBinding("workflow-research")
	if err != nil {
		t.Fatal(err)
	}
	definition, err := expectedDefinition(HarnessClaude, binding.NativeName)
	if err != nil {
		t.Fatal(err)
	}
	repository := testRepository(t)
	conflict := filepath.Join(repository, ".claude", "agents", binding.NativeName+".md")
	if err := os.MkdirAll(filepath.Dir(conflict), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(conflict, []byte("---\nname: "+binding.NativeName+"\n---\nMALICIOUS LOCAL OVERRIDE\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	admitted := admittedRoute{Route: Route{TargetHarness: HarnessClaude, ExactModel: "opus", Effort: "high", RepositoryRoot: repository, CapabilityMode: ModeReadOnly}, Binding: binding, DefinitionBytes: definition}
	spec, err := buildCommand(admitted, "")
	if err != nil {
		t.Fatal(err)
	}
	index := slices.Index(spec.Args, "--agents")
	if index < 0 || index+1 >= len(spec.Args) {
		t.Fatalf("argv lacks --agents: %q", spec.Args)
	}
	var agents map[string]canonicalClaudeAgent
	if err := json.Unmarshal([]byte(spec.Args[index+1]), &agents); err != nil {
		t.Fatal(err)
	}
	want, err := parseCanonicalClaudeAgent(definition, binding.NativeName)
	if err != nil {
		t.Fatal(err)
	}
	if got := agents[binding.NativeName]; !reflect.DeepEqual(got, want) {
		t.Fatalf("CLI agent override = %+v, want exact rendered semantics %+v", got, want)
	}
	if !slices.Contains(spec.Args, "user") || !slices.Contains(spec.Args, "--setting-sources") {
		t.Fatalf("project settings not excluded: %q", spec.Args)
	}
}
