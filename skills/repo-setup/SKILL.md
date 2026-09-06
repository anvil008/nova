---
name: repo-setup
description: Make a repository ready for agentic development — interview the user about purpose and tooling, then set up AGENTS.md / CLAUDE.md, the build runner, version control, and lint/format gates. Works on an existing repo or a new one.
---

# Repo setup

Get a repository into the shape where agents can work in it safely: instruction files that say what the project is and how to verify it, a build and test command that actually runs, and gates that catch mistakes mechanically. Works on an established codebase or an empty directory.

The orchestrator owns scope, user decisions, dispatch, and final evaluation. Specialists author plans and source changes; independent evidence determines completion. Team size follows useful work and explicit user constraints. See [ADR 0029](../../docs/adr/0029-composable-workflows-and-native-research.md).

This orchestrator interviews the human and assigns documentation to `documenter` and code-like configuration to `builder`.

## Read before you ask

Dispatch a `researcher` agent to report what is already there: language and manifests, existing build/test/lint commands, CI workflows, version control (git, or `.jj/`), any current `AGENTS.md` / `CLAUDE.md` / `GEMINI.md`, and the test layout. `scripts/bootstrap-project.sh <dir>` reports the detected stack and tool readiness without installing anything, and is the fastest way to get that picture.

Then ask the human what the survey cannot tell you. State what you found so the questions are corrections rather than an interrogation:

- **Purpose** — what is this project, who uses it, and what does "working" mean? An instruction file that cannot answer this is decoration.
- **Verification** — the exact commands for build, test, and lint. Agents need a command they can run, not a description of one.
- **Build runner** — keep what exists, or move to something else? Ask specifically about **Bazel** if the repo is large, polyglot, or has a slow build: it is a real commitment and a bad default for a small one.
- **Version control** — stay on plain git, or adopt **jj**? A git-only repo still gets isolation through `workcell-ws`, which falls back to git worktrees under the same naming and teardown, so nothing is blocked; jj adoption with `jj git init --colocate` remains the recommendation for parallel waves, because one operation log and `jj undo` are what make many concurrent working copies recoverable.
- **Lint and format** — which tools, and are they advisory or blocking?
- **Conventions worth writing down** — the ones a newcomer gets wrong: layout, naming, error handling, what must never be edited by hand.

Recommend defaults for each rather than presenting a blank form, and mark which answers are blocking.

## Procedure

1. **Survey** with a `researcher` agent plus `scripts/bootstrap-project.sh <dir>`.
2. **Interview** as above, with your recommendations attached.
3. **Version control**, if adopting jj: `jj git init --colocate` at the repo root. Colocation keeps `.git/` working, so existing tooling, CI, and `gh` are unaffected.
4. **Instruction files — one source of truth.** Dispatch the `documenter` agent to write **`AGENTS.md`** as the single real instruction file, covering purpose, layout, the exact verification commands, and the conventions from the interview. Every other harness's instruction file is a symbolic link to it, never a second copy:

   ```bash
   ln -sf AGENTS.md CLAUDE.md      # and GEMINI.md where a harness wants its own name
   ```

   Where the repository already has a divergent `CLAUDE.md` and `AGENTS.md`, merge both into `AGENTS.md` first and show the human that diff; only then replace `CLAUDE.md` with the link. Keep the file inside the line budget the [`docs`](../docs/SKILL.md) gate enforces — a long instruction file is one nobody reads and every agent pays for. State facts, not aspirations: a documented command that does not run is worse than none.
5. **Tooling and gates.** Install the per-stack formatters and linters and wire the advisory hooks:

   ```bash
   scripts/bootstrap-project.sh --install --with-hooks <dir>
   ```

   Everything it writes is added to the repository's `info/exclude`, so none of it shows up in a diff or a commit. Source configuration changes such as CI workflows, build files, and Bazel targets use [build](../build/SKILL.md), carrying the setup decisions and authorization. Build establishes the missing executable checks, isolation, specifier RED or appropriate protected baseline, implementation, independent review, and final verification. Do not dispatch an unprepared builder directly.
6. **Prove it.** Dispatch an `integrator` with a brief conforming to [`agents/handoff.md`](../../agents/handoff.md) and carrying `mode: baseline`: run the documented verification on the untouched tree at `base`, return command-linked evidence, and perform no merge. It runs the documented build, test, and lint commands exactly as written in the instruction files. This is the whole point of the setup: if the commands in `AGENTS.md` do not run, the file is a liability. Fix and re-run until they do.
7. **Report** what was set up, what was left alone and why, and what the human still has to decide.

## Boundaries

Never overwrite an existing `AGENTS.md`, `CLAUDE.md`, or CI workflow without showing the human what changes — these encode decisions you were not present for. Never invent a build or test command to fill a section; if none exists, say so and offer to create one. Never adopt jj or Bazel because they are available: both are answers to specific problems, and imposing them on a repo that does not have those problems is a cost with no return. This skill sets a repository up; it does not implement features in it.

## Source changes

Route authorized CI, build, and source configuration changes through [build](../build/SKILL.md), carrying the existing goal, decisions, and authorization. Build owns executable checks, workspace isolation, independent test protection, implementation, review, documentation, and final verification. A direct builder dispatch without that preparation is incomplete. Return the verified source to this workflow; deployment still uses the named target and commit authorization.
