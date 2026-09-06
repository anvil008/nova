# Final source, documentation, and delivery

Use this stage after implementation tasks are accepted. Required documentation belongs in the same final source and PR as the software change. Standalone `/docs` is for a documentation request made on its own; an internal documenter assignment is not a new workflow.

## Include the relevant documentation

Dispatch documenters with the actual changed-file list, user-visible changes, accepted source refs, and docs-only ownership. Parallel documentation is useful when the owned areas are disjoint. They may start while independent tasks or candidate verification are running, but all required docs must be combined before the final verification. Have them run `skills/docs/scripts/docs_check.py` and the project's other applicable docs checks, including `render-diagrams.py --check` when its visuals are generated.

For a single change, combine the pinned implementation and documenter commits in an isolated final workspace, preserving both originals. For a dependency run, follow [the final-documentation run protocol](../../../docs/build-runs.md#final-documentation-and-pr-source): create a separate final branch from the accepted integration commit, combine the pinned docs commits there, and keep `<planId>-integration` unchanged. Do not pass a documenter handoff to `build_run.py prepare` as if it were a sealed builder task. Conflicts go back to the assigned content owner; the orchestrator performs branch operations, not product edits.

Persist `finalization.json` outside source before combining, with state `preparing`, the accepted code commit, documenter commits and handoffs, final workspace and branch, and required checks. Record exactly which commits the resulting candidate contains. Documentation changes after verification invalidate that verification.

## Verify and measure

Dispatch an integrator for direct-ref verification of the complete source. It returns command IDs, outputs, exit codes, the exact source commit, and any failures. This is the full required project check set, including the docs gate, performed on a source tree that stays unchanged during the checks. Compare current source and base with those recorded before accepting the evidence.

For optimization work, send that same verified source to a profiler with the existing baseline report and fixed benchmark specification. Remeasure after the combined correctness checks, under the same inputs, environment, command, and sampling method as the baseline. The orchestrator considers the distribution, regressions, and agreed target; a faster median by itself is not permission to change correctness. If a benchmark requires a new or changed harness, scope and review that harness work explicitly, then establish a comparable baseline before claiming improvement. Neither the profiler nor integrator repairs code to make its result pass.

Mark the finalization record `verified` only with the actual final commit and all applicable verification and measurement artifact paths. Stale source, missing evidence, failed checks, blocking review findings, or an unresolved performance goal mean unfinished work. Return that evidence to the relevant builder inside the current build; repeat the affected verification after changes.

## Deliver and resume

Return the verified local change or open/update the single final PR within the user's existing authorization. Use the recorded final branch and exact head; include only real issue-closing references. Inspect remote checks for that head before any authorized merge. A changed target base requires fresh combined verification before merging. Never substitute a direct push to `main` for the final PR.

On resume, compare actual source commits, branch, workspace, base, and PR with the finalization record. Reuse valid completed stages; a `preparing` record is not accepted evidence. Retain docs, source, and final workspaces until acceptance and any outstanding finalization or merge, or explicit abandonment. Recovery preserves the accepted integration ledger rather than moving it to disguise a stale final result.
