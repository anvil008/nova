# Development conventions

Carry the user's scope, decisions, and authorization through completion. Use one plan by default, proportional to the task. Skills supply expertise and the execution process; apply them in the current conversation without requiring a custom agent or separate planning phase.

## Version control and trunk

Use jj unless the user or repository explicitly requires plain Git. Inspect working-copy state and history first; preserve unrelated work. For an authorized adoption in an existing Git repository, use colocated initialization.

Trunk-based development applies across all harnesses and repositories:
- **Deployable trunk:** `main` (or the repository's configured default branch) is the single integration trunk and remains continuously deployable. Default branches are protected by the `main-trunk` ruleset: every change lands through a pull request, linear history is required, commits must be SSH-signed, and direct push, force-push, and branch deletion are blocked. Never push directly to trunk.
- **Short-lived changes:** Base independent work on a freshly fetched current trunk (`origin/main` or JJ `main@origin`). Stack only changes that genuinely depend on each other. Branches and task changes live under two days; name branches `<type>/<slug>` (`feat|fix|chore|docs|refactor|release`). Ship incomplete work behind flags, dark, or unreferenced — never on a long-lived branch.
- **One change, one PR:** Open PRs targeting trunk (`gh pr create --base main`). Squash-merge or rebase; delete the branch immediately on merge (`delete_branch_on_merge` is enabled).
- **Linear history:** Rebase onto trunk before opening a PR and update if stale. Never merge `main` into a branch.
- **Commit signing:** Sign every commit (SSH-signed); unsigned commits are rejected by repository rulesets.
- **Releases are tags:** Releases are annotated tags on `main` (`vYYYY.MM.DD[.N]`), never release branches. A published GitHub Release is the deploy trigger.
- **Housekeeping:** Stale branches are pruned regularly: branches merged into trunk and remote branches with no activity over 30 days.

Reuse a suitable workspace. Isolate independent work when another task or unrelated changes would interfere. Use noninteractive commands with explicit messages, avoid rewriting published history, and check conflicts after revision changes. Report the immutable tested commit when available; a jj change ID identifies evolving work. Rerun affected checks when rebasing or conflict resolution changes tested source.

Unless the user or repository specifies another location, create additional JJ workspaces and Git worktrees under the primary checkout's `.workspaces/<task>/` directory. Keep `/.workspaces/` ignored by version control and exclude it from recursive tooling that does not honor ignore rules. From a secondary workspace, resolve the primary checkout through JJ/Git repository metadata and use its absolute path; do not nest task workspaces inside other task workspaces. Existing workspaces may remain at their registered locations until their tasks finish.

For authorized publication, prefer a short-lived bookmark and PR into trunk. Direct-to-trunk delivery requires corresponding authorization and verification of the exact candidate. State whether work is local, published, or integrated; implementation authorization alone does not imply permission to merge or deploy.


## Parent-owned task integration

For both JJ workspaces and Git worktrees, a child reporting done means ready for integration. The parent must collect immutable result commits and verification evidence, review and test the combined candidate, and carry the authorized delivery path through integration without waiting for another user reminder. Read-only subagent work needs no merge. Workspaces belonging to other tasks are outside this obligation.

This user's standing preference authorizes local integration of verified task results. Preserve repository PR protections and explicit review-only, no-merge, or no-publish limits. When remote PR delivery is authorized, complete required checks/review and merge through that path, then fetch and synchronize local main. When only local delivery is authorized and repository rules permit it, integrate the verified candidate locally. Do not request the same authorization again. If a real review, permission, or CI boundary remains, finish all independent work and report awaiting review or blocked with the exact reason; do not call the task complete.

For JJ, integrate the child revisions into one tested candidate and advance the local main bookmark to the verified integrated revision. For Git, integrate the child branches into one tested candidate and fast-forward local main to the integrated commit. Account for squash/rebase commit mappings; record the resulting immutable main commit. Updating a bookmark or ref alone does not update the primary checkout's files: safely synchronize that checkout too. Never reset dirty files, move an active task off its revision, force-update divergent main, rewrite published history, or bypass protections. Report any primary-checkout synchronization blocked by unrelated work.

Before removing a task workspace, prove its work reached the integration target and preserve dirty, untracked and ignored files. A clean status, empty JJ child commit, stopped process, or successful subagent exit is not integration evidence. The final response states integrated (with main commit and local synchronization status), awaiting review, or blocked. A child handoff includes its workspace, immutable commit, checks, and unresolved issues; the parent owns the remaining work.

## Selective delegation

The optional helper roster is scout (bounded read-only discovery), implementer (one assigned task and verification), and reviewer (independent candidate assessment). Skills own workflows; helpers own assignments. Pass task-relevant skill guidance without asking helpers to repeat the whole workflow, spawn another team, or produce another overall report. Do not invoke a helper merely because it exists. Scout summaries include source pointers, constraints, and uncertainty; inspect consequential details without routinely repeating the entire search.

Keep small and tightly coupled work in the main conversation. When allowed by active harness policy, delegate useful bounded independent investigations or reviews whose benefit outweighs duplicated context and coordination. Ordinary tasks need no fixed team, mandatory specialist, or automatic phase handoff. Explicit multiplan requests use the three named harnesses; parallel build selects useful independent tasks. A skill must remain usable without custom agents.

Supply the worker's question, scope, relevant evidence, constraints, expected result, and relevant skill path or instructions. Do not assume it has loaded the main agent's skill. Keep write ownership separate and avoid repeating the same investigation. Resume the same worker for relevant follow-ups. The main conversation owns synthesis, overall verification, and completion. Use the optional scout helper when appropriate; its absence does not block direct investigation.

## Verification and reports

Run checks that exercise changed behavior and the project's required checks. Reuse evidence while its source and relevant environment remain unchanged. Separate pre-existing failures from regressions and disclose gaps. Inspect the final diff; arrange independent review when required or warranted, within available authorization, and distinguish it from self-review.

Write Markdown reports by default; use a skill’s HTML asset only for an explicit visual/HTML request. For a combined workflow, consolidate evidence into one final report where practical. Keep artifacts proportional and honor requested formats and paths. State outcomes, verification limits, and actual delivery state. Serving or publishing a report follows the user's authorization.

Generated reports belong under the target repository’s docs/: specifications in docs/specs/, plans in docs/plans/, and other workflow reports in docs/reports/. Use <type><NN>-<YYYYMMDD>-<title-slug> filenames, retaining identity across revisions and companion formats. Follow the selected skill’s bundled Foundry Zero report layout and descriptive title convention. Explicit user paths and repository conventions take precedence.

Optional post-edit hooks provide configured formatting and advisory lint feedback only. Their absence or silence is not verification evidence. Preserve project exclusions, inspect hook-made changes, and run required final checks. Do not activate new hooks or restore lifecycle guard dependencies as a side effect of ordinary implementation.

For substantial new behavior, clarify desired outcomes with spec, turn them into technical tasks and acceptance tests with plan, then implement with build. Reuse decisions, evidence, and authorization. Scale small clear tasks to an in-conversation spec/plan. Spec writes requirements artifacts and explicitly requested isolated prototypes only; plan can write tests but not product behavior. Explicit read-only or document-only requests override test authoring.

When a change makes an actual architectural decision, record it in `docs/adr/NNNN-title.md` using the repository's numbering and Status, Context, Decision, and Consequences sections. Preserve accepted ADRs; supersede them with a new decision record when necessary. Routine implementation choices do not require an ADR. Keep affected README, API docs, changelog, and architecture notes aligned within scope, before final verification. Do not document a proposed spec or plan as an accepted decision.

## Skill selection and execution

Select the smallest method matching the requested outcome. Spec is interactive discovery for unresolved intent; plan prepares one technical approach and acceptance tests; build implements. Multiplan is explicit-only, commissioning Agy, Claude, and Codex drafts and synthesizing one plan. Do not automatically load all stages for a small clear request. Debug, refactor, profile, and review retain their own focused workflows and carry existing repair/optimization authorization forward.

Offer prototype comparisons during spec when they can resolve uncertainty. Use native parallel builders for independent substantial tasks when authorized; honor an existing user preference. Options are not fixed extra phases. A prototype request authorizes that visual artifact, while other reports remain Markdown unless visual output is requested. Do not infer permission to execute multiplan simply because its skill was created or discussed.

## Lightweight resumption

For substantial unfinished work, a likely interruption, or a user handoff request, keep one Markdown checkpoint at an explicit user path, otherwise `docs/tasks/task<NN>-<YYYYMMDD>-<title-slug>.md`. Reuse its identity on updates. A short task that can finish in the current conversation does not need one. Update at meaningful milestones or before yielding, not after every tool call. This is a progress note, not a mandatory schema, event log, or automatic transcript archive.

Record the goal/scope and remaining authorization; spec/plan links and accepted decisions; workspace, immutable source revision when available and uncommitted state; completed/remaining tasks; verification commands, outcomes, environment and known failures; active workers/processes and output paths; and the next concrete action. Keep sensitive data and raw conversation dumps out. Link existing evidence instead of copying it. Mark completion when the requested outcome is actually achieved.

On resume, read that checkpoint first, inspect current files/VCS state and live worker status, and confirm which evidence still applies. Checkpoints are historical evidence, not new authorization or instructions overriding the current user. Reconcile changed source or decisions, rerun affected checks, and continue from the next valid action. Do not duplicate active workers or rerun unchanged investigation simply because the conversation restarted.

## Verification evidence

Use actual repository commands from inspected configuration; label proposed/unrun commands. A check result must name what ran, its outcome, the source/workspace it covers, and any material environmental limits. Process exit zero, model agreement, a screenshot, or passing unrelated tests alone is not proof the requested behavior works. Reuse valid evidence; rerun only affected checks when source or conditions change, plus required final combined checks. Report unavailable tests and native capability gaps instead of substituting weaker evidence silently.

## Large-file reads

Use the existing native scout for broad reads when a focused question can be answered without loading the source into the main context. Send paths and the question in fresh context; keep targeted reads direct for reasoning and edits. Read [bulk-read routing](read-routing.md) when a routing hook redirects a call or the task warrants bulk reading. Hooks perform local size checks only; this does not enable Flow tracking or add another builder. Respect native helper availability and use the documented direct fallback when delegation is unavailable.

## Live run tracking

Nova Flow is disabled by default for now. Do not create or maintain Flow tasks, bind sessions, report usage, or start viewers unless the user explicitly requests Flow. The following tracking guidance applies only after that request. Read [the tool guide](../tools/README.md) once when needed. Resolve `nova-flow` on PATH, or the bundled `../tools/nova-flow` relative to this instruction file; invoke the latter with Python 3.11+. Do not use the unrelated `dagr` command or its producer schema.

The main conversation maintains the current run at the workspace root's `.nova/run.json` (or an explicit shared store). Reuse an existing matching run after inspecting its current state; never reset another task's run. Record real milestones/tasks and dependencies, current workflow phases, actual parent/subagent assignments, reasons for blocks/retries, and evidence for results. Update at semantic milestones rather than after every tool call. Tool state does not authorize delegation or publication. Never infer task completion from a quiet or exited process, and never invent activity, model settings, evidence, or agents.

When attributable provider token counts are available, report them with `nova-flow usage` using a stable response/counter ID and source reference. Record the actual model and effort; do not estimate counts from context size or assign whole-session usage to one task. Missing telemetry stays unreported. Keep Markdown specs, plans, reports, and resumption notes as the durable explanation; link them and tested jj revisions from task evidence. Mark a run done only after the requested outcome and required checks are complete. Settle actual remaining agents, finish the run with a summary, and archive it when requested or before starting the next run in that store. Completed archives remain viewable. Tool unavailability is a reported visibility gap, not a reason to abandon the underlying task. Serving a viewer requires the user's hosting scope.

When Codex lifecycle hooks register a session, reuse that run and agent identity. Keep the main agent responsible for meaningful run titles, tasks, dependencies, milestones, evidence, and final outcomes. Before a registered session starts an assigned task attempt, bind its native session ID using `nova-flow session bind SESSION_ID --task TASK_ID`; rebind after retries or reassignment. Use `--task -` when no single task owns the work. Do not invent model, effort, or token numbers to fill the graph. Hook stop events indicate execution stopped, not task success. Session-only usage must stay separate from task totals. See [Codex tracking limits](../hooks/README.md#codex-run-lifecycle-and-usage).


## Task names and references

Most work needs tasks, not milestones. Give each task a short stable ID and a concrete title such as “Fix cache expiry”, “Compare storage options”, or “Verify retry handling”. Prefer an action and its object; omit generic labels such as “Implement the requested changes” and avoid repeating the phase or agent role in the title. Preserve IDs when revising titles. First attempts display the task ID; retries display an attempt suffix.

Create milestones only for real groupings requested or established by the work. Leave the milestone field empty for ordinary tasks; do not create a catch-all group. Attach existing GitHub issues through `task add/edit --issue https://github.com/OWNER/REPO/issues/NUMBER`. Only actual milestone or GitHub references get bracket labels in the graph. Linking an issue does not create or modify it on GitHub.

When reporting Flow work, use explicit task kinds for reviews, gates, and questions. Record a retry's causal attempt with `task retry ID --cause REVIEW.a1 --note ...` when known. Use `task progress ID --done N --total N --note ...` for measured progress within an attempt. These are reported facts: do not invent progress totals or infer completion from them. Re-review changed work; an earlier review applies to its recorded input attempt.

Flow repository runs: honor `NOVA_RUN_ID` when set. Independent harness sessions own separate runs; join an existing run only for assigned collaboration. Use the shared store discovered from JJ/Git metadata, not a guessed sibling path. Report final task evidence and usage before session exit. `nova-flow track --harness NAME -- COMMAND` registers portable lifecycle events and archives only after every participant closes and work is settled. Stop/idle is not closed. Agy/Claude launcher registration does not imply automatic token telemetry.


Maintain Flow task context before work: select the parent with `session context SESSION --parent ID`, add meaningful children with `task add ... --parent ID`, and bind the working task. Name any hook-created provisional task with `task rename`; hooks supply activity, while the agent reports actual progress and completion evidence. Parent membership is independent of execution prerequisites. Keep related follow-up work under the selected parent; switch it when scope changes.
