# Single change protocol

Use this internal `/build` mode when one executable brief and isolated source are sufficient. It follows the same test, review, documentation, and acceptance rules as a dependency run without requiring a milestone or the multi-task ledger. A serial chain of changes in a plain Git repository can reuse this protocol with each next task based on the preceding accepted commit.

## Keep the brief and evidence

Save the existing or planner-completed `brief.json` and Markdown plan in a durable directory outside all source workspaces. Preserve the goal, non-goals, assumptions, decisions and authorization, exact base revision, branch, implementation ownership, acceptance oracles, required verification argv, and any input review, diagnosis, or profiling evidence. The dispatched portion follows [`agents/handoff.md`](../../../agents/handoff.md): `issue` is a real existing number or `null`; `brief.acceptanceTests` carries `name`, `kind`, and `oracle`. Explicit `brief.testOwnership[]` covers tests outside implementation ownership. Tests may otherwise stay inside the owned subtree.

Reuse an executable brief rather than dispatching another planner. Missing executable detail goes to a planner under [/plan](../../plan/SKILL.md)'s chosen planning mode. The planner authors the brief and acceptance criteria; the orchestrator reviews them. Research is managed within planning, and existing evidence is reusable. Markdown is the default, with HTML only when requested. Do not fabricate issue numbers, milestone records, or `Closes` references.

## Isolate and seal

Use `workcell-ws` with the assigned branch and pinned immutable base, following [`docs/workspaces.md`](../../../docs/workspaces.md). Preserve the repository's chosen VCS. In Jujutsu, resolve a real commit from `trunk()` or the supplied integration bookmark. In plain Git, pin the configured target branch commit and use the assigned worktree; do not convert the repository for this mode.

- **Feature or fix:** A specifier creates the workspace, authors the runnable acceptance tests, demonstrates honest RED, records the seal, and hands it to a builder. The planner's oracles specify behavior; the specifier makes them runnable. No builder starts without the seal. A bug fix carries the debugger's real reproduction and minimal case into these tests.
- **Behavior-preserving refactor or optimization:** The orchestrator creates the workspace with `workcell-ws add <branch> --base <base>`. An integrator with `mode: baseline` runs the existing tests named by `sealedTests` using the exact `baselineCommand`, proves GREEN, and records a `kind: baseline` seal. Only then does a builder with `mode: refactor` begin. No specifier is required, and baseline tests are unchanged. A failing baseline stops implementation and returns its evidence.

## Implement and obtain independent review

The builder works within its assigned ownership, verifies the bound command using `tdd-guard verify --green-command`, runs relevant targeted regressions, and exercises the changed runnable surface. Independent reviewers inspect the whole task diff and return findings against its actual revision. Critical or high findings block acceptance. The orchestrator chooses reviewer assignments, further repair, and renewed verification from progress and remaining evidence; there is no fixed pass count or required team size. Preserve useful findings and never duplicate a review of unchanged source merely because another entry workflow also names review.

A necessary test amendment goes back to the specifier with evidence that the oracle is wrong, for RED proof and an explicit `tdd-guard reseal --reason <text>`. Builders do not silently redefine acceptance. Baseline tests cannot be amended inside behavior-preserving scope. If satisfying the request requires a different contract, return that scope decision before implementing it.

The builder returns its structured handoff, immutable source commit, changed files, command IDs, runtime proof, and review findings with `pr: null`. In Jujutsu record the stable `changeId` and immutable `commitId`; in plain Git record `git rev-parse HEAD` as `commitId`, with `changeId: null`. Retain the source workspace and store all findings and logs outside it. Internal review findings return to this build, never to a recursively invoked standalone `/review` workflow.

## Verify and accept

Include required documentation using [finalization](finalization.md) before the integrator verifies the already-combined final ref. This is the integrator's direct-ref procedure; it does not create a synthetic multi-task ledger. Capture the source commit and guard base/tree digest before and after checks; a check that changes source invalidates its run. Remeasure optimization work against its profiler baseline after combined verification.

The orchestrator reads real command outcomes and fresh `tdd-guard status --json` in the retained builder workspace. Require `ready: true`, `greenStale: false`, current independent findings without blocking issues, matching source/base evidence, and successful final verification. A changed commit, tree, or target base requires refreshed verification and review as applicable. Failed checks return to the responsible builder rather than producing a readiness claim.

Save `completion.json` outside source with the exact source commit and base, brief revision, handoff paths, guard output path, verifier command IDs, finalization record if any, and the orchestrator's decision. This records local readiness, not a merged PR. For authorized PR delivery, its head must equal the verified source; inspect `gh pr checks` for that head before an authorized merge. Retain workspaces and evidence through outstanding finalization or merge, or explicit abandonment.

## Resume or expand the task graph

Read the saved brief and handoffs, find the retained workspace, and compare actual source and base with recorded evidence. Reuse valid seals and completed stages; refresh stale GREEN, review, or integration evidence. Do not recreate an existing PR or overwrite another run. If new dependencies require coordination, carry the same decisions, source, and accepted evidence into the [dependency run protocol](dependency-runs.md), asking only for newly required scope decisions.
