# Anvil Coding Fleet workflow contract

The native Coding Fleet has three routing layers:

1. one orchestration-only entry agent;
2. seven peer workflow units;
3. shared technical and domain specialist pools.

This is an adaptive swarm topology, not a mandatory serial pipeline and not an
executable ADK graph. The canonical catalog is the source of truth for all
Codex, Claude Code, and Antigravity projections.

## Coding Orchestrator Agent

`anvil-coding-orchestrator` is the only default entrypoint for coding tasks. It
owns the durable goal, dependency-ready queue, cross-unit integration,
checkpoints, and overall completion decision.

The orchestrator does not directly research, inspect, edit, test, or implement
target-project code. It dispatches the minimum sufficient workflow units,
reconciles their returned evidence with current state, and routes follow-up
through the appropriate unit. This keeps the front door focused on long-running
goal ownership instead of duplicating worker responsibilities.

For work that spans turns, handoffs, interruption, or context compaction, the
orchestrator binds these fields to the harness's observable native goal,
session, thread, or resume state:

- objective and acceptance criteria;
- constraints, granted authority, and stop conditions;
- decisions and completed evidence;
- runnable and blocked workflow-unit assignments;
- active unit identities and mutation ownership;
- exact next action.

On resume, observed repository and external state outrank stale checkpoints or
delegate claims. Only the orchestrator may declare the overall goal complete.

### User-directed model routing

The orchestrator parses explicit natural-language routes before scheduling.
Routes may cover every delegate (for example, `use Terra Max for all
subagents`) or individual lanes and roles (for example, `use Gemini 3.7 Flash
for execution and Opus for planning`). An explicit user route overrides fleet
defaults and is checkpointed with the assignments it governs.

Provider, family, model, and effort aliases resolve only against capabilities
that the active harness or supervisor has currently discovered and allowlisted.
Ambiguous, conflicting, or unavailable routes fail closed and are reported;
the fleet never silently substitutes another provider, family, model, or effort.

Routing is native-first. When the requested model belongs to the current
provider, the orchestrator always uses that harness's native subagent mechanism
with explicit model and effort overrides: Agy/Antigravity uses native Gemini
agents, Claude uses native Anthropic agents, and Codex uses native OpenAI
agents. The shared launcher is not used for same-provider work. This includes
Gemini-only evaluation runs, where the orchestrator and specialists remain
native Gemini sessions.

Only a request for a different provider crosses the shared supervised run
plane. The launcher starts the exact canonical workflow or specialist
definition as the foreign harness's main headless session, accompanied only by
a bounded task brief. A generic prompt is not a role definition, and a foreign
run must never start another Coding Orchestrator. The parent orchestrator
retains monitor, resume, message, cancel, evidence reconciliation, integration,
and completion authority.

The supervisor is an explicit authenticated loopback service, not a magic tool
or a hot-loaded daemon. The parent starts or uses it with
`/home/anvil/.local/bin/swarm-runplane serve`; it defaults to
`http://127.0.0.1:8083`, stores state in `~/.local/state/swarm-runplane`, and
reads its bearer token from `~/.local/state/swarm-runplane/auth.token`.
`SWARM_RUNPLANE_STATE`, `SWARM_RUNPLANE_URL`, `SWARM_RUNPLANE_TOKEN`, and
`SWARM_RUNPLANE_TOKEN_FILE` are the supported overrides.

Before starting a foreign run, the parent runs
`/home/anvil/.local/bin/swarm-runplane health` and
`/home/anvil/.local/bin/swarm-runplane capabilities` and fails closed unless
the exact canonical role and requested provider, family, model, and effort
capability are present. It starts with
`/home/anvil/.local/bin/swarm-runplane start --request route.json`;
the bounded role and task brief travels in that request file. Follow-up input
uses `/home/anvil/.local/bin/swarm-runplane send JOB_ID` via stdin and resumed
input uses `/home/anvil/.local/bin/swarm-runplane resume JOB_ID` via stdin,
never argv. The remaining lifecycle is
`/home/anvil/.local/bin/swarm-runplane list`,
`/home/anvil/.local/bin/swarm-runplane status JOB_ID`,
`/home/anvil/.local/bin/swarm-runplane events --after N JOB_ID`,
`/home/anvil/.local/bin/swarm-runplane cancel JOB_ID`, and
`/home/anvil/.local/bin/swarm-runplane evidence JOB_ID`.

Native and foreign children share only the small
`anvil.agent-handoff/v1` integration record: `runId`, `parentRunId`,
`canonicalRole` (the canonical catalog role ID), `provider`, `model`, `effort`, `mode`, `ownedFiles`, `limits`,
`changedFiles`, `tests`, `result`, and `disposition`. Harness-specific session,
process, retry, and storage state remains inside the harness that owns it.

For implementation work, the orchestrator performs one independent
verification pass and may request at most one focused repair followed by one
re-verification. That is two total verification passes, not an open-ended
agent loop. It stops early on acceptance, cancellation, blockage, exhaustion,
or no material change and emits one final answer or patch.

## Peer workflow layer

The second layer contains exactly seven units:

- **Research Agent** owns repository, runtime, UI, and current official-doc
  evidence. UI review is research work that selects browser UI, Foundary UI,
  accessibility, and visualization specialists as needed.
- **Planner Agent** owns solution, refactor, migration, and implementation
  planning. It selects specialists for the actual architecture, API, data,
  security, UI, provider, and domain surfaces.
- **Executor Agent** owns authorized target-project mutations, integration,
  repair, and proportional verification. It is the ordinary code-writing unit.
- **Code Review Agent** owns read-only correctness, security, contract, test,
  UI, migration, compatibility, and release assurance.
- **Debugger Agent** owns read-only diagnosis, competing hypotheses,
  reproduction, causal evidence, and the remediation contract.
- **Coding Evaluation Agent** owns read-only evaluation of the coding run,
  routing quality, evidence, verification, safety, and final communication.
- **Factory Agent** creates one missing technical or domain specialist in the
  canonical Swarm catalog, renders every native projection, and installs the
  generated definitions globally. It never edits a target project.

No workflow unit owns or invokes another workflow unit. Each receives one
explicit assignment from the orchestrator and returns evidence and control to
it. Research, Planner, Code Review, Debugger, and Coding Evaluation are
read-only. Executor owns ordinary target-project writes. Factory has narrowly
scoped write authority over the canonical specialist catalog, generated
projections, and installer-owned global harness state.

## Shared specialist pools

Every workflow unit can select from both shared pools:

- `anvil-cf-technical-*` covers language and framework implementation,
  repository mapping, architecture, APIs, security, testing, performance, UI,
  accessibility, data, infrastructure, provider integration, and observability.
- `anvil-cf-domain-*` covers product and operational context such as Nexus,
  Swarm, Proxmox, Unraid, UniFi, Ubiquiti hardware, Home Assistant, finance,
  health telemetry, media automation, markets, and robotics.

Pool membership is availability, not mandatory fan-out. A unit selects the
minimum specialists justified by task, repository, risk, or failure evidence.
For example, UI research can select browser UI QA, accessibility, Foundary UI,
and the relevant product-domain specialist; it does not need a separate UI
workflow agent.

Specialists inherit the narrower authority of the invoking unit. A writable
specialist cannot mutate files when selected by Research, Planner, Code Review,
Debugger, or Coding Evaluation. Specialist results are evidence, not automatic
integration or completion claims.

If a non-Factory unit proves that no existing specialist is sufficiently
specific, it returns the missing capability to the orchestrator. The
orchestrator dispatches Factory Agent, then resumes the original unit with the
generated definition. This preserves the flat peer layer; units do not call
Factory directly.
Factory returns the new definition to the orchestrator and never redispatches
itself or invokes another workflow unit.

## Parallel swarm scheduling

The orchestrator may run up to 25 materially independent workflow units in
parallel. Executor may run up to 20 independent specialist lanes; Research,
Planner, Code Review, Debugger, Coding Evaluation, and Factory may each run up
to 10. These declared `maxParallel` values are logical fleet ceilings, while
any lower native-harness, provider, or runtime cap is a hard effective limit.
Excess work remains queued and the lower constraint is reported. Parallelism
should reduce latency or add genuinely independent evidence:

- prefer read-heavy investigations and disjoint mutation ownership;
- serialize overlapping writes unless a harness-native worktree isolates them;
- keep one explicit integrator for every mutation surface;
- do not fan out trivial work or duplicate the same question;
- independently verify accepted results before releasing dependent work.

The orchestrator continues the active goal through routine phase boundaries. A
terminal state is verified completion, a genuine blocker, a requirement for
new authority, or an explicit user pause or goal change.

## Native harness seam

The provider-neutral catalog renders the same contract into Codex, Claude Code,
and Antigravity definitions. The installer exposes every canonical role as a
direct Codex headless profile, direct Claude agent, and direct Antigravity
agent, so a supervised foreign run can load the exact role contract rather than
reconstructing it in a prompt. Harness-native subagent tools provide the
same-provider run plane. These definitions do not claim an always-running
service or a durable store the harness cannot expose.

The separate Go ADK runtime remains responsible only for executable Swarm ADK
graphs. The repository-native Factory belongs to this coding fleet and creates
technical or domain specialists only; it does not create ADK roots, workflow
units, skills, services, or product code.
