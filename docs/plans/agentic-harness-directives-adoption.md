# Adopting the agentic-harness directives in the Coding Fleet

Source: `agentic-harness-directives.md`. Baseline: catalog `2026.08.24.2`
(52 roles), commit `51c4950`. Decisions taken 2026-08-25: collapse specialists
(D1, mapping in §4), test seal is a digest baseline with no new commit
authority (D2), evaluation stays on LXC 135 / SWE-bench and is out of scope
here (D3). Every change ships to all three harnesses: Claude Code, Codex,
Antigravity.

## 1. Gap summary (Section 6 anti-patterns present)

| # | Anti-pattern | Where |
|---|---|---|
| G1 | Persona-only subagents | 44 specialists, same model/tools, 1–2 sentence instructions |
| G2 | Handoff chains on coupled work | orchestrator (`filesystemRead: none`) → executor → specialist waves |
| G3 | Self-reported test booleans | `AgentHandoffTest{Name, Passed}` not tied to `CommandEvidence` |
| G4 | Review stages need not execute | Code Review / Evaluator may pass with zero commands run |
| G5 | No mechanical test guard | only hook installed is herdr `SessionStart` |
| G6 | Exploration returns prose | Research has no pointer schema or breadth cap |
| G7 | Window as system of record | checkpoint fallback "preserve in the conversation" |
| G8 | Mandatory front door / heavy plan pipeline | every task → orchestrator; ~50 KB HTML plans |
| G9 | Prompt bloat | runplane CLI reference in every orchestrator turn |
| G10 | No AST rewrite / structural search | `ast-grep`, linters absent |

Already aligned and kept: `CommandEvidence` (argv/stdout digests, exit code),
bounded verification budget (2 passes / 1 repair), plans pinned to commit +
sha256, worktree-aware ownership, dispatch-per-unit context resets, fail-closed
routing, orchestrator forbidden from consuming scorers or hidden tests.

## 2. Harness hook facts (verified 2026-08-25)

| | Claude Code 2.1.241 | Codex 0.149.1 | Antigravity CLI 1.1.20 |
|---|---|---|---|
| Config | subagent frontmatter `hooks:` (Pre/PostToolUse, Stop→SubagentStop; ignored under `--agents`), `~/.claude/settings.json` `hooks` | `~/.codex/hooks.json` `{"hooks":{Event:[{matcher,hooks:[…]}]}}` or `[hooks]` in config.toml | `~/.gemini/config/hooks.json` `{"<handler>":{enabled,PreToolUse:[…],PostToolUse:[…],Stop:[…]}}` |
| Events | PreToolUse, PostToolUse, Stop, SubagentStop | PreToolUse, PostToolUse, Stop, SubagentStop | PreToolUse, PostToolUse, PreInvocation, PostInvocation, Stop |
| Edit tools | `Edit\|Write\|MultiEdit\|NotebookEdit` | `apply_patch` | `write_to_file\|replace_file_content\|multi_replace_file_content` |
| Shell tools | `Bash` | `Bash` (`exec_command` matches as Bash) | `run_command` |
| stdin | `hook_event_name, tool_name, tool_input.file_path, cwd, agent_type` | `hook_event_name, tool_name, tool_input, cwd, turn_id` | `toolCall.name, toolCall.args, workspacePaths, conversationId`; Stop: `terminationReason, fullyIdle` |
| Block | PreToolUse exit 2 / `permissionDecision: deny`; PostToolUse cannot block (exit 2 = message); Stop/SubagentStop exit 2 = keep going | exit 2 + stderr, or `decision: "block"` + `reason`; Stop `continue:false` | `{"decision":"deny","reason"}`; Stop `{"decision":"continue"}` re-enters loop |
| Trust | folder trust (`~/.claude/agents/` ok) | per-hook hash trust, recorded in `[hooks.state]`; hash format not reproducible → one-time `/hooks` approval | none documented |
| Foreign runs | runplane passes `--setting-sources user` → settings hooks apply | profile runs load user hooks | global hooks apply |

Consequences: the guard must be one harness-neutral binary with a
`--harness claude|codex|agy` output dialect; Codex entries are appended
(trust keys are index-based) and need a one-time `/hooks` approval that
`install --check` reports; Antigravity gets a named handler key
`anvil-coding-fleet` (add/remove by key).

## 3. Enforcement design

### 3.1 `anvil-guard` (new `cmd/anvil-guard`, installed at `~/.local/bin/anvil-guard`)

State per repository at `~/.local/state/anvil-guard/<sha256(git toplevel)>/`:

- `seal.json` — `{sealedAt, base: {headCommit, treeDigest}, tests: [{path, digest}], red: CommandEvidence, amendments: [{at, reason, before, after}]}`
- `green.json` — `CommandEvidence` of the passing run, must postdate the seal
- `diff-review.json` — `{reviewedAt, diffDigest, base, findings: [...]}`

Subcommands:

| Command | Purpose |
|---|---|
| `seal --tests <globs\|paths> --red-command <argv…>` | Runs the red command, requires non-zero exit, records test digests + red evidence |
| `verify --green-command <argv…>` | Runs green, requires exit 0, re-digests sealed tests, writes `green.json` |
| `reseal --reason <text>` | Explicit amendment; recorded as evidence, never silent |
| `diff-review record --findings <file>` | Digests `git diff HEAD` + untracked list, stores review |
| `hook --harness <h>` | Reads the harness payload on stdin; PreToolUse: deny edits to sealed test paths; PostToolUse(shell): re-digest and report; Stop: refuse stop while sealed tests changed, no green evidence, or diff review stale |
| `status` | Prints the machine-readable state the orchestrator reconciles |

No seal for the repository → every hook exits 0 immediately, so non-fleet
sessions are untouched. Test globs default to
`**/*_test.go **/*.spec.* **/*.test.* **/test_*.py **/tests/** **/testdata/**`
and are overridable per repository via `.anvil/guard.json`.

### 3.2 TDD sequence (Executor and every toolchain profile)

1. RED — write or extend tests; run them; they must fail for the intended
   reason; `anvil-guard seal`.
2. IMPLEMENT — sealed test paths are read-only (hooks + control plane).
3. GREEN — `anvil-guard verify`; the passing command evidence must postdate
   the seal.
4. FINAL DIFF REVIEW — read the real `git diff HEAD` (not the handoff
   summary), record findings with `anvil-guard diff-review record`; the Stop
   gate refuses to finish while the recorded diff digest differs from the
   current one.
5. RETURN — handoff `tests[]` entries cite `commandId`s; result carries the
   seal, green, and diff-review records.

Amending a sealed test is allowed only via `reseal --reason`; the
amendment is evidence the Code Review pass must look at.

### 3.3 Control plane (`controlplane/`, `codingfleet/handoff.go`)

- `AgentHandoffTest` gains `commandId`; `passed: true` without a matching
  exit-0, `current: true` `CommandEvidence` is invalid.
- `VerificationState.TestSeal{SealedAt, Tests[]{Path,Digest}, RedCommandID, Amendments[]}`;
  `ApplyVerification` rejects when observed test digests differ from the seal
  (non-repairable unless an amendment is recorded) or when no green
  `CheckEvidence` postdates the seal.
- `WorkflowResult.DiffReview{CommandID, DiffDigest, ReviewedAt, Findings[]}`
  required on the execution lane; the assurance pass must reference the same
  `DiffDigest` or is rejected as reviewing a different change.
- Assurance and evaluation lane results with zero `CommandEvidence` cannot
  carry pass/warn — disposition `unverified`.
- `controlplane.Pointer{Path, StartLine, EndLine, Symbol, Why}`; Research
  results carry pointers, not excerpts.
- `CheckpointPolicy` `file-and-native-session`: `checkpoint.json` + `plan.md`
  under `~/.local/state/swarm-runplane/goals/<goalId>/`, re-read on resume;
  native session state is a cache.

Amendments after the Phase 1 review (2026-08-25):

- **Evidence must resolve to guard records, not agent text.** A
  `commandId` in `tests[]`, `TestSeal.RedCommandID`, or `DiffReview` is valid
  only if it names a record `anvil-guard` itself produced (`seal.json` red
  run, `green.json`, `diff-review.json`), and `passed` must agree with that
  record's exit code. Handoff/result validation takes a guard-state
  snapshot (`anvil-guard status --json`) as input; the assurance pass
  obtains it by running the command, and the runplane supervisor reads the
  state directory itself after a foreign child exits. This removes the
  single-author problem for honest agents; a deliberate forgery of the
  state directory remains possible within one OS user and is what the
  LXC 135 holdout measures — a separate trust boundary is out of scope.
- **Checkpoints persist through the `goal` verb, never through file
  tools.** The orchestrator's authority already lists `goal`; the
  `swarm_runplane_lifecycle` MCP tool and `swarm-runplane goal
  checkpoint|show` CLI implement it against local state
  (`~/.local/state/swarm-runplane/goals/<goalId>/`) without requiring the
  HTTP service to be running. The orchestrator keeps `Filesystem write: none`.
- **Seal lookup is by edit target, not session cwd.** The hook resolves the
  repository of each written path; shell and Stop checks cover the cwd
  repository plus every repository the session touched (per-session touch
  log keyed by `session_id`/`conversationId`). Paths outside any sealed
  repository stay allowed.

### 3.4 Installer (`codingfleet install`)

Adds three managed hook registrations (all idempotent, dry-run/check aware,
removed by `--uninstall`):

- Claude: `hooks` block in `~/.claude/settings.json` (entries identified by
  the `anvil-guard` command path) **and** frontmatter `hooks:` in every
  rendered fleet definition that can write.
- Codex: matcher groups appended to `~/.codex/hooks.json`; `--check` reports
  missing `[hooks.state]` trust for them.
- Antigravity: `anvil-coding-fleet` handler in `~/.gemini/config/hooks.json`.

Plus `anvil-guard` binary build/link and a `scripts/bootstrap-tools.sh`
listing verifier tools (`ast-grep`, `golangci-lint`, `ruff`, `pyright`,
`tsc`, `actionlint`, `shellcheck`) — run by the user, never by the installer.
Missing verifier → the profile reports that check as unverified, never as
passed.

## 4. Specialist collapse (Phase 2): 44 → 10

Split rule (directive 3.2): a role exists only if it carries a distinct
verifier command set, a distinct verification environment, or a guardrail set
that must travel with write authority.

| New role | Absorbs | Verifier / environment |
|---|---|---|
| `toolchain-go` | go, go-adk-v2, mcp-a2a, observability, realtime-streaming, llm-provider-integration, integration, herdr | `gofmt -l`, `go vet`, `go build`, `go test -race`, `golangci-lint` (if present), `govulncheck` |
| `toolchain-rust` | rust, gpu-cuda, numerical-computing | `cargo fmt --check`, `cargo clippy --all-targets -D warnings`, `cargo test`; CUDA parity tests when the feature exists |
| `toolchain-python` | python, knowledge-ingestion (code) | `ruff check`, `ruff format --check`, `pyright`, `pytest -q` |
| `toolchain-web` | react-typescript, foundary-ui, data-visualization, accessibility (static) | `tsc --noEmit`, `eslint` (incl. jsx-a11y), `vitest run`, `vite build` |
| `toolchain-database` | postgresql, clickhouse, sqlite-recovery, data-migration | migration up→down→up on a scratch instance, `PRAGMA integrity_check`, never a live database |
| `toolchain-ops` | linux-systemd, github-ci | `systemd-analyze verify`, `actionlint`, `shellcheck` |
| `lens-browser` (read-only) | browser-ui-qa, accessibility (runtime) | Playwright + axe against a running app; states and viewports must actually be exercised |
| `lens-security` (read-only) | security-review, api-contracts (boundary checks) | `gitleaks`, `semgrep`/`gosec`, `govulncheck`, `npm audit`/`pip-audit`/`cargo audit` |
| `env-homelab` | proxmox, unraid, unifi-networking, ubiquiti-hardware, tailscale, home-assistant, media-automation | read-only API probes / dry-run only; all seven roles' "never mutate live" boundaries kept verbatim |
| `env-robotics` | robotics-drone | simulator-first; hardware never commanded during coding or verification |

Deleted, function absorbed elsewhere: `code-review` (→ Code Review unit),
`testing-verification` (→ TDD sequence in every writer), `repository-cartography`
(→ Research pointer schema), `performance` (→ benchmarks are toolchain tests;
"measure, don't guess" moves to the Executor contract), `agent-harness`.

Product-context domain roles (`finance-plaid`, `markets-ibkr`,
`health-telemetry`, `nexus-operations`, `swarm-orchestration`) are not agents
any more. Their instructions and boundaries are rendered to
`harness-agents/rendered/knowledge/<repo>.md` (grouped by each role's
`evidence[].repository`) for placement in that repository's layered
`CLAUDE.md`/`AGENTS.md`/`GEMINI.md`. The installer never writes into other
repositories.

Activation stays file/dependency-based (`go.mod` → `toolchain-go`), so the
existing selection machinery selects a verifier instead of a persona.
Routing tiers are kept as today (unmeasured); explicit user routes still win.

## 5. Phases

### Phase 1 — enforcement, context, prompts (dispatched 2026-08-25)

1. `cmd/anvil-guard` + `guard/` package, with tests (seal/verify/reseal/diff-review/hook dialects for the three payload shapes).
2. Control-plane changes in §3.3 with tests; conformance fixtures updated (`runplane/testdata/conformance`).
3. Installer hook registration for the three harnesses (§3.4) with tests; `install --check` trust report for Codex.
4. Rendered definitions: TDD + final-diff-review stages in Executor; assurance-must-execute in Code Review/Evaluator; Research pointer contract + breadth cap; output-hygiene block everywhere; runplane CLI reference moved out of the orchestrator prompt into a skill loaded on foreign dispatch; Claude frontmatter hooks.
5. Checkpoint-to-disk policy in catalog + render.
6. `scripts/bootstrap-tools.sh`; docs (`harness-agents/README.md`, `workflows.md`, `runplane/README.md`).

Gate: `go build ./... && go vet ./... && go test -race ./...`,
`codingfleet render --check`, offline conformance suite, `install --dry-run`
showing exactly the three hook registrations. Actual `install` is a separate
authorized step.

### Phase 2 — topology (after the §4 mapping is confirmed)

1. Catalog collapse per §4; `harness-agents/rendered/knowledge/` output; Factory repurposed to add toolchain/lens/env roles only.
2. Executor default: implement coupled changes in-parent; fan out only for disjoint-file work in isolated worktrees, with the independence reason recorded in the `SelectionEnvelope`.
3. Orchestrator gains `filesystemRead: ["."]` (still non-writing) to reconcile handoffs against real files.
4. Task-shape routing: bounded single-file → direct single-agent path (no orchestrator dispatch, no plan); multi-file → short `plan.md`; greenfield → existing plan pipeline. Executor activation on `implementation-plan.json` no longer implies a plan is required.
5. Global routing block (`CLAUDE.md`/`AGENTS.md`/`GEMINI.md`) and READMEs updated; installer cleans retired symlinks/profiles.

Gate: same as Phase 1 plus `install --check` after an authorized reinstall.

## Phase 3 — topology reduction + always-on TDD (decided 2026-08-25)

User decisions after reviewing the fleet diagram:
- Workflow layer reduced to **4 peers** (Research, Planner, Builder/Executor, Code Review) + orchestrator. **Debugger folded into Builder** (diagnose-before-fix), **Coding Evaluation and Factory removed from this swarm** — evaluation runs as a separate process and owns the Factory agent. The Go factory machinery (`factory_transaction.go`, `factory_policy.go`) stays in swarm-coder for that separate process to drive; only the workflow *role* and orchestrator wiring are removed, plus the orphaned `workflow-factory-write` authority profile.
- **Builder parallelization is conditional**: implement in-parent by default; fan out only for plan-marked independent, disjoint-file work in isolated worktrees when it materially cuts latency — never coupled/same-file work. Same "not every time" principle as the plan stage.
- **TDD is unconditional and lives at the Builder + guard**, not the Planner: the bounded direct route (no Planner) must still go RED→seal→IMPLEMENT→GREEN. Planner may sequence tests-first for complex work as an aid, never as the gate. A guard Stop-check flags *source changed with no active seal* so TDD can't be silently skipped.
- **Bounded review loop**: Code-Review↔Builder repair is capped by the verification budget (2 passes / 1 repair); on exhaustion without acceptance, escalate to the user.

### Model tiers (proposed, from the user's diagram)
Generalize the existing `routingTier` (advanced/standard) into named tiers resolved per provider from one file both render and dispatch read:
- Powerhorse — Fable high | Sol xhigh | Gemini Pro (Planner, Research, hard reasoning)
- Workhorse — Opus 5 medium | Sol medium | Gemini 3.7 Flash high (Builder, execution)
- Quick — Opus 5 low | Luna high | Gemini 3.7 Flash medium (mechanical/quick specialist verification)
Tier→role assignment validated on the eval suite; the table updates as models change. Lesson from Phase 2: the run-plane binary embeds the catalog at build time, so it must be rebuilt whenever the catalog/tiers change or foreign dispatch silently drops changed roles.
