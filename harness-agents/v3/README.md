# Swarm Coder agents — v3 (design, in progress)

v3 is a deliberate **simplification**. v1 (58 roles, 7 peers) and v2 (15 roles,
4 peers) were both heavier than the evidence justifies: on bounded single-repo
coding tasks our own DeepSWE benchmarks put the swarm at rough parity with a
single agent at ~2.4× the cost, and the published literature (Cognition, the
Anthropic multi-agent post, the Berkeley MAST failure study, Agentless vs. the
SWE-bench leaderboard, compute-matched studies) converges on the same verdict:
**a single strong agent is the right default for tightly-coupled coding; multi-agent
pays off only for genuinely parallel, independent, breadth-first work.**

## Principles

- **Single strong agent is the default.** Fan out only where subtasks are
  genuinely independent (disjoint files, distinct research areas, distinct
  review lenses).
- **Native subagents, not headless scripts.** Use each harness's own subagent
  primitive (Claude `Agent` tool + `isolation:"worktree"`; Codex/Agy native
  agents; `swarm-runplane` only for cross-provider work).
- **GitHub is the source of truth.** Plans become GitHub issues under a
  milestone; the issues *are* the durable state (survives crashes, resumable,
  observable). A future nexus Kanban can pull from it.
- Don't let the orchestration skill regrow into a role catalog. Keep it minimal.

## Agents (4)

Small, single-purpose, native subagents:

- **research** — explore code / docs / runtime / prior-art; read-only; returns findings.
  Owns `read-the-damn-docs`, `find-docs`.
- **builder** — implement one unit of work end-to-end (branch → change → PR); the
  only writer; forbidden from committing to `main`. Owns `jj`, `full-output-enforcement`,
  and `builder-frontend` (basic UI). See `docs/adr/0001-agent-owned-skills.md`.
- **code-reviewer** — assurance; read-only; one instance per review *lens*.
  Owns `code-reviewer-frontend-review` (UI/UX review, from the old anvil-ui-review).
- **docs** — documentation specialist; the docs-scoped writer. Standardizes &
  reviews docs to a fixed practice (update-don't-duplicate, lean `CLAUDE.md`/
  `AGENTS.md`, ADRs), backed by the mechanical `docs-check`. Owns `grill-with-docs`.

(No planner agent — planning is a skill; see below.)

**Agent-owned skills.** An agent may carry its own domain skills: give it the `Skill`
tool and a `## Skills` section in its `AGENT.md` (with a boundary against the
orchestration skills). Skills are reused from the global install (e.g. `jj`) or vendored
under `agents/<agent>/skills/<skill>/`. Only agents that need them get `Skill`; the
read-only leaves (research, code-reviewer) stay skill-free. Convention: ADR 0001.

## Skills (4) + one human gate

Planning, plus **one orchestrator skill per fan-out phase**. Each orchestrator is
the same fan-out mechanism (spawn N native subagents → collect → merge → verify)
specialized for its phase. Kept as separate skills (not one shared engine) so
each is simple to invoke and evolve independently — the operator's chosen topology.

- **planner skill** — investigate → **HTML plan report + JSON sidecar** → human
  gate → idempotent GitHub milestone (= plan name) + issues. **Built.**
- **research orchestrator skill** — split by area / source; spawn read-only
  research agents; dedupe + merge findings (conflicts + coverage gaps). **Built.**
- **build orchestrator skill** — the flagship wave loop (below): split by
  unblocked GitHub issue; spawn builder agents in isolated worktrees under
  file-ownership; integrate diffs + re-test each wave; unblock the next.
- **code-review orchestrator skill** — split by lens (correctness / security /
  perf / tests); spawn read-only code-reviewer agents; dedupe + adversarially
  verify findings before reporting a ranked verdict.

Plus one **utility** skill (not an orchestrator):

- **use-other-harness skill** — explicit, user-triggered escape hatch to run a one-shot
  subagent in another harness (Claude / Codex / Antigravity `agy`) via headless mode; the
  user names harness + model + effort. Replaces the old `swarm-runplane` run-plane + MCP.

Lifecycle skills (beyond the build core):

- **docs skill** — standardize + review documentation to the practice standard, write
  ADRs, and run the mechanical `docs-check` (instruction-file budget + ADR format).
- **deploy skill** — ship a verified change safely: pre-flight → version/changelog →
  CI/CD → **human-gated deploy** → verify → rollback (ADR + release notes via docs).

  | phase | split by | isolation | merge | fan out |
  |---|---|---|---|---|
  | research | area / source | read-only | dedupe + merge findings | yes |
  | build | unblocked issue / file | worktree + ownership | integrate diffs + retest | when independent |
  | review | lens | read-only | dedupe + adversarial verify | yes |

  Fan-out count scales to the task (real areas / applicable lenses / independent
  change-sites), not a fixed N. The **human gate** lives in the planner skill: no
  GitHub write without explicit approval.

## The flagship workflow: plan → issues → parallel builders

1. planner skill → HTML plan + sidecar (dependency-annotated, ownership-hinted issues,
   each carrying `acceptanceTests` — its TDD definition of done, rendered into the issue body).
2. Human approves.
3. Create milestone (= plan name) + issues.
4. Build wave loop: dispatch builders for every **unblocked** issue in parallel;
   each builder claims its issue (self-assign/label), owns a branch/worktree,
   seals the issue's `acceptanceTests` as its RED tests, implements to green, opens a
   PR linking the issue; wait for the wave; **integrate +
   verify** (PRs were tested against old `main`, so a combined test pass is
   required); mark done; unblock the next wave; repeat.
5. Optional: review recipe (lens-differentiated) per PR before merge.

The **primary agent** running the skill owns synthesis + final
integration-verification and is the sole completion authority.

## TDD enforcement (build-hooks)

The **builder** is the only writer, so its TDD cycle (RED -> `tdd-guard seal` ->
implement -> GREEN -> diff-review) is hook-enforced via **`build-hooks`** — a thin
wrapper over `tdd-guard` (`~/.local/bin/build-hooks <harness> <event>`). On Claude the
builder agent frontmatter registers the gate (PreToolUse on Edit/Write, PostToolUse on
Bash, Stop, SubagentStop), scoped to the builder subagent. research and code-reviewer are
read-only and carry no gate. Codex/Antigravity hooks are global (`~/.codex/hooks.json`,
`~/.gemini/config/hooks.json`) and need a one-time `/hooks` trust; enable there only if
global gating is wanted, otherwise the builder AGENT.md instructions still mandate the cycle.

## Open design decisions

- planner: single by default vs. judge-panel (N approaches) — default single.
- who runs the merge: a dedicated synthesis pass vs. the primary agent inline.
- build integration strategy: serial merge-with-retest vs. integration branch.
- how the build recipe enforces file-ownership so parallel builders don't clobber.

## Status

**Agents (4):** research · builder · code-reviewer · docs.
**Skills (7):** planner · research · build · code-review · docs · deploy · use-other-harness.
All built, reviewed, and green (37 tests). Installed natively in Claude, Codex, and
Antigravity. TDD is enforced on the builder via **build-hooks** → **`tdd-guard`**
(formerly `anvil-guard`; kept as a compat symlink). Documentation hygiene is enforced
mechanically by **`docs-check`**.

Deferred: the deep `tdd-guard` source rename (Go `cmd/` dir, internal strings, legacy
v2 catalog, state dir) — the tool is invoked as `tdd-guard` today via the built binary.
The live build still ships v2 at the top-level catalog until `embed.go` is rewired.
