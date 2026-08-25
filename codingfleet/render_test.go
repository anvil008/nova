package codingfleet

import (
	"bytes"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
)

func TestRenderProjectsEveryRoleDeterministically(t *testing.T) {
	document := mustLoad(t)
	root := filepath.Join(string(filepath.Separator), "srv", "swarm")
	first, err := Render(root, document)
	if err != nil {
		t.Fatalf("Render() error = %v", err)
	}
	second, err := Render(root, document)
	if err != nil {
		t.Fatalf("second Render() error = %v", err)
	}
	if !reflect.DeepEqual(first, second) {
		t.Fatal("Render() is not deterministic")
	}
	if got, want := len(first.Files), len(document.Roles)*3+4; got != want {
		t.Fatalf("rendered files = %d, want %d", got, want)
	}

	counts := map[string]int{}
	paths := make([]string, 0, len(first.Files))
	for _, file := range first.Files {
		provider := strings.SplitN(file.Path, "/", 2)[0]
		counts[provider]++
		paths = append(paths, file.Path)
		if bytes.Contains(file.Content, []byte("{{")) || bytes.Contains(file.Content, []byte("<ROLE")) {
			t.Errorf("%s contains an unresolved placeholder", file.Path)
		}
	}
	if !sort.StringsAreSorted(paths) {
		t.Fatal("rendered files are not sorted by path")
	}
	for _, provider := range []string{"antigravity", "claude", "codex"} {
		if got, want := counts[provider], len(document.Roles); got != want {
			t.Errorf("%s files = %d, want %d", provider, got, want)
		}
	}
	if got, want := counts["knowledge"], 4; got != want {
		t.Errorf("knowledge files = %d, want %d", got, want)
	}
	if got := bytes.Count(first.CodexConfigBlock, []byte("[agents.")); got != len(document.Roles) {
		t.Fatalf("Codex declarations = %d, want %d", got, len(document.Roles))
	}
	if bytes.Contains(first.CodexConfigBlock, []byte("\nname =")) {
		t.Fatal("Codex declarations contain unsupported name field")
	}
}

func TestRenderNativeMappingsByCapabilityAndTier(t *testing.T) {
	document := mustLoad(t)
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)

	// lens-browser and env-homelab are both workhorse leaves; they differ by
	// capability mode (read-only vs workspace-write), not by tier/model.
	readOnlyClaude := string(files["claude/anvil-cf-lens-browser.md"])
	assertContains(t, readOnlyClaude,
		"tools: Read, Grep, Glob\n",
		"model: \"opus\"\n",
		"effort: medium\n",
		"permissionMode: plan\n",
	)
	assertNotContains(t, readOnlyClaude, "Edit", "Write", "Bash", "commandExecutionPolicy")

	writeClaude := string(files["claude/anvil-cf-toolchain-go.md"])
	assertContains(t, writeClaude,
		"tools: Read, Grep, Glob, Edit, Write, Bash\n",
		"permissionMode: default\n",
	)

	writeClaudeEnv := string(files["claude/anvil-cf-env-homelab.md"])
	assertContains(t, writeClaudeEnv, "model: \"opus\"\n", "effort: medium\n")

	readOnlyAntigravity := string(files["antigravity/anvil-cf-lens-browser/agent.md"])
	assertContains(t, readOnlyAntigravity,
		"  - view_file\n",
		"  - grep_search\n",
		"mainAgent: true\n",
		"subagent: true\n",
		"model: \"gemini-3.7-flash-high\"\n",
		"commandExecutionPolicy: off\n",
	)
	assertNotContains(t, readOnlyAntigravity, "replace_file_content", "run_command", "permissionMode", "effort:")

	writeAntigravity := string(files["antigravity/anvil-cf-env-homelab/agent.md"])
	assertContains(t, writeAntigravity,
		"  - replace_file_content\n",
		"  - run_command\n",
		"model: \"gemini-3.7-flash-high\"\n",
		"commandExecutionPolicy: sandbox\n",
	)

	readOnlyCodex := string(files["codex/anvil-cf-lens-browser.toml"])
	assertContains(t, readOnlyCodex,
		"model = \"gpt-5.6-sol\"\n",
		"model_reasoning_effort = \"medium\"\n",
		"sandbox_mode = \"read-only\"\n",
		"developer_instructions = ",
	)
	assertNotContains(t, readOnlyCodex, "name =", "description =", "permissionMode")

	writeCodexEnv := string(files["codex/anvil-cf-env-homelab.toml"])
	assertContains(t, writeCodexEnv,
		"model = \"gpt-5.6-sol\"\n",
		"model_reasoning_effort = \"medium\"\n",
		"sandbox_mode = \"workspace-write\"\n",
	)
}

func TestRenderFlatOrchestratorAndWorkflowUnits(t *testing.T) {
	document := mustLoad(t)
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)

	orchestratorClaude := string(files["claude/anvil-coding-orchestrator.md"])
	assertContains(t, orchestratorClaude,
		"name: anvil-coding-orchestrator\n",
		"tools: Agent, Skill, Read, Grep, Glob, mcp__anvil-swarm-runplane__swarm_runplane_lifecycle\n",
		`mcpServers: [{"anvil-swarm-runplane":{"type":"stdio","command":"/home/anvil/.local/bin/swarm-runplane","args":["mcp"]}}]`,
		"Workflow stages:\n",
		"anvil-wf-research",
		"anvil-wf-planner",
		"anvil-wf-executor",
		"anvil-wf-code-review",
		"Durable goal and scheduling contract:\n",
		"Goal mode: native-durable.",
		"Checkpoint policy: file-and-native-session.",
		"`checkpoint.json` plus a short `plan.md` under `~/.local/state/swarm-runplane/goals/<goalId>/`",
		// The orchestrator holds no filesystem write authority, so the only
		// executable way to persist a checkpoint is the lifecycle goal verb.
		"only through the `goal` verb",
		"swarm-runplane goal checkpoint",
		"never through a file tool",
		"Tools allowed: `cancel`, `dispatch`, `evidence`, `goal`, `message`, `monitor`, `resume`. Tools denied: `edit`, `shell`, `test`, `write`. Filesystem read: `.`. Filesystem write: none.",
		"system of record and native session state is only a cache",
		"Scheduling policy: dependency-aware.",
		"Proactive delegation is enabled",
		"Completion authority is exclusive to Coding Orchestrator Agent",
		"User-directed model routing contract:",
		"use Terra Max for all subagents",
		"use Gemini 3.7 Flash for execution and Opus for planning",
		"An explicit user route overrides fleet defaults.",
		"Fail closed on ambiguous, conflicting, or unavailable requests",
		"native-subagent-explicit-model-effort",
		"supervisor-exact-role-headless",
		"When the requested model belongs to the current harness provider, always use that harness's native subagent mechanism",
		"Agy/Antigravity uses native Gemini agents",
		"Do not use the shared launcher for same-provider work",
		"Use the installed shared launcher only when the requested provider differs",
		"exact matching canonical workflow or specialist definition",
		"Never replace the role contract with a generic prompt",
		"Common handoff boundary: `anvil.agent-handoff/v1`",
		"runId, parentRunId, canonicalRole (the canonical catalog role ID), provider, model, effort, mode, ownedFiles, limits, changedFiles, tests, result, and disposition",
		"two total verification passes",
		"capability-first-fail-closed",
		"/home/anvil/.local/bin/swarm-runplane health",
		"/home/anvil/.local/bin/swarm-runplane capabilities",
		"/home/anvil/.local/bin/swarm-runplane start --request route.json",
		"request-file-and-stdin",
		"follow-up and resumed input always travel on stdin, never argv",
		"/home/anvil/.local/share/anvil-coding-fleet/swarm-runplane-foreign-dispatch.md",
		"Read that absolute path only when a foreign dispatch is actually required",
		"retains monitor, resume, message, cancel, evidence reconciliation, integration, and completion authority",
		"Execution boundary: orchestrate only.",
		"Proactively use up to 25 independent workflow units",
		"logical fleet ceiling, not a promise that the active harness or provider exposes that many slots",
		"the orchestrator does not bypass the workflow layer",
		"This agent is orchestration-only.",
	)
	// The full run-plane lifecycle reference lives in the foreign-dispatch skill,
	// not in every orchestrator turn.
	assertNotContains(t, orchestratorClaude, "Shared specialist pools:", "anvil.workflow-result/v1", "anvil.authority/v1", "Edit", "Write", "Bash",
		"swarm-runplane serve", "http://127.0.0.1:8083", "auth.token",
		"SWARM_RUNPLANE_STATE", "SWARM_RUNPLANE_URL", "SWARM_RUNPLANE_TOKEN", "SWARM_RUNPLANE_TOKEN_FILE",
		"events --after N JOB_ID", "send JOB_ID", "resume JOB_ID", "cancel JOB_ID", "evidence JOB_ID")

	orchestratorAntigravity := string(files["antigravity/anvil-coding-orchestrator/agent.md"])
	assertContains(t, orchestratorAntigravity,
		"  - invoke_subagent\n",
		"  - swarm_runplane_lifecycle\n",
		"mainAgent: true\n",
		"subagent: true\n",
		"model: \"gemini-3.1-pro-high\"\n",
		"User-directed model routing contract:",
	)
	assertNotContains(t, orchestratorAntigravity, "replace_file_content", "run_command")

	orchestratorCodex := string(files["codex/anvil-coding-orchestrator.toml"])
	assertContains(t, orchestratorCodex,
		"model = \"gpt-5.6-sol\"\n",
		"sandbox_mode = \"read-only\"\n",
		"You are Coding Orchestrator Agent, the single coding entrypoint",
		"Lane: orchestration.",
		"the only default entrypoint for coding tasks",
		"User-directed model routing contract:",
	)

	executor := string(files["codex/anvil-wf-executor.toml"])
	assertContains(t, executor,
		"sandbox_mode = \"workspace-write\"",
		"Executor Agent, a peer execution workflow unit",
		"dispatched by Coding Orchestrator Agent",
		"Shared specialist pools:",
		"Run no more than 20 independent specialist delegates concurrently.",
	)
	assertContains(t, string(rendered.CodexConfigBlock), "[agents.anvil-coding-orchestrator]\n")
	assertNotContains(t, string(rendered.CodexConfigBlock), "[agents.anvil-deep-code]\n")
}

func TestRenderEveryAntigravityRoleIsHeadlessAndSubagentSelectable(t *testing.T) {
	document := mustLoad(t)
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)
	for _, role := range document.Roles {
		name := nativeAgentName(role)
		content := string(files["antigravity/"+name+"/agent.md"])
		assertContains(t, content,
			"name: "+name+"\n",
			"mainAgent: true\n",
			"subagent: true\n",
		)
	}
}

func TestRenderEveryWorkflowUnitGetsSharedPoolsAndCorrectGapRouting(t *testing.T) {
	document := mustLoad(t)
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)

	for _, role := range document.Roles {
		if role.Class != ClassWorkflow {
			continue
		}
		name := nativeAgentName(role)
		antigravity := string(files["antigravity/"+name+"/agent.md"])
		assertContains(t, antigravity, "mainAgent: true\n")
		assertContains(t, antigravity, "subagent: true\n")
		paths := []string{
			"claude/" + name + ".md",
			"codex/" + name + ".toml",
			"antigravity/" + name + "/agent.md",
		}
		for _, providerPath := range paths {
			content := string(files[providerPath])
			if role.ID == workflowCodingOrchestratorID {
				assertContains(t, content, "Durable goal and scheduling contract:", "Workflow units (complete peer layer):")
				assertNotContains(t, content, "Shared specialist pools:")
				continue
			}
			assertContains(t, content,
				"Shared specialist pools:",
				"Technical pool (`anvil-cf-technical-*`)",
				"Domain pool (`anvil-cf-domain-*`)",
				"no leaf specialist is mandatory by default",
			)
			assertNotContains(t, content, "Durable goal and scheduling contract:", "Completion authority is exclusive")
			if role.ID == workflowAgentFactoryID {
				assertContains(t, content,
					"Factory is the orchestrator-dispatched response to a confirmed specialist gap.",
					"let the orchestrator resume the original workflow unit",
					"never redispatch Factory or invoke another workflow unit",
					"sole writer for agent creation",
					"never modify a target project's files",
				)
				assertNotContains(t, content, "so it can dispatch Factory Agent")
			} else {
				assertContains(t, content,
					"return the missing capability to Coding Orchestrator Agent",
					"so it can dispatch Factory Agent",
					"resume only after the orchestrator returns the new definition",
				)
			}
			if role.CapabilityMode == CapabilityReadOnly {
				assertContains(t, content,
					"This workflow is read-only.",
					"neither you nor any delegate may modify files",
				)
			}
			if role.ID == workflowExecutorID {
				assertContains(t, content, "the only ordinary workflow unit that writes target-project code")
			}
		}
	}
}

func TestRenderCodeReviewWorkflowProjections(t *testing.T) {
	document := mustLoad(t)
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)

	for _, providerPath := range []string{
		"claude/anvil-wf-code-review.md",
		"codex/anvil-wf-code-review.toml",
		"antigravity/anvil-wf-code-review/agent.md",
	} {
		if _, exists := files[providerPath]; !exists {
			t.Errorf("Code Review projection %q is missing", providerPath)
		}
	}

	claude := string(files["claude/anvil-wf-code-review.md"])
	assertContains(t, claude,
		"name: anvil-wf-code-review\n",
		"tools: Agent, Skill, Read, Grep, Glob, Bash\n",
		"model: \"fable\"\n",
		"permissionMode: plan\n",
		"You are Code Review Agent, a peer assurance workflow unit",
		"dispatched by Coding Orchestrator Agent",
		"Workflow stages:\n",
		"Shared specialist pools:\n",
		"Run no more than 10 independent specialist delegates concurrently.",
		"logical fleet ceiling; any lower harness, provider, or runtime cap remains authoritative",
		"This workflow is read-only.",
		"Do not edit files, create commits, push branches, mutate pull requests, merge, deploy",
	)
	assertNotContains(t, claude, "Edit, Write")

	codex := string(files["codex/anvil-wf-code-review.toml"])
	assertContains(t, codex,
		"model = \"gpt-5.6-sol\"\n",
		"model_reasoning_effort = \"xhigh\"\n",
		"sandbox_mode = \"read-only\"\n",
		"You are Code Review Agent, a peer assurance workflow unit",
		"Shared specialist pools:",
		"no leaf specialist is mandatory by default",
	)
	assertNotContains(t, codex, "Preferred delegates", "workflow-deep-review", "workflow-release-readiness")

	antigravity := string(files["antigravity/anvil-wf-code-review/agent.md"])
	assertContains(t, antigravity,
		"name: anvil-wf-code-review\n",
		"  - invoke_subagent\n",
		"  - run_command\n",
		"mainAgent: true\n",
		"subagent: true\n",
		"model: \"gemini-3.1-pro-high\"\n",
		"commandExecutionPolicy: sandbox\n",
		"This workflow is read-only.",
	)
	assertNotContains(t, antigravity, "replace_file_content")
}


func TestRenderFrontmatterHasOnlyProviderNativeKeys(t *testing.T) {
	document := mustLoad(t)
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)

	claudeAllowed := map[string]bool{
		"name": true, "description": true, "tools": true, "model": true,
		"effort": true, "permissionMode": true, "mcpServers": true,
	}
	// Only roles that can write carry guard hooks.
	claudeOptional := map[string]bool{"hooks": true}
	antigravityAllowed := map[string]bool{
		"name": true, "description": true, "tools": true, "mainAgent": true,
		"subagent": true, "model": true, "commandExecutionPolicy": true,
	}
	for path, content := range files {
		switch {
		case strings.HasPrefix(path, "claude/"):
			assertFrontmatterKeys(t, path, content, claudeAllowed, claudeOptional)
		case strings.HasPrefix(path, "antigravity/"):
			keys := assertFrontmatterKeys(t, path, content, antigravityAllowed, nil)
			model := keys["model"]
			if model != "\"gemini-3.7-flash-high\"" && model != "\"gemini-3.1-pro-high\"" {
				t.Errorf("%s model = %s, want documented workhorse or powerhorse antigravity tier", path, model)
			}
		}
	}
}

func TestRenderEscapesNativeStrings(t *testing.T) {
	document := mustLoad(t)
	document.Roles[0].Summary = "Quotes \" and backslash \\ remain data"
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(rendered.CodexConfigBlock, []byte(`description = "Quotes \" and backslash \\ remain data"`)) {
		t.Fatalf("Codex declaration was not escaped: %s", rendered.CodexConfigBlock)
	}
	files := renderedMap(rendered)
	role := document.Roles[0]
	for _, providerPath := range []string{
		"claude/" + nativeAgentName(role) + ".md",
		"antigravity/" + nativeAgentName(role) + "/agent.md",
	} {
		if !bytes.Contains(files[providerPath], []byte(`description: "Quotes \" and backslash \\ remain data"`)) {
			t.Errorf("%s description was not escaped", providerPath)
		}
	}
}

func TestSyncRenderedWriteCheckAndDrift(t *testing.T) {
	document := mustLoad(t)
	root := t.TempDir()
	rendered, err := Render(root, document)
	if err != nil {
		t.Fatal(err)
	}
	if err := SyncRendered(root, rendered, false); err != nil {
		t.Fatalf("SyncRendered(write) error = %v", err)
	}
	if err := SyncRendered(root, rendered, true); err != nil {
		t.Fatalf("SyncRendered(check) error = %v", err)
	}
	target := filepath.Join(root, "harness-agents", "rendered", filepath.FromSlash(rendered.Files[0].Path))
	if err := os.WriteFile(target, []byte("drift\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := SyncRendered(root, rendered, true); err == nil || !strings.Contains(err.Error(), "changed") {
		t.Fatalf("drift check error = %v, want changed", err)
	}
	if err := SyncRendered(root, rendered, false); err != nil {
		t.Fatal(err)
	}
	stale := filepath.Join(root, "harness-agents", "rendered", "claude", "anvil-cf-stale.md")
	if err := os.WriteFile(stale, []byte("stale"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := SyncRendered(root, rendered, true); err == nil || !strings.Contains(err.Error(), "stale") {
		t.Fatalf("stale check error = %v, want stale", err)
	}
	if err := SyncRendered(root, rendered, false); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(stale); !os.IsNotExist(err) {
		t.Fatalf("stale generated file still exists, stat error = %v", err)
	}
}

func TestSyncRenderedRejectsSymlinkedManagedPaths(t *testing.T) {
	document := mustLoad(t)
	tests := []struct {
		name     string
		linkPath func(root string, rendered RenderResult) string
	}{
		{
			name: "provider directory",
			linkPath: func(root string, _ RenderResult) string {
				return filepath.Join(root, "harness-agents", "rendered", "claude")
			},
		},
		{
			name: "role directory",
			linkPath: func(root string, _ RenderResult) string {
				return filepath.Join(root, "harness-agents", "rendered", "antigravity", "anvil-cf-env-homelab")
			},
		},
		{
			name: "managed file",
			linkPath: func(root string, rendered RenderResult) string {
				return filepath.Join(root, "harness-agents", "rendered", filepath.FromSlash(rendered.Files[0].Path))
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root := t.TempDir()
			rendered, err := Render(root, document)
			if err != nil {
				t.Fatal(err)
			}
			if err := SyncRendered(root, rendered, false); err != nil {
				t.Fatal(err)
			}
			linkPath := test.linkPath(root, rendered)
			if err := os.RemoveAll(linkPath); err != nil {
				t.Fatal(err)
			}
			outside := filepath.Join(t.TempDir(), "outside")
			if err := os.MkdirAll(outside, 0o755); err != nil {
				t.Fatal(err)
			}
			if strings.HasSuffix(linkPath, ".md") || strings.HasSuffix(linkPath, ".toml") {
				outside = filepath.Join(outside, "agent")
				if err := os.WriteFile(outside, []byte("outside\n"), 0o644); err != nil {
					t.Fatal(err)
				}
			}
			if err := os.Symlink(outside, linkPath); err != nil {
				t.Fatal(err)
			}
			if err := SyncRendered(root, rendered, false); err == nil || !strings.Contains(err.Error(), "symlink") {
				t.Fatalf("SyncRendered() error = %v, want symlink refusal", err)
			}
		})
	}
}

func renderedMap(rendered RenderResult) map[string][]byte {
	files := make(map[string][]byte, len(rendered.Files))
	for _, file := range rendered.Files {
		files[file.Path] = file.Content
	}
	return files
}

func assertContains(t *testing.T, value string, fragments ...string) {
	t.Helper()
	for _, fragment := range fragments {
		if !strings.Contains(value, fragment) {
			t.Errorf("value does not contain %q:\n%s", fragment, value)
		}
	}
}

func assertNotContains(t *testing.T, value string, fragments ...string) {
	t.Helper()
	for _, fragment := range fragments {
		if strings.Contains(value, fragment) {
			t.Errorf("value unexpectedly contains %q:\n%s", fragment, value)
		}
	}
}

func assertFrontmatterKeys(t *testing.T, path string, content []byte, allowed, optional map[string]bool) map[string]string {
	t.Helper()
	lines := strings.Split(string(content), "\n")
	if len(lines) < 3 || lines[0] != "---" {
		t.Errorf("%s lacks opening frontmatter", path)
		return nil
	}
	keys := map[string]string{}
	for _, line := range lines[1:] {
		if line == "---" {
			break
		}
		if strings.HasPrefix(line, "  - ") {
			continue
		}
		key, value, ok := strings.Cut(line, ":")
		if !ok || (!allowed[key] && !optional[key]) {
			t.Errorf("%s has unsupported frontmatter line %q", path, line)
			continue
		}
		if _, duplicate := keys[key]; duplicate {
			t.Errorf("%s duplicates frontmatter key %q", path, key)
		}
		keys[key] = strings.TrimSpace(value)
	}
	for key := range allowed {
		if _, ok := keys[key]; !ok {
			t.Errorf("%s lacks frontmatter key %q", path, key)
		}
	}
	return keys
}

func TestRenderGivesEveryWritingRoleClaudeGuardHooks(t *testing.T) {
	document := mustLoad(t)
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)
	for _, role := range document.Roles {
		claude := string(files["claude/"+nativeAgentName(role)+".md"])
		writes := role.CapabilityMode == CapabilityWorkspaceWrite || role.CapabilityMode == CapabilityFactoryWrite
		hasHooks := strings.Contains(claude, "\nhooks: {")
		if writes != hasHooks {
			t.Errorf("%s writes=%v but frontmatter hooks=%v", role.ID, writes, hasHooks)
		}
		if writes {
			assertContains(t, claude,
				`"matcher":"Edit|Write|MultiEdit|NotebookEdit"`,
				`"matcher":"Bash"`,
				`"Stop":[{"hooks":[{"type":"command","command":"/home/anvil/.local/bin/anvil-guard hook --harness claude --event Stop"}]}]`,
				`"command":"/home/anvil/.local/bin/anvil-guard hook --harness claude --event PreToolUse"`,
				`"command":"/home/anvil/.local/bin/anvil-guard hook --harness claude --event PostToolUse"`,
			)
		}
		// Codex and Antigravity expose no per-agent hook surface; they rely on
		// the installer's global registrations.
		assertNotContains(t, string(files["codex/"+nativeAgentName(role)+".toml"]), "hook --harness")
		assertNotContains(t, string(files["antigravity/"+nativeAgentName(role)+"/agent.md"]), "hook --harness")
	}
}

func TestRenderCarriesOutputHygieneInEveryDefinition(t *testing.T) {
	document := mustLoad(t)
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), document)
	if err != nil {
		t.Fatal(err)
	}
	for _, file := range rendered.Files {
		if strings.HasPrefix(file.Path, "knowledge/") {
			continue
		}
		assertContains(t, string(file.Content),
			"Output hygiene:",
			"Read by line range whenever you already know the target",
			"Filter test, build, and lint output down to failures",
			"Never list a repository tree recursively into the context window.",
			"Return search results as `path:line` references",
		)
	}
}

func TestRenderCitesTheInstalledRunplaneSkillPath(t *testing.T) {
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), mustLoad(t))
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)
	installed := skillInstalledPath(canonicalHomeDirectory)
	for _, providerPath := range []string{
		"antigravity/anvil-coding-orchestrator/agent.md",
		"claude/anvil-coding-orchestrator.md",
		"codex/anvil-coding-orchestrator.toml",
	} {
		content := string(files[providerPath])
		if content == "" {
			t.Fatalf("%s was not rendered", providerPath)
		}
		assertContains(t, content, installed)
		// A repository-relative path is unreachable: the orchestrator runs with
		// the target project as its working directory.
		if strings.Contains(content, supervisorRunplaneSkillSource) {
			t.Fatalf("%s still cites the repository-relative skill path", providerPath)
		}
	}
}

func TestRenderKnowledgeProjections(t *testing.T) {
	rendered, err := Render(filepath.Join(string(filepath.Separator), "repo"), mustLoad(t))
	if err != nil {
		t.Fatal(err)
	}
	files := renderedMap(rendered)

	for _, repo := range []string{"biofeed", "ledger", "nexus", "swarm"} {
		path := "knowledge/" + repo + ".md"
		content := string(files[path])
		if content == "" {
			t.Fatalf("%s was not rendered", path)
		}
		assertContains(t, content, "<!-- Generated by go run ./cmd/codingfleet render; DO NOT EDIT. -->")
	}

	ledger := string(files["knowledge/ledger.md"])
	assertContains(t, ledger,
		"## Finance and Plaid",
		"Builds bounded personal-finance, transaction, account-linking, and reconciliation features.",
		"## Markets and IBKR",
		"Builds market-data, brokerage-import, research, and trading-analysis software.",
	)

	biofeed := string(files["knowledge/biofeed.md"])
	assertContains(t, biofeed,
		"## Health Telemetry",
		"Builds health-ingestion and biological telemetry features with cautious interpretation.",
	)

	nexus := string(files["knowledge/nexus.md"])
	assertContains(t, nexus,
		"## Nexus Operations",
		"Builds Nexus mission-control, Tasks board, fleet, approval, and operational data features.",
	)

	swarm := string(files["knowledge/swarm.md"])
	assertContains(t, swarm,
		"## Markets and IBKR",
		"Builds market-data, brokerage-import, research, and trading-analysis software.",
		"## Swarm Orchestration",
		"Builds Swarm agent definitions, workflow graphs, registry contracts, and guarded run-plane behavior.",
	)
}
