---
name: repo-setup
description: Make a repository ready for agentic development — interview the user about purpose and tooling, then set up AGENTS.md / CLAUDE.md, the build runner, version control, and lint/format gates. Works on an existing repo or a new one.
---

# Repo Setup

Get a repository into the shape where agents can work in it safely: instruction files that say what the project is and how to verify it, a build and test command that actually runs, and gates that catch mistakes mechanically.

Invocation: `/workcell:repo-setup`
Prompting Reference: [`docs/models/gemini-3.7-flash/prompting.md`](../../runtime/docs/models/gemini-3.7-flash/prompting.md)

You are the orchestrator ([ADR 0007](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents via Antigravity's `invoke_subagent`, hold the human gates, run `git` / `jj` / `gh` and scripts via `run_command` for branch, merge, and issue-state operations, and read gate output and handoff records using the [`anvil.agent-handoff/v1`](../../runtime/handoff.md) schema. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator surveys the repository, interviews the human, and coordinates setup agents. Per the Gemini 3.7 Flash guide, place critical constraints first, demand verified execution commands, and keep instruction files lean.

## Critical Constraints

- **Goal:** Equip a repository with verified instruction files, reliable build/test commands, and mechanical lint/format gates.
- **Constraints:** Never overwrite existing instruction files or CI workflows without presenting a diff. Never document commands that do not run. Maintain `AGENTS.md` as the single source of truth.
- **Success Criteria:** Verified `AGENTS.md` with symbolic links, working verification commands confirmed by an integrator baseline, and wired advisory hooks.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **interview**: Survey repository and interview user about purpose, verification commands, and tooling.
2. **instruction setup**: Documenter establishes `AGENTS.md` as single source of truth with symlinks.
3. **build runner**: Configure build and test runners based on repo size and architecture.
4. **version control**: Adopt colocated jj repo if appropriate, or preserve git worktree compatibility.
5. **lint and format gates**: Install per-stack linters/formatters and verify documented commands via integrator baseline.

## Read before you ask

Dispatch a `researcher` agent via `invoke_subagent` to report what is already there: language and manifests, existing build/test/lint commands, CI workflows, version control (git, or `.jj/`), any current `AGENTS.md` / `CLAUDE.md` / `GEMINI.md`, and the test layout. `scripts/bootstrap-project.sh <dir>` reports the detected stack and tool readiness without installing anything, and is the fastest way to get that picture.

Then ask the human what the survey cannot tell you. State what you found so the questions are corrections rather than an interrogation:

- **Purpose** — what is this project, who uses it, and what does "working" mean? An instruction file that cannot answer this is decoration.
- **Verification** — the exact commands for build, test, and lint. Agents need a command they can run, not a description of one.
- **Build runner** — keep what exists, or move to something else? Ask specifically about **Bazel** if the repo is large, polyglot, or has a slow build: it is a real commitment and a bad default for a small one.
- **Version control** — stay on plain git, or adopt **jj**? A git-only repo still gets isolation through `workcell-ws`, which falls back to git worktrees under the same naming and teardown, so nothing is blocked; jj adoption with `jj git init --colocate` remains the recommendation for parallel waves, because one operation log and `jj undo` are what make many concurrent working copies recoverable.
- **Lint and format** — which tools, and are they advisory or blocking?
- **Conventions worth writing down** — the ones a newcomer gets wrong: layout, naming, error handling, what must never be edited by hand.

Recommend defaults for each rather than presenting a blank form, and mark which answers are blocking.

## Procedure

1. **Survey and interview.** Dispatch a `researcher` agent via `invoke_subagent` and run `scripts/bootstrap-project.sh <dir>` to inspect manifests, existing commands, and tooling. Interview the user regarding project purpose, verification commands, and build runner choices.
2. **Instruction files.** Dispatch the `documenter` agent via `invoke_subagent` to author `AGENTS.md` as the canonical instruction file. Link all harness-specific instruction files (`CLAUDE.md`, `GEMINI.md`) as symbolic links to `AGENTS.md`:
   ```bash
   ln -sf AGENTS.md CLAUDE.md
   ln -sf AGENTS.md GEMINI.md
   ```
3. **Build runner.** Configure build and test runners based on repo size and architecture.
4. **Version control.** When adopting jj, run `jj git init --colocate` at the repo root via `run_command` to enable operation logging and conflict recovery while preserving `.git/` compatibility.
5. **Lint and format gates.** Wire formatters, linters, and advisory hooks via `scripts/bootstrap-project.sh --install --with-hooks <dir>`. Everything it writes is added to the repository's `.git/info/exclude`, so none of it shows up in a diff or a commit. Any config that is genuinely code — a CI workflow, a build file, a Bazel target — goes through a `builder` test-first where it is testable, not hand-edited here.
6. **Verify with baseline.** Dispatch an `integrator` agent with `mode: baseline` via `invoke_subagent` to execute every command documented in `AGENTS.md`. Every documented command must run green.
7. **Report.** Report what was set up, what was left alone and why, and what the human still has to decide.

## Boundaries

Never overwrite an existing `AGENTS.md`, `CLAUDE.md`, or CI workflow without showing the human what changes — these encode decisions you were not present for. Never invent a build or test command to fill a section; if none exists, say so and offer to create one. Never adopt jj or Bazel because they are available: both are answers to specific problems, and imposing them on a repo that does not have those problems is a cost with no return. This skill sets a repository up; it does not implement features in it.

Based on the requirements and constraints above, execute the repo-setup workflow systematically.
