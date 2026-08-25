package codingfleet

import (
	"bytes"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"github.com/anvil008/swarm-coder/guard"
)

const (
	managedAgentPrefix          = "anvil-cf-"
	managedWorkflowPrefix       = "anvil-wf-"
	codingOrchestratorAgentName = "anvil-coding-orchestrator"
	// retiredDeepCodeAgentName remains managed only so render/install upgrades
	// can safely remove the former v2 entrypoint without touching other files.
	retiredDeepCodeAgentName = "anvil-deep-code"
)

// RenderConfig maps provider-neutral routing hints to provider-native model
// names. Callers may replace the defaults without changing the canonical role
// definitions.
type RenderConfig struct {
	CodexStandardModel       string
	CodexAdvancedModel       string
	ClaudeStandardModel      string
	ClaudeAdvancedModel      string
	AntigravityStandardModel string
	AntigravityAdvancedModel string
}

// DefaultRenderConfig returns the checked-in projection's model routing.
func DefaultRenderConfig() RenderConfig {
	return RenderConfig{
		CodexStandardModel:       "gpt-5.6-terra",
		CodexAdvancedModel:       "gpt-5.6-sol",
		ClaudeStandardModel:      "sonnet",
		ClaudeAdvancedModel:      "opus",
		AntigravityStandardModel: "flash",
		AntigravityAdvancedModel: "pro",
	}
}

// RenderedFile is one repository-relative native projection.
type RenderedFile struct {
	Path    string
	Content []byte
}

// RenderResult contains native role files plus the Codex declaration block.
// The latter is installed into ~/.codex/config.toml rather than checked in,
// because its config_file values must be absolute on the target machine.
type RenderResult struct {
	Files            []RenderedFile
	CodexConfigBlock []byte
}

// Render deterministically projects every role using the default model map.
// repositoryRoot must be absolute because Codex config_file paths are absolute.
func Render(repositoryRoot string, document Document) (RenderResult, error) {
	return RenderWithConfig(repositoryRoot, document, DefaultRenderConfig())
}

// RenderWithConfig deterministically projects every role using config.
func RenderWithConfig(repositoryRoot string, document Document, config RenderConfig) (RenderResult, error) {
	if !filepath.IsAbs(repositoryRoot) {
		return RenderResult{}, fmt.Errorf("repository root %q must be absolute", repositoryRoot)
	}
	if err := validateRenderConfig(config); err != nil {
		return RenderResult{}, err
	}
	if document.APIVersion != APIVersion || len(document.Roles) == 0 {
		return RenderResult{}, fmt.Errorf("catalog document must be loaded and non-empty")
	}

	root := filepath.Clean(repositoryRoot)
	result := RenderResult{Files: make([]RenderedFile, 0, len(document.Roles)*3)}
	nativeNames := make(map[string]string, len(document.Roles))
	for _, role := range document.Roles {
		authority, err := AuthorityForRole(document, role.ID)
		if err != nil {
			return RenderResult{}, err
		}
		name := nativeAgentName(role)
		if previous, exists := nativeNames[name]; exists {
			return RenderResult{}, fmt.Errorf("roles %q and %q map to duplicate native name %q", previous, role.ID, name)
		}
		nativeNames[name] = role.ID
		result.Files = append(result.Files,
			RenderedFile{
				Path:    filepath.ToSlash(filepath.Join("codex", name+".toml")),
				Content: renderCodexRole(role, authority, config),
			},
			RenderedFile{
				Path:    filepath.ToSlash(filepath.Join("claude", name+".md")),
				Content: renderClaudeRole(role, authority, config),
			},
			RenderedFile{
				Path:    filepath.ToSlash(filepath.Join("antigravity", name, "agent.md")),
				Content: renderAntigravityRole(role, authority, config),
			},
		)
	}
	knowledgeByRepo := make(map[string][]KnowledgeRole)
	for _, kr := range document.KnowledgeRoles {
		for _, repo := range kr.Repositories {
			knowledgeByRepo[repo] = append(knowledgeByRepo[repo], kr)
		}
	}
	repos := make([]string, 0, len(knowledgeByRepo))
	for repo := range knowledgeByRepo {
		repos = append(repos, repo)
	}
	sort.Strings(repos)
	for _, repo := range repos {
		roles := knowledgeByRepo[repo]
		sort.Slice(roles, func(i, j int) bool {
			return roles[i].ID < roles[j].ID
		})
		result.Files = append(result.Files, RenderedFile{
			Path:    filepath.ToSlash(filepath.Join("knowledge", repo+".md")),
			Content: renderKnowledgeRepository(repo, roles),
		})
	}
	sort.Slice(result.Files, func(left, right int) bool {
		return result.Files[left].Path < result.Files[right].Path
	})
	result.CodexConfigBlock = renderCodexDeclarations(root, document)
	return result, nil
}

func validateRenderConfig(config RenderConfig) error {
	models := map[string]string{
		"Codex standard":       config.CodexStandardModel,
		"Codex advanced":       config.CodexAdvancedModel,
		"Claude standard":      config.ClaudeStandardModel,
		"Claude advanced":      config.ClaudeAdvancedModel,
		"Antigravity standard": config.AntigravityStandardModel,
		"Antigravity advanced": config.AntigravityAdvancedModel,
	}
	for label, model := range models {
		if strings.TrimSpace(model) == "" || strings.ContainsAny(model, "\r\n\x00") {
			return fmt.Errorf("%s model must be a non-empty single-line value", label)
		}
	}
	return nil
}

func nativeAgentName(role Role) string {
	return nativeAgentNameForID(role.ID)
}

func nativeAgentNameForID(roleID string) string {
	if roleID == workflowCodingOrchestratorID {
		return codingOrchestratorAgentName
	}
	if strings.HasPrefix(roleID, "workflow-") {
		return managedWorkflowPrefix + strings.TrimPrefix(roleID, "workflow-")
	}
	return managedAgentPrefix + roleID
}

func isManagedAgentName(name string) bool {
	return name == codingOrchestratorAgentName || name == retiredDeepCodeAgentName || strings.HasPrefix(name, managedAgentPrefix) || strings.HasPrefix(name, managedWorkflowPrefix)
}

func renderCodexRole(role Role, authority AuthorityProfile, config RenderConfig) []byte {
	model := config.CodexStandardModel
	effort := "medium"
	sandboxMode := string(role.CapabilityMode)
	if role.RoutingTier == RoutingAdvanced {
		model = config.CodexAdvancedModel
		effort = "high"
	}
	if role.CapabilityMode == CapabilityFactoryWrite {
		sandboxMode = "danger-full-access"
	} else if role.CapabilityMode == CapabilityOrchestration {
		sandboxMode = "read-only"
	}

	var builder strings.Builder
	writeGeneratedHeader(&builder, "#")
	fmt.Fprintf(&builder, "model = %s\n", quoteString(model))
	fmt.Fprintf(&builder, "model_reasoning_effort = %s\n", quoteString(effort))
	fmt.Fprintf(&builder, "sandbox_mode = %s\n", quoteString(sandboxMode))
	fmt.Fprintf(&builder, "developer_instructions = %s\n", quoteString(agentPrompt(role, authority)))
	return []byte(builder.String())
}

func renderClaudeRole(role Role, authority AuthorityProfile, config RenderConfig) []byte {
	model := config.ClaudeStandardModel
	effort := "medium"
	tools := "Read, Grep, Glob"
	permissionMode := "plan"
	if role.RoutingTier == RoutingAdvanced {
		model = config.ClaudeAdvancedModel
		effort = "high"
	}
	if role.CapabilityMode == CapabilityWorkspaceWrite || role.CapabilityMode == CapabilityFactoryWrite {
		tools = "Read, Grep, Glob, Edit, Write, Bash"
		permissionMode = "default"
	}
	if role.Class == ClassWorkflow {
		tools = "Agent, Skill, Read, Grep, Glob"
		if role.CapabilityMode == CapabilityReadOnly {
			tools += ", Bash"
		}
		if role.CapabilityMode == CapabilityWorkspaceWrite || role.CapabilityMode == CapabilityFactoryWrite {
			tools += ", Edit, Write, Bash"
		}
	}
	if role.CapabilityMode == CapabilityFactoryWrite {
		permissionMode = "bypassPermissions"
	}
	hooks := ""
	if role.CapabilityMode == CapabilityWorkspaceWrite || role.CapabilityMode == CapabilityFactoryWrite {
		hooks = claudeGuardHooksFrontmatter()
	}
	mcpServers := "[]"
	if role.ID == workflowCodingOrchestratorID {
		tools += ", " + supervisorClaudeMCPToolName
		mcpServers = `[{"` + supervisorMCPServerName + `":{"type":"stdio","command":"` + supervisorRunplaneBinary + `","args":["mcp"]}}]`
	}

	var builder strings.Builder
	builder.WriteString("---\n")
	fmt.Fprintf(&builder, "name: %s\n", nativeAgentName(role))
	fmt.Fprintf(&builder, "description: %s\n", quoteString(role.Summary))
	fmt.Fprintf(&builder, "tools: %s\n", tools)
	fmt.Fprintf(&builder, "mcpServers: %s\n", mcpServers)
	fmt.Fprintf(&builder, "model: %s\n", quoteString(model))
	fmt.Fprintf(&builder, "effort: %s\n", effort)
	fmt.Fprintf(&builder, "permissionMode: %s\n", permissionMode)
	if hooks != "" {
		fmt.Fprintf(&builder, "hooks: %s\n", hooks)
	}
	builder.WriteString("---\n\n")
	builder.WriteString(agentPrompt(role, authority))
	builder.WriteByte('\n')
	return []byte(builder.String())
}

func renderAntigravityRole(role Role, authority AuthorityProfile, config RenderConfig) []byte {
	model := config.AntigravityStandardModel
	tools := []string{"view_file", "grep_search"}
	commandPolicy := "off"
	if role.RoutingTier == RoutingAdvanced {
		model = config.AntigravityAdvancedModel
	}
	switch role.CapabilityMode {
	case CapabilityWorkspaceWrite:
		tools = append(tools, "replace_file_content", "run_command")
		commandPolicy = "sandbox"
	case CapabilityFactoryWrite:
		tools = append(tools, "replace_file_content", "run_command")
		// Antigravity custom agents use off/auto/eager/sandbox here; the
		// application-level always-proceed preset is a different schema. Auto
		// keeps ordinary validation commands moving while retaining approval
		// gates for high-risk operations.
		commandPolicy = "auto"
	}
	if role.Class == ClassWorkflow {
		tools = append([]string{"invoke_subagent"}, tools...)
		if role.CapabilityMode == CapabilityReadOnly {
			tools = append(tools, "run_command")
			commandPolicy = "sandbox"
		}
	}
	if role.ID == workflowCodingOrchestratorID {
		tools = append(tools, supervisorMCPToolName)
	}

	var builder strings.Builder
	builder.WriteString("---\n")
	fmt.Fprintf(&builder, "name: %s\n", nativeAgentName(role))
	fmt.Fprintf(&builder, "description: %s\n", quoteString(role.Summary))
	builder.WriteString("tools:\n")
	for _, tool := range tools {
		fmt.Fprintf(&builder, "  - %s\n", tool)
	}
	// Supervised cross-provider runs invoke any canonical role as the foreign
	// harness's main headless session. Keep every role subagent-selectable too so
	// same-harness delegation continues to use the native mechanism.
	builder.WriteString("mainAgent: true\n")
	builder.WriteString("subagent: true\n")
	fmt.Fprintf(&builder, "model: %s\n", quoteString(model))
	fmt.Fprintf(&builder, "commandExecutionPolicy: %s\n", commandPolicy)
	builder.WriteString("---\n\n")
	builder.WriteString(agentPrompt(role, authority))
	builder.WriteByte('\n')
	return []byte(builder.String())
}

func renderKnowledgeRepository(repo string, roles []KnowledgeRole) []byte {
	var builder strings.Builder
	builder.WriteString("<!-- Generated by go run ./cmd/codingfleet render; DO NOT EDIT. -->\n\n")
	for index, role := range roles {
		if index > 0 {
			builder.WriteString("\n")
		}
		fmt.Fprintf(&builder, "## %s\n\n", role.Name)
		fmt.Fprintf(&builder, "%s\n\n", role.Summary)
		fmt.Fprintf(&builder, "%s\n\n", role.Instructions)
		builder.WriteString("### Boundaries\n\n")
		for _, boundary := range role.Boundaries {
			fmt.Fprintf(&builder, "- %s\n", boundary)
		}
	}
	return []byte(builder.String())
}

func renderCodexDeclarations(repositoryRoot string, document Document) []byte {
	var builder strings.Builder
	builder.WriteString(codexBeginMarker)
	builder.WriteByte('\n')
	for index, role := range document.Roles {
		if index > 0 {
			builder.WriteByte('\n')
		}
		name := nativeAgentName(role)
		configPath := filepath.Join(repositoryRoot, "harness-agents", "rendered", "codex", name+".toml")
		fmt.Fprintf(&builder, "[agents.%s]\n", name)
		fmt.Fprintf(&builder, "description = %s\n", quoteString(role.Summary))
		fmt.Fprintf(&builder, "config_file = %s\n", quoteString(configPath))
	}
	builder.WriteByte('\n')
	builder.WriteString(codexEndMarker)
	builder.WriteByte('\n')
	return []byte(builder.String())
}

func agentPrompt(role Role, authority AuthorityProfile) string {
	var builder strings.Builder
	if role.Class == ClassWorkflow {
		if role.ID == workflowCodingOrchestratorID {
			builder.WriteString("You are Coding Orchestrator Agent, the single coding entrypoint, durable goal owner, integration owner, and overall completion authority for the Anvil Coding Fleet.\n\n")
		} else {
			fmt.Fprintf(&builder, "You are %s, a peer %s workflow unit beneath Coding Orchestrator Agent in the Anvil Coding Fleet.\n\n", role.Name, role.Workflow.Lane)
		}
	} else {
		fmt.Fprintf(&builder, "You are the %s specialist in the Anvil Coding Fleet.\n\n", role.Name)
	}
	builder.WriteString(role.Instructions)
	builder.WriteString("\n\nRole boundary:\n")
	fmt.Fprintf(&builder, "- Canonical role: `%s` (%s/%s). Stay within this role and the parent assignment; a child never broadens either.\n", authority.ID, authority.RoleClass, authority.CapabilityMode)
	fmt.Fprintf(&builder, "- Tools allowed: %s. Tools denied: %s. Filesystem read: %s. Filesystem write: %s.\n", renderStringSet(authority.Grant.ToolAllow), renderStringSet(authority.Grant.ToolDeny), renderStringSet(authority.Grant.FilesystemRead), renderStringSet(authority.Grant.FilesystemWrite))
	fmt.Fprintf(&builder, "- Invocable role kinds: %s. Invocable role IDs: %s. Unavailable or ambiguous model routes reject without substitution.\n", renderStringSet(authority.Grant.InvocableRoleKinds), renderStringSet(authority.Grant.InvocableRoleIDs))
	if role.Workflow != nil {
		builder.WriteString("\n\nOrchestration contract:\n")
		fmt.Fprintf(&builder, "- Lane: %s.\n", role.Workflow.Lane)
		if role.ID == workflowCodingOrchestratorID {
			builder.WriteString("- Invocation: the only default entrypoint for coding tasks and the sole owner of cross-unit integration and overall completion.\n")
			builder.WriteString("- Execution boundary: orchestrate only. Do not directly inspect, edit, test, or implement target-project code; dispatch that work to the appropriate workflow unit and reconcile its evidence.\n")
		} else {
			builder.WriteString("- Invocation: dispatched by Coding Orchestrator Agent for one explicit lane assignment. Return evidence and control to the orchestrator; do not invoke another workflow unit or claim overall completion.\n")
		}
		builder.WriteString("\nDelegation boundary:\n")
		fmt.Fprintf(&builder, "- Available specialist role classes: %s. Availability does not require delegation.\n", renderRoleClassSet(role.Workflow.ProposableRoleClasses))
		fmt.Fprintf(&builder, "- Invocable role IDs: %s. Invocable specialist pools: %s.\n", renderStringSet(role.Workflow.InvocableRoleIDs), renderSpecialistPoolSet(role.Workflow.InvocableSpecialistPools))
		if role.ID == workflowCodingOrchestratorID {
			builder.WriteString("- Select exactly one justified workflow unit per assignment. The selected workflow may retain, add, or remove proposed technical/domain lenses and owns every leaf invocation. Direct orchestrator-to-specialist invocation is forbidden.\n")
		} else {
			builder.WriteString("- You own refinement and leaf invocation for this workflow assignment. Record retain/add/remove reasons and evidence. Selecting zero leaves is valid when a reason is recorded. Never invoke another workflow unit.\n")
		}
		if role.Workflow.Orchestration != nil {
			orchestration := role.Workflow.Orchestration
			builder.WriteString("\nDurable goal and scheduling contract:\n")
			fmt.Fprintf(&builder, "- Goal mode: %s. Bind the objective, constraints, acceptance and verification criteria, granted authority, and stop conditions to the durable goal directory, and mirror them into the harness's native goal, session, thread, or resume state.\n", orchestration.GoalMode)
			fmt.Fprintf(&builder, "- Checkpoint policy: %s. Persist `checkpoint.json` plus a short `plan.md` under `%s` at phase transitions, delegate handoffs, context compaction, interruptions, and before yielding, recording the objective, constraints, decisions, completed evidence, runnable and blocked queues, active delegate identities and file ownership, and the exact next action.\n", orchestration.CheckpointPolicy, checkpointGoalDirectory)
			fmt.Fprintf(&builder, "- Persist and re-read those files only through the `goal` verb of `%s` (`{\"operation\":\"goal\",\"goal\":{\"goalId\":…,\"action\":\"checkpoint\"|\"show\",…}}`) or `%s goal checkpoint|show`, never through a file tool: this role holds no filesystem write authority. The verb runs against local state, so it needs no running service.\n", supervisorMCPToolName, supervisorRunplaneBinary)
			builder.WriteString("- Those files are the system of record and native session state is only a cache of them. Re-read them on every resume and reconcile them with current repository and external state before releasing more work; stale delegate claims never outrank observed state.\n")
			fmt.Fprintf(&builder, "- Scheduling policy: %s. Maintain a dependency-ready queue and proactively fill available capacity with materially independent work up to %d concurrent delegates. This is a logical fleet ceiling, not a promise that the active harness or provider exposes that many slots; obey any lower hard runtime cap, keep excess work queued, and record the residual constraint in checkpoints. Prefer parallel read-heavy investigation and disjoint file ownership; serialize overlapping writes unless the harness provides isolated worktrees. Do not fan out work that lacks a real latency or assurance benefit.\n", orchestration.SchedulingPolicy, role.Workflow.MaxParallel)
			if orchestration.ProactiveDelegation {
				builder.WriteString("- Proactive delegation is enabled: select and start justified workflow units without waiting for a separate user request, while keeping one explicit integration owner.\n")
			}
			if orchestration.CompletionAuthority {
				builder.WriteString("- Completion authority is exclusive to Coding Orchestrator Agent. Continue until the current goal is verified complete, genuinely blocked, requires new authority, or the user pauses or changes it; workflow units and specialists only return evidence and control.\n")
			}
			if orchestration.ModelRouting != nil {
				builder.WriteString("\nUser-directed model routing contract:\n")
				builder.WriteString("- Parse natural-language model routes before scheduling. A route may apply to the whole goal (for example, `use Terra Max for all subagents`) or to a lane or role (for example, `use Gemini 3.7 Flash for execution and Opus for planning`). Preserve the resolved route in checkpoints and apply it to every matching subsequent dispatch.\n")
				builder.WriteString("- An explicit user route overrides fleet defaults. Resolve provider, family, model, and effort aliases only against capabilities that the current harness or supervisor has discovered and allowlisted. Fail closed on ambiguous, conflicting, or unavailable requests; report the unresolved route and do not silently substitute another model, family, provider, or effort.\n")
				fmt.Fprintf(&builder, "- Native-first dispatch policy: `%s`. When the requested model belongs to the current harness provider, always use that harness's native subagent mechanism with explicit model and effort overrides. Agy/Antigravity uses native Gemini agents, Claude uses native Anthropic agents, and Codex uses native OpenAI agents. Do not use the shared launcher for same-provider work.\n", orchestration.ModelRouting.SameProviderDispatch)
				runplane := orchestration.ModelRouting.SupervisorRunplane
				fmt.Fprintf(&builder, "- Foreign-provider dispatch policy: `%s`. Use the installed shared launcher only when the requested provider differs from the current harness provider. Start the exact matching canonical workflow or specialist definition as the foreign harness's main headless session, plus only a bounded task brief. Never replace the role contract with a generic prompt or start another Coding Orchestrator Agent.\n", orchestration.ModelRouting.CrossProviderDispatch)
				fmt.Fprintf(&builder, "- Capability policy: `%s`. Before foreign dispatch, run `%s health` and then `%s capabilities`; the exact canonical role and requested provider, family, model, and effort capability must all be present. Fail closed when any exact capability is absent.\n", runplane.CapabilityPolicy, runplane.Binary, runplane.Binary)
				fmt.Fprintf(&builder, "- The bounded role and task brief always travels in the `%s start --request route.json` request file (`%s`); follow-up and resumed input always travel on stdin, never argv.\n", runplane.Binary, runplane.BriefTransport)
				fmt.Fprintf(&builder, "- The rest of the run-plane lifecycle, service bootstrap, start-document schema, and environment overrides live in the installed document `%s`. Read that absolute path only when a foreign dispatch is actually required; do not carry it in ordinary turns.\n", runplane.SkillDocument)
				builder.WriteString("- This parent Coding Orchestrator retains monitor, resume, message, cancel, evidence reconciliation, integration, and completion authority for every foreign run. A foreign harness session is a worker execution context, not a new owner.\n")
				fmt.Fprintf(&builder, "- Common handoff boundary: `%s`. Native and foreign children return only runId, parentRunId, canonicalRole (the canonical catalog role ID), provider, model, effort, mode, ownedFiles, limits, changedFiles, tests, result, and disposition. Harness-native session and process state stay inside the owning harness.\n", orchestration.ModelRouting.HandoffBoundary)
			}
		}
		builder.WriteString("\n\nWorkflow stages:\n")
		for index, stage := range role.Workflow.Stages {
			fmt.Fprintf(&builder, "%d. %s\n", index+1, stage)
		}
		if len(role.Workflow.SpecialistPools) > 0 {
			builder.WriteString("\nShared specialist pools:\n")
			builder.WriteString("- Technical pool (`anvil-cf-technical-*`): implementation-stack, architecture, security, testing, performance, data, UI, infrastructure, and provider specialists.\n")
			builder.WriteString("- Domain pool (`anvil-cf-domain-*`): product and operational-context specialists.\n")
			builder.WriteString("- Select from either pool only when explicit task, repository, risk, or failure evidence justifies it. Pool access is available throughout this workflow lane; no leaf specialist is mandatory by default.\n")
			if role.Workflow.CreatesSpecialists {
				builder.WriteString("- Factory is the orchestrator-dispatched response to a confirmed specialist gap. Create only the missing leaf, return its definition to Coding Orchestrator Agent, and let the orchestrator resume the original workflow unit; never redispatch Factory or invoke another workflow unit.\n")
			} else {
				builder.WriteString("- If no existing specialist is sufficiently specific, return the missing capability to Coding Orchestrator Agent so it can dispatch Factory Agent; resume only after the orchestrator returns the new definition.\n")
			}
		}
		if len(role.Workflow.Delegates) > 0 {
			builder.WriteString("\nWorkflow units (complete peer layer):\n")
			for _, delegate := range role.Workflow.Delegates {
				fmt.Fprintf(&builder, "- %s\n", nativeAgentNameForID(delegate))
			}
			builder.WriteString("- Dispatch specialists only through one of these workflow units; the orchestrator does not bypass the workflow layer.\n")
		}
		if role.Workflow.CreatesSpecialists {
			builder.WriteString("\nYou are the sole writer for agent creation. Specialist delegates may gather or review evidence, but you directly mutate the canonical Swarm Coder catalog, render every native projection, and run the managed global installer.\n")
		}
		if role.Workflow.Orchestration != nil && role.Workflow.Orchestration.ProactiveDelegation {
			fmt.Fprintf(&builder, "\nProactively use up to %d independent workflow units when the dependency queue and ownership boundaries make parallel work useful. Preserve explicit ownership and integrate every result in this parent context.\n", role.Workflow.MaxParallel)
		} else {
			fmt.Fprintf(&builder, "\nRun no more than %d independent specialist delegates concurrently. This is a logical fleet ceiling; any lower harness, provider, or runtime cap remains authoritative, with excess work kept queued. Preserve explicit ownership and integrate their evidence before returning.\n", role.Workflow.MaxParallel)
		}
		builder.WriteString("Every child returns one small `anvil.agent-handoff/v1` record containing runId, parentRunId, canonicalRole (the canonical catalog role ID), provider, model, effort, mode, ownedFiles, limits, changedFiles, tests, result, and disposition. Exit zero or narrative success alone is not completion; missing current test evidence is uncertain or failed.\n")
		if role.ID == workflowCodingOrchestratorID {
			builder.WriteString("For implementation outcomes, run the bounded independent verification policy internally: one independent verification pass, at most one focused repair, and at most one re-verification (two total verification passes). Stop early on acceptance, cancellation, blockage, exhaustion, or no material change. Emit one final answer or patch only; never call or consume benchmark scorers, gold patches, hidden tests, prior-run history, or issue-web solutions.\n")
		}
		if role.CapabilityMode == CapabilityReadOnly {
			builder.WriteString("This workflow is read-only. You may run inspection and verification commands, but neither you nor any delegate may modify files. A delegate's broader default capability does not expand this workflow's authority.\n")
		} else if role.CapabilityMode == CapabilityOrchestration {
			builder.WriteString("This agent is orchestration-only. It may manage goal state, dispatch workflow units, and integrate their evidence, but it may not perform target-project research, mutation, testing, or specialist work itself.\n")
		}
	}
	builder.WriteString("\n\nOutput hygiene:\n")
	builder.WriteString("- Read by line range whenever you already know the target; do not read a whole file to reach one symbol.\n")
	builder.WriteString("- Filter test, build, and lint output down to failures and the lines that explain them.\n")
	builder.WriteString("- Never list a repository tree recursively into the context window.\n")
	builder.WriteString("- Return search results as `path:line` references rather than surrounding blocks.\n")
	builder.WriteString("\nBoundaries:\n")
	for _, boundary := range role.Boundaries {
		fmt.Fprintf(&builder, "- %s\n", boundary)
	}
	if role.Class == ClassWorkflow {
		builder.WriteString("\nThis is native-harness workflow guidance, not an executable ADK graph. Enforce stage gates from observed evidence and never claim delegated work is complete before validating the returned evidence and current state.")
	} else {
		builder.WriteString("\nThis is a specialist definition, not an ADK workflow graph or proof of a running adapter. Work only within the task delegated by the parent harness.")
	}
	return builder.String()
}

// claudeGuardHooksFrontmatter renders the per-agent registrations Claude Code
// reads from subagent frontmatter. Codex and Antigravity expose no per-agent
// hook surface and rely on the installer's global registrations instead.
func claudeGuardHooksFrontmatter() string {
	command := func(event string) string {
		return guardCommandPath + " hook --harness claude --event " + event
	}
	matched := func(event, matcher string) string {
		return `{"matcher":"` + matcher + `","hooks":[{"type":"command","command":"` + command(event) + `"}]}`
	}
	return `{"PreToolUse":[` + matched("PreToolUse", guard.EditToolMatchers[guard.HarnessClaude]) +
		`],"PostToolUse":[` + matched("PostToolUse", guard.ShellToolMatchers[guard.HarnessClaude]) +
		`],"Stop":[{"hooks":[{"type":"command","command":"` + command("Stop") + `"}]}]}`
}

func renderStringSet(values []string) string {
	if len(values) == 0 {
		return "none"
	}
	return "`" + strings.Join(values, "`, `") + "`"
}

func renderRoleClassSet(values []RoleClass) string {
	converted := make([]string, len(values))
	for index, value := range values {
		converted[index] = string(value)
	}
	return renderStringSet(converted)
}

func renderSpecialistPoolSet(values []SpecialistPool) string {
	converted := make([]string, len(values))
	for index, value := range values {
		converted[index] = string(value)
	}
	return renderStringSet(converted)
}

func writeGeneratedHeader(builder *strings.Builder, comment string) {
	fmt.Fprintf(builder, "%s Generated by go run ./cmd/codingfleet render; DO NOT EDIT.\n", comment)
}

func quoteString(value string) string {
	return strconv.Quote(value)
}

// SyncRendered writes result into the repository-owned generated tree. In
// check mode it makes no changes and reports any missing, changed, or stale
// managed output.
func SyncRendered(repositoryRoot string, result RenderResult, check bool) error {
	if !filepath.IsAbs(repositoryRoot) {
		return fmt.Errorf("repository root %q must be absolute", repositoryRoot)
	}
	outputRoot := filepath.Join(filepath.Clean(repositoryRoot), "harness-agents", "rendered")
	if err := rejectSymlinkComponents(filepath.Clean(repositoryRoot), outputRoot); err != nil {
		return fmt.Errorf("validate rendered output root: %w", err)
	}
	expected := make(map[string][]byte, len(result.Files))
	for _, file := range result.Files {
		clean, err := validateRenderedPath(file.Path)
		if err != nil {
			return err
		}
		if _, duplicate := expected[clean]; duplicate {
			return fmt.Errorf("duplicate rendered path %q", clean)
		}
		expected[clean] = file.Content
	}
	for _, provider := range []string{"antigravity", "claude", "codex", "knowledge"} {
		if err := rejectSymlinkComponents(outputRoot, filepath.Join(outputRoot, provider)); err != nil {
			return fmt.Errorf("validate rendered %s tree: %w", provider, err)
		}
	}

	drift := make([]string, 0)
	for relative, content := range expected {
		target := filepath.Join(outputRoot, filepath.FromSlash(relative))
		if err := rejectSymlinkComponents(outputRoot, filepath.Dir(target)); err != nil {
			return fmt.Errorf("validate rendered file %s: %w", relative, err)
		}
		if err := rejectSymlinkFile(target); err != nil {
			return fmt.Errorf("validate rendered file %s: %w", relative, err)
		}
		current, err := os.ReadFile(target)
		switch {
		case err == nil && bytes.Equal(current, content):
			continue
		case err == nil:
			drift = append(drift, "changed "+relative)
		case errors.Is(err, fs.ErrNotExist):
			drift = append(drift, "missing "+relative)
		default:
			return fmt.Errorf("read rendered file %s: %w", relative, err)
		}
	}

	stale, err := staleRenderedPaths(outputRoot, expected)
	if err != nil {
		return err
	}
	for _, relative := range stale {
		drift = append(drift, "stale "+relative)
	}
	sort.Strings(drift)
	if check {
		if len(drift) > 0 {
			return fmt.Errorf("rendered coding fleet is out of date: %s", strings.Join(drift, ", "))
		}
		return nil
	}

	for relative, content := range expected {
		target := filepath.Join(outputRoot, filepath.FromSlash(relative))
		if err := rejectSymlinkComponents(outputRoot, filepath.Dir(target)); err != nil {
			return fmt.Errorf("validate rendered file %s: %w", relative, err)
		}
		if err := rejectSymlinkFile(target); err != nil {
			return fmt.Errorf("validate rendered file %s: %w", relative, err)
		}
		if current, err := os.ReadFile(target); err == nil && bytes.Equal(current, content) {
			continue
		} else if err != nil && !errors.Is(err, fs.ErrNotExist) {
			return fmt.Errorf("read rendered file %s: %w", relative, err)
		}
		if err := writeFileAtomic(target, content, 0o644); err != nil {
			return fmt.Errorf("write rendered file %s: %w", relative, err)
		}
	}
	for _, relative := range stale {
		if err := removeStaleRendered(outputRoot, relative); err != nil {
			return err
		}
	}
	return nil
}

// rejectSymlinkComponents ensures every existing component below base is a
// real directory, preventing generated output from escaping through a
// replaced provider or role directory.
func rejectSymlinkComponents(base, target string) error {
	base = filepath.Clean(base)
	target = filepath.Clean(target)
	baseInfo, baseErr := os.Lstat(base)
	if baseErr == nil {
		if baseInfo.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("trusted root %s is a symlink", base)
		}
		if !baseInfo.IsDir() {
			return fmt.Errorf("trusted root %s is not a directory", base)
		}
	} else if !errors.Is(baseErr, fs.ErrNotExist) {
		return fmt.Errorf("inspect trusted root %s: %w", base, baseErr)
	}
	relative, err := filepath.Rel(base, target)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return fmt.Errorf("path %s is outside trusted root %s", target, base)
	}
	if relative == "." {
		return nil
	}
	current := base
	for _, part := range strings.Split(relative, string(filepath.Separator)) {
		current = filepath.Join(current, part)
		info, statErr := os.Lstat(current)
		if errors.Is(statErr, fs.ErrNotExist) {
			return nil
		}
		if statErr != nil {
			return fmt.Errorf("inspect %s: %w", current, statErr)
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("path component %s is a symlink", current)
		}
		if !info.IsDir() {
			return fmt.Errorf("path component %s is not a directory", current)
		}
	}
	return nil
}

func rejectSymlinkFile(pathname string) error {
	info, err := os.Lstat(pathname)
	if errors.Is(err, fs.ErrNotExist) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("inspect %s: %w", pathname, err)
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("managed output %s is a symlink", pathname)
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("managed output %s is not a regular file", pathname)
	}
	return nil
}

func validateRenderedPath(relative string) (string, error) {
	clean := filepath.ToSlash(filepath.Clean(filepath.FromSlash(relative)))
	if clean == "." || clean != relative || strings.HasPrefix(clean, "../") || filepath.IsAbs(relative) {
		return "", fmt.Errorf("rendered path %q must be a clean relative path", relative)
	}
	parts := strings.Split(clean, "/")
	if len(parts) < 2 {
		return "", fmt.Errorf("rendered path %q has unsupported provider", relative)
	}
	switch parts[0] {
	case "codex", "claude", "antigravity":
	case "knowledge":
		if len(parts) != 2 || !strings.HasSuffix(parts[1], ".md") {
			return "", fmt.Errorf("rendered path %q has unsupported provider", relative)
		}
	default:
		return "", fmt.Errorf("rendered path %q has unsupported provider", relative)
	}
	return clean, nil
}

func staleRenderedPaths(outputRoot string, expected map[string][]byte) ([]string, error) {
	stale := make([]string, 0)
	for _, provider := range []string{"antigravity", "claude", "codex", "knowledge"} {
		providerRoot := filepath.Join(outputRoot, provider)
		walkErr := filepath.WalkDir(providerRoot, func(current string, entry fs.DirEntry, err error) error {
			if errors.Is(err, fs.ErrNotExist) {
				return fs.SkipDir
			}
			if err != nil {
				return err
			}
			if current == providerRoot || entry.IsDir() {
				return nil
			}
			relative, err := filepath.Rel(outputRoot, current)
			if err != nil {
				return err
			}
			relative = filepath.ToSlash(relative)
			if !isManagedRenderedPath(relative) {
				return fmt.Errorf("unexpected unowned file in generated tree: %s", relative)
			}
			if _, ok := expected[relative]; !ok {
				stale = append(stale, relative)
			}
			return nil
		})
		if walkErr != nil && !errors.Is(walkErr, fs.ErrNotExist) {
			return nil, fmt.Errorf("inspect rendered %s tree: %w", provider, walkErr)
		}
	}
	sort.Strings(stale)
	return stale, nil
}

func isManagedRenderedPath(relative string) bool {
	parts := strings.Split(filepath.ToSlash(relative), "/")
	switch {
	case len(parts) == 2 && parts[0] == "codex":
		return strings.HasSuffix(parts[1], ".toml") && isManagedAgentName(strings.TrimSuffix(parts[1], ".toml"))
	case len(parts) == 2 && parts[0] == "claude":
		return strings.HasSuffix(parts[1], ".md") && isManagedAgentName(strings.TrimSuffix(parts[1], ".md"))
	case len(parts) == 3 && parts[0] == "antigravity":
		return isManagedAgentName(parts[1]) && parts[2] == "agent.md"
	case len(parts) == 2 && parts[0] == "knowledge":
		return strings.HasSuffix(parts[1], ".md")
	default:
		return false
	}
}

func removeStaleRendered(outputRoot, relative string) error {
	target := filepath.Join(outputRoot, filepath.FromSlash(relative))
	info, err := os.Lstat(target)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil
		}
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return fmt.Errorf("refuse to remove non-regular stale output %s", relative)
	}
	if err := os.Remove(target); err != nil {
		return fmt.Errorf("remove stale output %s: %w", relative, err)
	}
	parent := filepath.Dir(target)
	for parent != outputRoot {
		if err := os.Remove(parent); err != nil {
			if errors.Is(err, fs.ErrNotExist) || strings.Contains(err.Error(), "directory not empty") {
				break
			}
			break
		}
		parent = filepath.Dir(parent)
	}
	return nil
}

func writeFileAtomic(target string, content []byte, mode fs.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return err
	}
	info, err := os.Lstat(target)
	if err == nil && !info.Mode().IsRegular() {
		return fmt.Errorf("target is not a regular file")
	}
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	temporary, err := os.CreateTemp(filepath.Dir(target), ".coding-fleet-*")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	cleanup := func() {
		_ = temporary.Close()
		_ = os.Remove(temporaryPath)
	}
	if err := temporary.Chmod(mode); err != nil {
		cleanup()
		return err
	}
	if _, err := temporary.Write(content); err != nil {
		cleanup()
		return err
	}
	if err := temporary.Sync(); err != nil {
		cleanup()
		return err
	}
	if err := temporary.Close(); err != nil {
		_ = os.Remove(temporaryPath)
		return err
	}
	if err := os.Rename(temporaryPath, target); err != nil {
		_ = os.Remove(temporaryPath)
		return err
	}
	return nil
}
