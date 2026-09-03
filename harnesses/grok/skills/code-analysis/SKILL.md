---
name: code-analysis
description: Hunt real defects across a codebase end-to-end — reproduce each as a failing test, fix it, and open one PR to main. Correctness only; never refactors for taste or adds features.
---

# Code Analysis

Find what is actually broken, prove it, and fix it. Every defect that ships in the PR arrives with a test that failed before the fix and passes after — no speculative defensiveness, no refactoring for taste, and no nearby cleanups. One PR to `main` at the end.

Invocation: `/workcell:code-analysis`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run workspace and VCS operations using shell commands, and read gate output and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never read or edit the target project's code directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Hunt down substantiated defects, reproduce them with honest failing tests, implement minimal verified fixes, and deliver a single clean PR to `main`.
- **Constraints and Boundaries:** Correctness only; never refactor for taste or add features. Never implement a fix for an issue that lacks an honest failing test sealed by a specifier. Never edit test files during implementation.
- **Success Criteria:** Every fixed defect has an honest red test sealed before implementation and green evidence after, validated through independent adversarial review.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **reproduction**: Baseline the tree and reproduce candidate defects with concrete failure scenarios.
2. **RED seal**: A `specifier` agent encodes each reproducible failure as an honest failing test and establishes a `tdd-guard seal`.
3. **GREEN**: A `builder` agent implements the minimal fix against the sealed test in an isolated workspace, confirming passing status without modifying the test.
4. **review**: Independent review passes verify the fix introduces no regressions or unapproved changes.
5. **pull request**: A single, clean pull request to `main` is opened incorporating all verified fixes with their command evidence.

## Input and Output Contracts

Subagent dispatch uses native Grok `spawn_subagent` (with `background: true` for parallel tasks, polled via `get_command_or_subagent_output`) or multi-step `/workflow` routines. Each dispatch exchanges structured handoff payloads conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

- **Integrator Baseline Inputs and Outputs:**
  - **Inputs:** Target codebase base commit, baseline command, and workspace configuration.
  - **Outputs:** Verification command evidence, pre-existing defect map, and baseline test status.
- **Reviewer Hunt Inputs and Outputs:**
  - **Inputs:** Assigned lens (`correctness`, `tests`, `security`, `performance`, `api-contract`), scope glob, and codebase commit.
  - **Outputs:** Structured candidate defect findings with reproduction steps and failure scenarios without editing files.
- **Specifier Inputs and Outputs:**
  - **Inputs:** Defect reproduction brief, assigned issue key, and workspace path.
  - **Outputs:** Sealed honest failing test manifest with `tdd-guard seal` evidence.
- **Builder Inputs and Outputs:**
  - **Inputs:** Assigned issue, sealed test command, and isolated workspace path.
  - **Outputs:** Verified passing fix, `tdd-guard verify` GREEN evidence, and review pass records.

## Procedure

1. **Baseline.** Dispatch an `integrator` via `spawn_subagent` with a brief conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) carrying `mode: baseline`: run documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge. A pre-existing failing suite maps existing defects rather than blocking progress.
2. **Hunt.** Dispatch `reviewer` agents in parallel via `spawn_subagent` (with `background: true` and checked via `get_command_or_subagent_output`), one lens each over the target area: `correctness` and `tests` always, plus `security`, `performance`, `api-contract`, `backend`, `integrations`, or `frontend` as code warrants. Reviewers return structured findings with concrete failure scenarios and never edit code.
3. **Adversarial verification.** Dispatch a fresh `reviewer` via `spawn_subagent` that did not originate the finding to attempt refutation against the code. Only findings that survive genuine refutation advance; refuted findings are documented in the report.
4. **Plan.** Dispatch a `planner` via `spawn_subagent` with surviving findings. One issue per defect, ordered by severity, with disjoint `ownershipHint` globs and acceptance tests derived from the reproduction scenarios. Stop for human approval before creating GitHub tracking.
5. **Execute.** Run [`build`](../build/SKILL.md) in single-PR mode. For each issue, a `specifier` seals an honest failing test via `tdd-guard seal`, and a `builder` implements the fix in an isolated workspace without modifying the test.
6. **Integrate and open PR.** Dispatch an `integrator` via `spawn_subagent` to confirm all sealed tests pass and no regressions occurred. Open one final PR to `main` referencing closed issues and including all reproduction and test evidence.

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
