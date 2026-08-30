---
name: repo-setup
description: Make a repository ready for agentic development — interview the user about purpose and tooling, then set up AGENTS.md / CLAUDE.md, the build runner, version control, and lint/format gates. Works on an existing repo or a new one.
---

# Repo setup

Get a repository into the shape where agents can work in it safely: instruction files that say what the project is and how to verify it, a build and test command that actually runs, and gates that catch mistakes mechanically. Works on an established codebase or an empty directory.

You are the orchestrator: you interview the human, dispatch the agents, and hold the gates ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)). The `docs` agent writes the instruction files; a `builder` writes any config that is code.

## Read before you ask

Dispatch a `research` agent to report what is already there: language and manifests, existing build/test/lint commands, CI workflows, version control (git, or `.jj/`), any current `AGENTS.md` / `CLAUDE.md` / `GEMINI.md`, and the test layout. `scripts/bootstrap-project.sh <dir>` reports the detected stack and tool readiness without installing anything, and is the fastest way to get that picture.

Then ask the human what the survey cannot tell you. State what you found so the questions are corrections rather than an interrogation:

- **Purpose** — what is this project, who uses it, and what does "working" mean? An instruction file that cannot answer this is decoration.
- **Verification** — the exact commands for build, test, and lint. Agents need a command they can run, not a description of one.
- **Build runner** — keep what exists, or move to something else? Ask specifically about **Bazel** if the repo is large, polyglot, or has a slow build: it is a real commitment and a bad default for a small one.
- **Version control** — stay on plain git, or adopt **jj**? Workcell's builders isolate through `jj workspace add`, so a repo that will run parallel waves benefits from `jj git init --colocate`; a repo that will not is fine on git.
- **Lint and format** — which tools, and are they advisory or blocking?
- **Conventions worth writing down** — the ones a newcomer gets wrong: layout, naming, error handling, what must never be edited by hand.

Recommend defaults for each rather than presenting a blank form, and mark which answers are blocking.

## Procedure

1. **Survey** with a `research` agent plus `scripts/bootstrap-project.sh <dir>`.
2. **Interview** as above, with your recommendations attached.
3. **Version control**, if adopting jj: `jj git init --colocate` at the repo root. Colocation keeps `.git/` working, so existing tooling, CI, and `gh` are unaffected.
4. **Instruction files.** Dispatch the `docs` agent to write `AGENTS.md` (and `CLAUDE.md` / `GEMINI.md` where the harness wants its own) covering purpose, layout, the exact verification commands, and the conventions from the interview. Keep them inside the line budget the [`docs`](../docs/SKILL.md) gate enforces — a long instruction file is one nobody reads and every agent pays for. State facts, not aspirations: a documented command that does not run is worse than none.
5. **Tooling and gates.** Install the per-stack formatters and linters and wire the advisory hooks:

   ```bash
   scripts/bootstrap-project.sh --install --with-hooks <dir>
   ```

   Everything it writes is added to the repository's `info/exclude`, so none of it shows up in a diff or a commit. Any config that is genuinely code — a CI workflow, a build file, a Bazel target — goes through a `builder` test-first where it is testable, not hand-edited here.
6. **Prove it.** Dispatch an `integrator` to run the documented build, test, and lint commands exactly as written in the instruction files. This is the whole point of the setup: if the commands in `AGENTS.md` do not run, the file is a liability. Fix and re-run until they do.
7. **Report** what was set up, what was left alone and why, and what the human still has to decide.

## Boundaries

Never overwrite an existing `AGENTS.md`, `CLAUDE.md`, or CI workflow without showing the human what changes — these encode decisions you were not present for. Never invent a build or test command to fill a section; if none exists, say so and offer to create one. Never adopt jj or Bazel because they are available: both are answers to specific problems, and imposing them on a repo that does not have those problems is a cost with no return. This skill sets a repository up; it does not implement features in it.
