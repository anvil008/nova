---
name: code-refactor
description: Simplify a codebase end-to-end without changing what it does — consolidate duplicated modules, deepen shallow ones, delete dead paths — then open one PR to main. Behaviour-preserving only; never fixes bugs or changes features.
---

# Code Refactor

Make the code simpler while it keeps doing exactly what it did. Combine modules that were split for no reason, deepen ones whose interface is wider than their substance, collapse indirection that earns nothing, and delete dead code. One PR to `main` at the end.

Invocation: `/workcell:code-refactor`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run workspace and VCS operations using shell commands, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Simplify code architecture and eliminate redundancy while preserving external and observable behaviour identically.
- **Constraints and Boundaries:** Never touch, modify, add, or delete test files. The builder must never edit a test file. Full test suite must remain identically green before and after every edit. No bug fixes, no new features, and no dependency upgrades.
- **Success Criteria:** Baseline green seal verified, refactor implemented without touching test files, and clean single PR to `main` summarizing simplifications.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **green baseline**: Prove the full test suite is green on untouched tree before making any changes.
2. **behaviour-preserving change**: Implement simplifications without altering existing behaviour or modifying test files.
3. **GREEN**: Verify all existing tests remain green under a baseline seal.
4. **review**: Multi-lens review verifies behaviour preservation and confirms no test edits occurred.
5. **pull request**: Open single PR to `main` with verified simplifications and identical test outcomes.

## Input and Output Contracts

Subagent dispatch uses native Grok `spawn_subagent` (with `background: true` for parallel tasks, polled via `get_command_or_subagent_output`) or multi-step `/workflow` routines. Each dispatch exchanges structured handoff payloads conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

- **Integrator Baseline Inputs and Outputs:**
  - **Inputs:** Repository root, base commit, and verification commands.
  - **Outputs:** Baseline green evidence and `kind: baseline` seal.
- **Researcher Survey Inputs and Outputs:**
  - **Inputs:** Structural scope, architectural heuristics, and target modules.
  - **Outputs:** Deduplicated refactoring candidates citing file and line evidence without code edits.
- **Planner Inputs and Outputs:**
  - **Inputs:** Simplification targets and behaviour-preservation constraints.
  - **Outputs:** Dependency-ordered refactoring plan with disjoint ownership hints and baseline acceptance tests.
- **Builder Inputs and Outputs:**
  - **Inputs:** Refactoring task assignment with `mode: refactor`, baseline seal, and isolated workspace.
  - **Outputs:** Verified simplifications, `tdd-guard verify` GREEN evidence, two review passes recorded via `tdd-guard diff-review record`, and diff touching no test files.

## Procedure

1. **Baseline.** Dispatch an `integrator` via `spawn_subagent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) carrying `mode: baseline`: verify the untouched tree at `base`, return command-linked evidence, and perform no merge. If the suite is not green before starting, stop immediately.
2. **Survey.** Dispatch `researcher` agents via `spawn_subagent` (running with `background: true` and checked via `get_command_or_subagent_output`), one per area, guided by [`references/design-heuristics.md`](references/design-heuristics.md). Candidates include duplicated logic, modules failing deletion tests, single-caller abstractions, and dead exports. Researchers return structured evidence with `file:line` references, never edits.
3. **Plan.** Dispatch a `planner` via `spawn_subagent` with survey findings and behaviour-preservation constraints. Each issue represents one independently landable simplification with disjoint `ownershipHint` globs. `acceptanceTests` specify existing tests that must remain green. Stop for human approval before creating GitHub tracking.
4. **Execute.** Run [`build`](../build/SKILL.md) in single-PR mode omitting the specifier phase. For each issue, create a workspace with `workcell-ws add refactor/<issue-key> --base <integration-base>` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)). Dispatch an `integrator` via `spawn_subagent` with `mode: baseline` to establish a `kind: baseline` seal and hand off with `tdd-guard handoff --to builder`. Dispatch the `builder` via `spawn_subagent` in the same workspace with `mode: refactor`. The builder must never edit a test file; it runs the bound command through `tdd-guard verify --green-command`, retains GREEN evidence postdating the baseline seal, and records `tdd-guard diff-review record`. Reject any change-set whose diff touches a test file, and send it back.
5. **Review and PR.** Dispatch multi-lens `reviewer` agents via `spawn_subagent` to confirm behaviour preservation and verify no test files were touched. Merge intermediate PRs into the integration branch upon green evidence and open the final PR to `main`.

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
