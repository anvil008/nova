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
orchestrator persists `checkpoint.json` plus a short `plan.md` under
`~/.local/state/swarm-runplane/goals/<goalId>/` and mirrors the same fields into
the harness's observable native goal, session, thread, or resume state. The
files are the system of record; native session state is only a cache of them:

- objective and acceptance criteria;
- constraints, granted authority, and stop conditions;
- decisions and completed evidence;
- runnable and blocked workflow-unit assignments;
- active unit identities and mutation ownership;
- exact next action.

On resume the orchestrator re-reads those files first. Observed repository and
external state outrank stale checkpoints or delegate claims. Only the
orchestrator may declare the overall goal complete.

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
or a hot-loaded daemon. Before starting a foreign run the parent runs
`/home/anvil/.local/bin/swarm-runplane health` and
`/home/anvil/.local/bin/swarm-runplane capabilities` and fails closed unless the
exact canonical role and requested provider, family, model, and effort
capability are present. The bounded role and task brief always travels in the
`start --request route.json` file; follow-up and resumed input always travel on
stdin, never argv.

The rest of the lifecycle, the service bootstrap, and the environment overrides
are authored in
[`skills/swarm-runplane-foreign-dispatch.md`](skills/swarm-runplane-foreign-dispatch.md)
and installed at
`~/.local/share/anvil-coding-fleet/swarm-runplane-foreign-dispatch.md`, which is
the absolute path every rendered prompt cites. That document is read only when a
foreign dispatch is actually required, so it does not consume context in
ordinary turns.

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
  accessibility, and visualization specialists as needed. Its delegates are
  one-shot localization passes capped at about eight files each, and they return
  `Pointer` records — path, line range, symbol, and one line of why it matters —
  never file contents. Semantic questions about how a subsystem behaves stay in
  the parent, which re-reads only the identified line ranges.
- **Planner Agent** owns solution, refactor, migration, and implementation
  planning. It selects specialists for the actual architecture, API, data,
  security, UI, provider, and domain surfaces.
- **Executor Agent** owns authorized target-project mutations, integration,
  repair, and proportional verification. It is the ordinary code-writing unit,
  and it works test-first: RED (`anvil-guard seal`), IMPLEMENT with sealed test
  paths read-only, GREEN (`anvil-guard verify`), FINAL DIFF REVIEW over the real
  `git diff HEAD` (`anvil-guard diff-review record`), then RETURN. Moving a
  sealed test requires `anvil-guard reseal --reason <text>`, and that amendment
  is evidence Code Review must inspect.
- **Code Review Agent** owns read-only correctness, security, contract, test,
  UI, migration, compatibility, and release assurance. A review that executed no
  command is `unverified`, never pass or warn, and it must reference the same
  diff digest the execution result recorded.
- **Debugger Agent** owns read-only diagnosis, competing hypotheses,
  reproduction, causal evidence, and the remediation contract.
- **Coding Evaluation Agent** owns read-only evaluation of the coding run,
  routing quality, evidence, verification, safety, and final communication. Its
  own verdict is execution grounded: a scorecard with no executed command is
  `unverified`.
- **Factory Agent** creates one missing technical or domain specialist in the
  canonical Swarm Coder catalog, renders every native projection, and installs the
  generated definitions globally. It never edits a target project.

No workflow unit owns or invokes another workflow unit. Each receives one
explicit assignment from the orchestrator and returns evidence and control to
it. Research, Planner, Code Review, Debugger, and Coding Evaluation are
read-only. Executor owns ordinary target-project writes. Factory has narrowly
scoped write authority over the canonical specialist catalog, generated
projections, and installer-owned global harness state.

## Mechanical verification

Prompt-level instructions are not a gate. `anvil-guard` enforces the test seal
in all three harnesses through registered hooks:

- **PreToolUse** on the harness's edit tools denies writes to sealed test paths.
- **PostToolUse** on the harness's shell tool re-digests the sealed tests and
  reports any that moved.
- **Stop** (and Claude's `SubagentStop`) refuses to finish while sealed tests
  changed without a recorded amendment, no green evidence postdates the seal, or
  the recorded diff digest differs from the current one.

A repository with no seal is untouched: every hook exits 0 immediately with
empty stdout, so ordinary non-fleet sessions see nothing.

The control plane enforces the same contract on the records themselves, and it
resolves every claim against the records `anvil-guard` produced rather than
against the reporting agent's own text. The handoff and the workflow result are
parsed from the same prose, so agreement between them proves only internal
consistency; a guard snapshot (`anvil-guard status --json`, or the state
directory read directly by the run-plane supervisor after a foreign child exits)
is the corroborating record written by a different process.

- A `commandId` cited by `tests[]`, `TestSeal.RedCommandID`, or `DiffReview` must
  name a record `anvil-guard` itself wrote, and that record's **kind** must be
  the kind of run being claimed. `green` and `diff-review` both exit 0, so on
  exit code alone the `git diff HEAD` run would stand in as proof that the test
  suite passed. A handoff test resolves to `green` or `seal-red`,
  `TestSeal.RedCommandID` to `seal-red`, and `DiffReview.CommandID` to
  `diff-review`.
- The agent's own `CommandEvidence` for a cited `commandId` must match the guard
  record's argv and stdout digests and its exit code, and the exit code that
  decides pass or fail is read from the guard record. Otherwise one honest run
  backs any number of invented named checks.
- One guard record backs one named check. A second `tests[]` entry citing the
  same `commandId` under a different name is rejected, so N required checks need
  N real runs.
- `ApplyVerification` rejects observed test digests that differ from the seal
  unless an amendment is recorded, and rejects a pass with no green check
  postdating the seal. An execution-lane result must carry a `DiffReview`, and
  the assurance pass must reference the same `DiffDigest` or it is reviewing a
  different change. Assurance and evaluation results with zero `CommandEvidence`
  cannot carry pass or warn; their disposition is `unverified`.

Without guard state for the repository there is nothing to resolve against, so
the older self-consistency contracts still apply on their own.

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
