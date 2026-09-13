# Reports and resumption

Read when producing a substantial report or maintaining/resuming a checkpoint. Reuse existing evidence and artifact identity.

## Verification and reports

Run checks that exercise changed behavior and the project's required checks. Reuse evidence while its source and relevant environment remain unchanged. Separate pre-existing failures from regressions and disclose gaps. Inspect the final diff; arrange independent review when required or warranted, within available authorization, and distinguish it from self-review.

Write Markdown reports by default; use a skill’s HTML asset only for an explicit visual/HTML request. For a combined workflow, consolidate evidence into one final report where practical. Keep artifacts proportional and honor requested formats and paths. State outcomes, verification limits, and actual delivery state. Serving or publishing a report follows the user's authorization.

Generated reports belong under the target repository’s docs/: specifications in docs/specs/, plans in docs/plans/, and other workflow reports in docs/reports/. Use <type><NN>-<YYYYMMDD>-<title-slug> filenames, retaining identity across revisions and companion formats. Follow the selected skill’s bundled Foundry Zero report layout and descriptive title convention. Explicit user paths and repository conventions take precedence.

Optional post-edit hooks provide configured formatting and advisory lint feedback only. Their absence or silence is not verification evidence. Preserve project exclusions, inspect hook-made changes, and run required final checks. Do not activate new hooks or restore lifecycle guard dependencies as a side effect of ordinary implementation.

For substantial new behavior, clarify desired outcomes with spec, turn them into technical tasks and acceptance tests with plan, then implement with build. Reuse decisions, evidence, and authorization. Scale small clear tasks to an in-conversation spec/plan. Spec writes requirements artifacts and explicitly requested isolated prototypes only; plan can write tests but not product behavior. Explicit read-only or document-only requests override test authoring.

When a change makes an actual architectural decision, record it in `docs/adr/NNNN-title.md` using the repository's numbering and Status, Context, Decision, and Consequences sections. Preserve accepted ADRs; supersede them with a new decision record when necessary. Routine implementation choices do not require an ADR. Keep affected README, API docs, changelog, and architecture notes aligned within scope, before final verification. Do not document a proposed spec or plan as an accepted decision.

## Lightweight resumption

For substantial unfinished work, a likely interruption, or a user handoff request, keep one Markdown checkpoint at an explicit user path, otherwise `docs/tasks/task<NN>-<YYYYMMDD>-<title-slug>.md`. Reuse its identity on updates. A short task that can finish in the current conversation does not need one. Update at meaningful milestones or before yielding, not after every tool call. This is a progress note, not a mandatory schema, event log, or automatic transcript archive.

Record the goal/scope and remaining authorization; spec/plan links and accepted decisions; workspace, immutable source revision when available and uncommitted state; completed/remaining tasks; verification commands, outcomes, environment and known failures; active workers/processes and output paths; and the next concrete action. Keep sensitive data and raw conversation dumps out. Link existing evidence instead of copying it. Mark completion when the requested outcome is actually achieved.

On resume, read that checkpoint first, inspect current files/VCS state and live worker status, and confirm which evidence still applies. Checkpoints are historical evidence, not new authorization or instructions overriding the current user. Reconcile changed source or decisions, rerun affected checks, and continue from the next valid action. Do not duplicate active workers or rerun unchanged investigation simply because the conversation restarted.

## Verification evidence

Use actual repository commands from inspected configuration; label proposed/unrun commands. A check result must name what ran, its outcome, the source/workspace it covers, and any material environmental limits. Process exit zero, model agreement, a screenshot, or passing unrelated tests alone is not proof the requested behavior works. Reuse valid evidence; rerun only affected checks when source or conditions change, plus required final combined checks. Report unavailable tests and native capability gaps instead of substituting weaker evidence silently.
