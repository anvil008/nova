---
name: repo-setup
description: Make a repository ready for agentic development — interview the user about purpose and tooling, then set up AGENTS.md / CLAUDE.md, the build runner, version control, and lint/format gates. Works on an existing repo or a new one.
---

# Repo Setup

Get a repository into the shape where agents can work in it safely: instruction files that say what the project is and how to verify it, working build and test commands, and mechanical lint and format gates. Works on an established codebase or an empty directory.

Invocation: `/workcell:repo-setup`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

You are the orchestrator ([`ADR 0007`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch specialists using `spawn_subagent` (running in foreground or with `background: true` tracked via `get_command_or_subagent_output`, or coordinated via `/workflow`), hold human gates, run VCS and setup scripts using shell execution, and read gate evidence and handoff records conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md). You never author project code or documentation directly. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

## Outcome, Constraints, and Success Criteria

- **Outcome:** Equip a repository with verified instruction files, reliable build/test commands, and mechanical lint/format gates.
- **Constraints and Boundaries:** Never overwrite existing instruction files or CI workflows without presenting a diff. Never document commands that do not run.
- **Success Criteria:** Verified `AGENTS.md` with symbolic links, working verification commands confirmed by an integrator baseline, and wired advisory hooks.

## Ordered Gates

Execution proceeds through five strict, ordered gates:

1. **interview**: Survey repository and interview user about purpose, verification commands, and tooling.
2. **instruction setup**: Documenter establishes `AGENTS.md` as single source of truth with symlinks.
3. **build runner**: Configure build and test runners based on repo size and architecture.
4. **version control**: Adopt colocated jj repo if appropriate, or preserve git worktree compatibility.
5. **lint and format gates**: Install per-stack linters/formatters and verify documented commands via integrator baseline.

## Input and Output Contracts

Subagent dispatch uses native Grok `spawn_subagent` (with `background: true` for parallel tasks, polled via `get_command_or_subagent_output`) or multi-step `/workflow` routines. Each dispatch exchanges structured handoff payloads conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

- **Survey Researcher Inputs and Outputs:**
  - **Inputs:** Repository root directory and existing build/config files.
  - **Outputs:** Repository scan summary, language detection, and candidate verification commands.
- **Documenter Inputs and Outputs:**
  - **Inputs:** Project goals, verification commands, and directory layouts.
  - **Outputs:** Standardized `AGENTS.md`, symlinked `CLAUDE.md`, and instruction file line budgets.
- **Integrator Baseline Inputs and Outputs:**
  - **Inputs:** Documented build, test, and lint commands.
  - **Outputs:** Verified command execution evidence proving all documented workflows pass.

## Procedure

1. **Survey and interview.** Dispatch a `researcher` via `spawn_subagent` and execute `scripts/bootstrap-project.sh <dir>` to inspect repository state, language manifests, and existing tooling. Interview the user to determine project purpose, canonical verification commands, build runners (e.g., standard vs Bazel), version control adoption, and lint/format tools.
2. **Version control.** When adopting Jujutsu, initialize colocation at repository root: `jj git init --colocate`. Otherwise ensure git worktree compatibility via `workcell-ws` ([`docs/workspaces.md`](../../runtime/docs/workspaces.md)).
3. **Instruction setup.** Dispatch a `documenter` via `spawn_subagent` to create `AGENTS.md` as the single source of truth, detailing project purpose, directory layout, verification commands, and conventions. Symlink harness-specific instruction files: `ln -sf AGENTS.md CLAUDE.md`.
4. **Build runner and tooling.** Configure build and test runners. Install stack-specific linters and formatters and wire advisory hooks:

   ```bash
   scripts/bootstrap-project.sh --install --with-hooks <dir>
   ```

   Everything it writes is added to the repository's `info/exclude`, so none of it shows up in a diff or a commit. Any config that is genuinely code — a CI workflow, a build file, a Bazel target — goes through a `builder` test-first where it is testable, not hand-edited here.

5. **Baseline verification.** Dispatch an `integrator` via `spawn_subagent` with `mode: baseline` conforming to [`anvil.agent-handoff/v1`](../../runtime/handoff.md) to confirm documented build, test, and lint commands run cleanly.

## Boundaries

Never overwrite an existing `AGENTS.md`, `CLAUDE.md`, or CI workflow without showing the human what changes — these encode decisions you were not present for. Never invent a build or test command to fill a section; if none exists, say so and offer to create one. Never adopt jj or Bazel because they are available: both are answers to specific problems, and imposing them on a repo that does not have those problems is a cost with no return. This skill sets a repository up; it does not implement features in it.

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
