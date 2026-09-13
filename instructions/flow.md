# Optional Nova Flow tracking

Read only when the user explicitly requests Flow.

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
