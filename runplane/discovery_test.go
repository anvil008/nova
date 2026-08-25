package runplane

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

type fakeCommandRunner struct {
	outputs map[string]string
	errors  map[string]error
}

func (f fakeCommandRunner) Output(_ context.Context, name string, args ...string) ([]byte, error) {
	key := name + " " + strings.Join(args, " ")
	return []byte(f.outputs[key]), f.errors[key]
}

func TestDiscoveryAllowlistsOnlyObservedExactAGYModelsAndCanonicalRoles(t *testing.T) {
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessAGY, "workflow-executor", "gemini-config-only", "high")
	writeDefinition(t, roots, HarnessAGY, "workflow-research", "gemini-config-only", "high")
	discoverer := Discoverer{Roots: roots, Runner: fakeCommandRunner{outputs: map[string]string{
		"agy --version": "agy 1.2.3\n",
		"agy --help":    "--agent --model --effort (low|medium|high) --input-format stream-json --output-format --conversation --sandbox",
		"agy models":    "gemini-exact-low\tExact Low\ngemini-exact-high\tExact High\n",
		"agy agents":    "anvil-wf-executor\nanvil-coding-orchestrator\nunmanaged-agent\n",
	}}}
	capability := discoverer.One(context.Background(), HarnessAGY)
	if !capability.Available {
		t.Fatalf("capability unavailable: %s", capability.Error)
	}
	if !reflect.DeepEqual(capability.Models, []string{"gemini-exact-high", "gemini-exact-low"}) {
		t.Fatalf("models = %v", capability.Models)
	}
	if !reflect.DeepEqual(capability.Roles, []string{"anvil-wf-executor"}) {
		t.Fatalf("roles = %v", capability.Roles)
	}
	if !reflect.DeepEqual(capability.Efforts, []string{"high", "low", "medium"}) {
		t.Fatalf("efforts = %v", capability.Efforts)
	}
}

func TestDiscoveryFailsClosedOnMissingRequiredHelpOrCommands(t *testing.T) {
	discoverer := Discoverer{Roots: testDefinitionRoots(t), Runner: fakeCommandRunner{outputs: map[string]string{
		"codex --version":          "codex 1",
		"codex exec --help":        "--model only",
		"codex exec resume --help": "SESSION_ID read from stdin",
	}, errors: map[string]error{"claude --version": errors.New("not found")}}}
	if capability := discoverer.One(context.Background(), HarnessCodex); capability.Available || !strings.Contains(capability.Error, "required") {
		t.Fatalf("codex capability = %+v", capability)
	}
	if capability := discoverer.One(context.Background(), HarnessClaude); capability.Available || capability.Error == "" {
		t.Fatalf("claude capability = %+v", capability)
	}
}

func TestCodexModelCacheDiscoversExplicitTerraMaxPair(t *testing.T) {
	roots := testDefinitionRoots(t)
	if err := os.MkdirAll(roots.CodexHome, 0o700); err != nil {
		t.Fatal(err)
	}
	cache := `{"client_version":"0.147.0","models":[{"slug":"gpt-5.6-terra","visibility":"list","supported_reasoning_levels":[{"effort":"medium"},{"effort":"max"}]}]}`
	if err := os.WriteFile(filepath.Join(roots.CodexHome, "models_cache.json"), []byte(cache), 0o600); err != nil {
		t.Fatal(err)
	}
	capability := Capability{Version: "codex-cli 0.147.0"}
	if err := (Discoverer{Roots: roots}).loadCodexModelEfforts(&capability); err != nil {
		t.Fatal(err)
	}
	if !containsModelEffort(capability.ModelEfforts, "gpt-5.6-terra", "max") {
		t.Fatalf("pairs=%+v", capability.ModelEfforts)
	}
}

func TestClaudeDiscoveryReportsOnlyCanonicalAliasPairsAndFailsClosed(t *testing.T) {
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "", "")
	writeDefinition(t, roots, HarnessClaude, "workflow-code-review", "", "")
	discoverer := Discoverer{Roots: roots, Runner: fakeCommandRunner{outputs: map[string]string{
		"claude --version": "2.1.test",
		"claude --help":    "--agent --agents --setting-sources --model --effort <level> (low, medium, high) --input-format stream-json --output-format --resume",
	}}}
	capability := discoverer.One(context.Background(), HarnessClaude)
	if capability.Available || !strings.Contains(capability.Error, "aliases") {
		t.Fatalf("Claude alias-only capability = %+v", capability)
	}
	if len(capability.ModelEfforts) != 2 {
		t.Fatalf("canonical role pairs = %+v, want exactly two non-Cartesian pairs", capability.ModelEfforts)
	}
	for _, pair := range capability.ModelEfforts {
		if pair.Reference != "alias" || (pair.Model == "opus" && pair.Effort != "medium") || (pair.Model == "fable" && pair.Effort != "high") {
			t.Fatalf("misrepresented Claude pair = %+v", pair)
		}
	}
	if containsModelEffort(capability.ModelEfforts, "opus", "high") {
		t.Fatal("alias was admitted as an exact route model")
	}
}

func testDefinitionRoots(t *testing.T) DefinitionRoots {
	t.Helper()
	root := t.TempDir()
	return DefinitionRoots{HomeDir: root, CodexHome: filepath.Join(root, "codex")}
}

func writeDefinition(t *testing.T, roots DefinitionRoots, harness Harness, roleID, model, effort string) string {
	t.Helper()
	binding, err := loadRoleBinding(roleID)
	if err != nil {
		t.Fatal(err)
	}
	path, err := roots.definitionPath(harness, binding.NativeName)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		t.Fatal(err)
	}
	content, err := expectedDefinition(harness, binding.NativeName)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, content, 0o600); err != nil {
		t.Fatal(err)
	}
	_, _ = model, effort
	return path
}
