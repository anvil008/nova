# Anvil Coding Fleet

This directory contains one provider-neutral workflow and specialist catalog
plus generated native projections for Codex, Claude Code, and Antigravity. The
catalog is the source of truth; files below `rendered/` are deterministic build
artifacts.

Workflow roles form a flat swarm: Coding Orchestrator Agent
(`anvil-coding-orchestrator`) is the one default entrypoint and durable goal,
integration, and completion owner; Research, Planner, Executor, Code Review,
Debugger, Coding Evaluation, and Factory are its seven peer workflow units.
The orchestrator only schedules and integrates. Each workflow unit dynamically
selects technical and domain specialists for its own lane, then returns evidence
and control to the orchestrator. No workflow unit owns another. These
definitions are not executable ADK graphs, live agent
processes, or proof that a runtime adapter is connected. Coding Orchestrator
durability uses each harness's observable native goal, session, thread, or
resume primitive plus the catalog's checkpoint contract; the separate Go ADK
runtime continues to own durable state only for executable Swarm graphs.

The native Claude Code projection is not the Anthropic Messages runtime. The
logical ADK alias `claude.fable` is a separate, API-native binding fixed to
`claude-fable-5`; it is reserved exclusively for the internal code-review
route. Alpha Ask and the manual coder/debugger routes remain on `codex.luna`.
Fable never falls back to Claude Code, Codex, Gemini, OpenAI, or another Claude model. Production
Fable readiness is default-off and requires both `ANTHROPIC_API_KEY` and the
operator's explicit `SWARM_FABLE_RETENTION_ACCEPTED=true` acknowledgement.
The API-native Fable provider contract remains in the sibling Swarm ADK
repository under `docs/providers/anthropic-fable.md`.

## Layout

- `canonical/catalog.json` — validated roles, evidence, activation signals,
  workflow lanes, the flat orchestrator-to-unit topology, shared specialist
  pools, durable orchestration and fail-closed model-routing metadata, routing tiers,
  and capability modes.
- `workflows.md` — the shared workflow operating contract and ADK seam.
- `rendered/codex/*.toml` — Codex role configuration layers.
- `rendered/claude/*.md` — Claude Code subagent definitions.
- `rendered/antigravity/*/agent.md` — Antigravity orchestrator, workflow units, and
  specialists. Every definition is both `mainAgent` and `subagent` selectable so
  supervised headless runs and native delegation load the same exact contract.

Leaf specialists use the `anvil-cf-` prefix. Workflow units use `anvil-wf-`;
the entrypoint is `anvil-coding-orchestrator`. Technical and domain roles are
shared worker pools, not fixed pipeline steps. Every workflow unit may select
evidence-justified leaves from both pools at the lane where they are needed;
no leaf is mandatory. When a non-Factory unit proves that no existing leaf is
sufficiently specific, it reports the gap to the orchestrator, which dispatches
Factory and then resumes the original unit. Factory is coding-only and
repository-native:
it adds one technical or domain role to Swarm Coder, renders all three projections,
and runs the global installer. Code Review owns assurance, while Coding
Evaluation scores the behavior and evidence of a coding-agent run without
repairing it. Domain roles cover Foundry Zero systems such as Proxmox, Unraid,
Home Assistant, Ubiquiti, finance, health telemetry, robotics, Nexus, and
Swarm.

## Durable native orchestration

`workflow.orchestration` is present on Coding Orchestrator Agent only. It fixes `goalMode` to
`native-durable`, `checkpointPolicy` to `native-session`, `schedulingPolicy` to
`dependency-aware`, enables proactive delegation, and grants the sole overall
completion authority. It does not add a daemon or a second session database.
Codex uses native goals and resumable threads; Claude Code and the other native
harnesses use their supported resumable session or conversation state. When a
harness cannot persist that state, the generated definition requires an honest
in-conversation checkpoint and forbids claiming durability.

Coding Orchestrator Agent checkpoints at phase transitions, handoffs, context compaction,
interruptions, and before yielding. A checkpoint records the objective,
constraints, decisions, completed evidence, runnable and blocked queues, active
delegate identities and file ownership, and the exact next action. On resume,
the orchestrator reconciles the checkpoint with current repository and external state
before releasing more work.

Coding Orchestrator Agent maintains a dependency-ready queue and proactively uses up to 25
parallel workflow units when doing so materially reduces latency or improves
independent assurance. Read-heavy investigations and disjoint file ownership
are preferred parallel work. Overlapping writes are serialized unless the
harness provides an isolated native worktree. The orchestrator continues until integrated
verification succeeds, work is genuinely blocked, new authority is required,
or the user pauses or changes the goal; workflow units and specialists never
declare the overall goal complete.

`maxParallel` is a logical fleet scheduling ceiling: 25 for Coding Orchestrator,
20 for Executor, and 10 for Research, Planner, Code Review, Debugger, Coding
Evaluation, and Factory. It does not manufacture provider or native-harness
capacity. A lower hard harness, provider, or runtime limit remains authoritative;
the owning workflow keeps excess work queued and records the residual constraint.

Explicit natural-language model routes override fleet defaults. The
orchestrator resolves provider, family, model, and effort aliases only against
current discovered and allowlisted capabilities, failing closed on ambiguity,
conflict, or unavailability. Routing is native-first: Agy/Antigravity uses
native Gemini agents, Claude uses native Anthropic agents, and Codex uses native
OpenAI agents whenever the requested provider matches the current harness.
Only a different-provider request uses the supervised run plane and exact
installed foreign role definition; the parent orchestrator retains all
lifecycle and completion authority.

The supported supervisor is the explicitly started, authenticated loopback
service at `/home/anvil/.local/bin/swarm-runplane serve`, defaulting to
`http://127.0.0.1:8083`. Its default state and token paths are
`~/.local/state/swarm-runplane` and
`~/.local/state/swarm-runplane/auth.token`; `SWARM_RUNPLANE_STATE`,
`SWARM_RUNPLANE_URL`, `SWARM_RUNPLANE_TOKEN`, and `SWARM_RUNPLANE_TOKEN_FILE`
override them. This service is neither a generic magic tool nor implicitly
hot-loaded by a role projection.

The supervised run plane defaults to a hard global admission cap of 25 jobs.
Operators can lower or raise that runtime cap with `serve --max-concurrent`; the
authenticated health response reports the configured `maxConcurrent` value.
That admission cap is independent of provider-specific process or account limits.

The parent must run `/home/anvil/.local/bin/swarm-runplane health` and
`/home/anvil/.local/bin/swarm-runplane capabilities` before foreign dispatch
and fail closed unless the exact canonical role and requested
provider/family/model/effort capability are present. It starts work with
`/home/anvil/.local/bin/swarm-runplane start --request route.json`. The bounded
foreign brief is carried by that request file, while
`/home/anvil/.local/bin/swarm-runplane send JOB_ID` and
`/home/anvil/.local/bin/swarm-runplane resume JOB_ID` read follow-up input from
stdin, never argv. The complete remaining lifecycle is
`/home/anvil/.local/bin/swarm-runplane list`,
`/home/anvil/.local/bin/swarm-runplane status JOB_ID`,
`/home/anvil/.local/bin/swarm-runplane events --after N JOB_ID`,
`/home/anvil/.local/bin/swarm-runplane cancel JOB_ID`, and
`/home/anvil/.local/bin/swarm-runplane evidence JOB_ID`.

Both native and foreign children return the small `anvil.agent-handoff/v1`
boundary: run and parent IDs, canonical catalog role ID, provider, model, effort, mode,
owned and changed files, limits, tests, result, and disposition. Provider-native
session and process state is not duplicated into a second control plane. The
orchestrator uses one independent verification pass plus at most one focused
repair and one re-verification—two total verification passes.

The native behavior is grounded in the official [Codex goals](https://learn.chatgpt.com/use-cases/follow-goals),
[Codex long-running work](https://learn.chatgpt.com/docs/long-running-work),
[Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents),
and [Claude Code session](https://code.claude.com/docs/en/how-claude-code-works)
and [subagent](https://code.claude.com/docs/en/sub-agents) contracts.

## Regenerate and verify

Run commands from the Swarm Coder repository:

```sh
go run ./cmd/codingfleet render
go run ./cmd/codingfleet render --check
```

`render` updates only recognized generated provider paths. `--check` is
read-only and fails on missing, changed, or stale generated files. Use
`codingfleet.RenderWithConfig` when a deployment needs different provider model
routing; checked-in output uses the repository defaults.

## Install on a development box

Inspect the proposed changes first, install, then verify:

```sh
go run ./cmd/codingfleet install --dry-run
go run ./cmd/codingfleet install
go run ./cmd/codingfleet install --check
```

The installer requires explicit, absolute roots internally. The CLI discovers
the Swarm Coder root from the current directory and uses the current user's home by
default; `--root /absolute/swarm-coder` and `--home /absolute/home` override them.

The managed installation owns only:

- `~/.claude/agents/anvil-coding-fleet`, a symlink to the generated Claude
  directory, plus one direct `~/.claude/agents/<role>.md` symlink per canonical
  role for exact `claude -p --agent <role>` loading. Other Claude agents are
  untouched.
- `~/.gemini/config/agents/anvil-cf-*`, `anvil-wf-*`, and
  `anvil-coding-orchestrator`, one symlink per generated Antigravity agent. Other
  Antigravity agents are untouched.
- The block between `BEGIN ANVIL CODING FLEET` and `END ANVIL CODING FLEET` in
  `~/.codex/config.toml`. It contains `[agents.<name>]` declarations with
  absolute `config_file` paths. Bytes outside the marked block are preserved.
- `~/.codex/<role>.config.toml`, one direct headless profile symlink per
  canonical role. Start an exact role with `codex exec --profile <role>`;
  `[agents.<name>]` declarations remain available for native subagents.
- The block between `BEGIN ANVIL CODING FLEET ROUTING` and its matching end
  marker in `~/.agents/AGENTS.md`, `~/.codex/AGENTS.md`, and
  `~/.claude/CLAUDE.md`, plus Antigravity's native global rule file at
  `~/.gemini/GEMINI.md`. It routes top-level coding tasks through Coding
  Orchestrator Agent, carries the fail-closed user-directed model-routing
  contract, authorizes parallel peer workflow units, gives every unit access to
  both shared specialist pools, fixes mutation authority, and prevents recursive
  self-invocation; bytes outside the block are preserved.

Installation is idempotent. It refuses conflicting non-symlink targets and
duplicate, partial, reversed, or inline Codex markers. Codex config replacement
is atomic. Dry-run and check modes do not write.

Factory alone directly owns its specialist catalog/render/install lifecycle;
that does not bypass harness policy.
Its Antigravity projection uses the custom-agent `auto` command policy, so
high-risk commands and global or project non-workspace permissions still govern
writes to the Swarm Coder repository when Factory is invoked from another project.

## Update and rollback

After changing the canonical catalog, regenerate, review the native diff, run
the focused tests, and repeat install/check:

```sh
go test ./codingfleet ./cmd/codingfleet
go run ./cmd/codingfleet render
go run ./cmd/codingfleet install
go run ./cmd/codingfleet install --check
```

To roll back discovery without deleting auditable generated files:

```sh
go run ./cmd/codingfleet install --uninstall
```

Uninstall removes only the managed Claude, Codex-profile, and Antigravity
symlinks plus the managed Codex-config and global-routing blocks. It refuses
non-symlink agent targets rather than deleting them and preserves all bytes
outside its marked blocks.
