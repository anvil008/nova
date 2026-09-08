# Nova Flow

`nova-flow` is an independent Nova tool for recording and viewing a run. It has its own versioned JSON format and no dependency on Herdr or its Flow plugin. Python 3.11+ on Linux or macOS is sufficient; there are no third-party runtime packages.

The tool records explicit updates. It does not launch agents, execute recorded commands, monitor processes, infer success from activity, or enforce a prescribed spec/plan/build sequence. Phases, task kinds of work, roles, harnesses, and models are descriptive strings.

## Start and inspect a run

After bootstrap installs the command in `~/.local/bin/` (or `--bin-dir`):

```sh
nova-flow init 'Add CSV export'
nova-flow milestone discovery 'Define export behavior'
nova-flow milestone delivery 'Implement and verify'
nova-flow task add requirements 'Confirm export fields' --milestone discovery --phase spec
nova-flow task add implementation 'Implement CSV export' --milestone delivery --phase build --after requirements
nova-flow view
nova-flow view --watch
nova-flow serve
```

Before installation, use `python3 /absolute/path/to/tools/nova-flow`. The complete executable also ships inside each plugin under `tools/nova-flow`.

The default store is `.nova/` relative to the current directory. Invoke from the workspace root, or pass `--dir /absolute/path/to/store` before the subcommand. Nova's repository already ignores `.nova/`; add that exclusion during target repo setup when appropriate.

```text
.nova/
  run.json                     Current run, active or finished
  .lock                        Writer coordination
  archive/<run-id>/run.json     Finished snapshot, never overwritten by this tool
```

One store has one current run. Use another `--dir` for simultaneous independent runs. `init` refuses an existing run; it never quietly resets work.

Task and milestone IDs are stable, explicit IDs supplied by the producer (for example `T1` and `M1`), unique within their respective collections. Attempts are numbered within each task. Omitting `task add --milestone` creates an ordinary task with no group label; it does not invent a milestone. A pending task can later be grouped with `task edit T1 --milestone M1`. Unknown named milestones and dependencies are rejected. Agents can report run-level activity before any tasks exist; unassigned working/waiting agents remain visible below the terminal graph.

## Phases and agents

```sh
nova-flow phase spec
nova-flow agent main --role main --harness codex --phase spec --activity 'Clarifying error cases'
nova-flow agent scout-1 --parent main --role scout --harness claude --phase spec --activity 'Finding the existing export contract'
nova-flow task set requirements working --agent scout-1
```

Optional agent fields: `--model`, `--effort`, `--state` (idle, working, waiting, done, failed), `--task`, and `--activity`. Use actual observed settings; leave unknown models/effort blank. `--parent -` and `--task -` clear those associations. A phase can be any workflow name, including spec, plan, multiplan, build, review, or a project-specific activity. Each agent's phase is independent of the run's phase.

Register an agent before assigning it via a task update. Assignment does not spawn a process. Parent links represent actual delegation; do not create fictional agents just to fill a diagram. Agents may work in different phases at once. Last-update timestamps are reports, not live process health checks.

## Refine the plan

Use `task edit TASK --title "New title" --phase plan --after DEPENDENCY` for pending tasks. `--after` replaces the dependency list; `--clear-deps` removes it. Only pending work can be replanned. Use `task note TASK "Current finding"` for progress notes on unfinished work; this records an event without starting another attempt.

## Progress, results, and retries

```sh
nova-flow task set requirements blocked --note 'Waiting for the required CSV columns'
nova-flow task set requirements working
nova-flow task set requirements done --evidence 'Confirmed fields in docs/specs/spec01-20260907-csv-export.md'
nova-flow phase build
nova-flow task set implementation working --agent main
nova-flow task set implementation failed --note 'Unicode export test failed'
nova-flow task retry implementation --note 'Fix quoting for non-ASCII values' --agent main
nova-flow task set implementation done --evidence 'python3 -m unittest: 12 passed; docs/reports/build01-20260907-csv-export.md' --verified --source-revision abc123
```

Task states are pending, working, blocked, done, failed, and canceled. Starting or completing a task requires its dependencies to be done. Cancellation and blocked/failed states need a reason. A completed attempt needs an evidence reference or result; `--verified` is the producer's explicit assertion that a real check supports it, not an automatic validation of that check. Without it evidence is labeled reported. The tool never runs evidence text.

Retries append an attempt and preserve previous attempts. Reopening a dependency is refused while a downstream task has already started; represent the follow-up as new work after reviewing its downstream impact. Task settlement releases assigned agents to idle. Milestone counts are derived from their tasks; canceled tasks remain visible and are not counted as successful completions.

## Models and token usage

Task assignment with `task set TASK working --agent AGENT` saves the agent's harness, model, and effort on that attempt, so later agent changes do not erase its runtime identity. Report actual provider usage explicitly:

```bash
nova-flow usage implement --record response-123 --agent builder \
  --source "provider response response-123" \
  --input-tokens 12000 --output-tokens 800 --cache-read-tokens 9000
```

Use a distinct record ID per provider response or cumulative task/worker counter. Repeating a record updates supplied fields rather than adding the counts again. Never mix cumulative snapshots and individual responses for the same consumption. A record belongs to one attempt; retries retain earlier records and need new IDs. Report usage before finishing the run. `--harness`, `--model`, and `--effort` can override the registered agent's values for a response.

Input/output are the provider's primary counters; cache-read, cache-write, and reasoning are separately labeled breakdowns and are never added into an overall total. Missing fields mean **not reported**, not zero. Task totals sum each field across records and attempts; **partial** means some records lack that field. The display includes per-record agent/model/source attribution. It cannot detect unreported requests or shared-session consumption: supply only counts attributable to this task. Codex hooks can collect session metadata as described below; other harnesses currently require explicit reporting. There is no cost estimate.

## Finish and archive

```sh
nova-flow agent main --state done --activity 'Implementation and combined checks complete'
nova-flow finish --note 'CSV export implemented and verified'
nova-flow archive
nova-flow list
nova-flow view --archive RUN_ID
nova-flow check --archive RUN_ID
```

`finish` defaults to done and requires all tasks done/canceled and no working/waiting agents. Use `--state failed` or `--state canceled` to record another terminal outcome with a summary. Working tasks still need settlement. Finished runs cannot be mutated. Archive is explicit and only accepts a terminal run; it atomically links the complete snapshot into an exclusive archive location before removing the current file. An interruption between those steps can safely be retried. An existing different archive is never overwritten. Archived IDs cannot be reused by init.

The archive stores the run and its references, not copies of linked reports or source files. Keep durable documents in the repository's docs directories and record immutable tested revisions when available. Filesystem owners can still edit files manually; immutability here is the command's behavior, not tamper-proof storage.

## Interactive terminal

Run `nova-flow` (or `nova-flow view`) from the project root to open the live terminal UI. It polls `.nova/run.json` every two seconds. When no active run exists, the terminal initially opens the latest archive and labels it ARCHIVE. Use [ / ] to switch back to the active slot or browse other archives. Use `view --archive RUN_ID` to open a completed run directly. In a source checkout, use `./tools/nova-flow` until installed.

The terminal shows a compact branching task graph, right-aligned model/effort, input/output token, and status columns, and a bordered detail panel below. Green marks completion, cyan working tasks, amber blocks, and red failures. A diamond marks reported (◇) or verified (◆) completion evidence. For an ordinary task, the first dependency in the same milestone supplies the compact tree connector; all dependencies remain explicit. A declared gate has its own join row. Use arrow keys to select tasks, **Tab** to switch between task evidence, agents, and events, **Page Up / Page Down** to scroll the panel, **[ / ]** to browse active and archived runs, **r** to refresh, and **q** to quit. Terminal graph rows show only the model on the right; effort and token totals stay in the details panel. Cyan-to-mint-to-violet branch colors use the terminal’s 256-color palette, with a basic-color fallback; status symbols retain their meaning. A dash means unknown, and an asterisk means a partial total across reported usage records. Agent activity is explicitly reported, not process monitoring.

The UI uses Python's standard `curses` module and restores terminal settings on exit. `view --plain` prints a snapshot; `view --plain --watch` repeats it. Redirected output and `--json` stay noninteractive.

## Live viewer

`nova-flow serve` starts a read-only browser view on `http://127.0.0.1:8910`. The console-style view shows a top-down task graph with colored milestone lanes, dependency splits and joins, attempt evidence, an event log, and the parent/subagent roster. Rows follow dependency order; vertical proximity alone does not mean dependency. Select a task by clicking its row or pressing j/k or the arrow keys. It polls every two seconds. Use the run selector for archived snapshots, or `/?run=RUN_ID` for a direct archive link.

To explicitly expose it on a LAN interface, use `serve --host <LAN-IP> --port 8910`. It serves only the viewer and validated run data, not arbitrary local files. There is no authentication; choose a bind address appropriate for who may read task titles and evidence. No external assets, analytics, or remote scripts are loaded. Ctrl-C stops the server.

## Format and correctness

Schema marker: `"nova_dagr": 1`. A run has `run`, `revision`, `updated_at`, `milestones`, `tasks`, `agents`, and `events`. Tasks reference one milestone and zero or more task dependencies; agents can reference a parent agent and task. Attempts preserve start/end times, retry reasons, evidence, and tested source revision. Events have consecutive sequence numbers and timestamps.

`nova-flow check` validates the current file; `view --json` prints it. Mutations lock the store, read and validate the existing file, apply one semantic update, validate the candidate, and atomically replace run.json. Concurrent CLI updates are serialized. Failed validation leaves the live file intact. The tool does not import another Flow schema or silently migrate future schema versions.

The main conversation should own semantic updates, incorporating helper returns at milestones. A lock prevents lost writes; it does not resolve contradictory human or agent decisions.

### Codex session integration

The bundled Codex plugin hooks register agent sessions and collect available model, effort, and cumulative usage metadata into the same `.nova/run.json`. See [hook setup and limits](../hooks/README.md#codex-run-lifecycle-and-usage). This is independent of terminal/browser rendering. No personal plugin installation is implied by building bundles.

`nova-flow session bind SESSION_ID --task TASK_ID` binds a registered native session to the currently started attempt. Use `--task -` to detach. Bind before the relevant model turn; token intervals crossing an uncertain boundary stay session-only in the agent panel. The initial session history is never retroactively charged to a task. Models and effort are observed facts, never inferred from helper profile defaults.

## Attempts, navigation, and diagnostics

Graph rows use stable display IDs such as `T1.a1` and `T1.a2`; CLI mutations still use task ID `T1`. Each attempt shows its own model, usage, elapsed duration, and outcome. Retried failures stay visible. Explicit gate rows (`⋈`) list inputs and their current blockers. Legacy tasks without a kind retain the old multi-input join display. Selecting a browser row highlights its visible incoming/outgoing edges. Folded or filtered inputs remain named in task details.

In the terminal, search is removed; `h` toggles hiding settled tasks and `d` opens diagnostics. Task/attempt selection is retained by ID across refreshes. Search matches task IDs/titles, milestone IDs, worker IDs, and recorded usage models. Folding keeps unfinished, blocked, and failed tasks visible; the footer counts settled tasks. Browser search and the fold checkbox provide the equivalent controls. `Tab` also cycles the terminal diagnostics panel.

Elapsed duration freezes at an attempt's end. Last task progress measures semantic task events; report age measures stored/observed updates. Neither silence nor a large age proves a process died. Diagnostics shows the selected store, active/archive status, observed sessions, model/effort, binding, transcript cursor, and warnings. It explicitly does not infer installation status. Use `nova-flow doctor` (optionally `--archive ID` or `--json`) even when no active run exists.


## Task labels

Use short concrete titles: `cache` / “Fix cache expiry”, `storage` / “Compare storage options”. Ordinary rows show only the ID and title; no “ungrouped” placeholder appears. First attempts display the task ID, retries retain `.a2` and later suffixes. Actual milestone and GitHub references appear in brackets, for example `[M1 · #42]`. Add or edit a pending task's issue reference with `--issue https://github.com/OWNER/REPO/issues/42`; the viewer links to that URL. No GitHub writes occur.

The viewer follows the working task by default. Manual terminal navigation disables following; press `f` to enable it again. The browser has a “Follow working task” checkbox; clicking a row switches to manual inspection.

## Explicit graph facts

Use `--kind review`, `--kind gate`, or `--kind question` when adding tasks. Ordinary tasks default to `task`; custom kinds are allowed. Gates require inputs and stay at the group boundary. Multiple dependencies alone do not make new tasks gates. A pending question with satisfied prerequisites displays “needs answer”; it still needs explicit settlement and evidence.

```sh
nova-flow task add review 'Review the implementation' --kind review --after build
# After the review is settled, record its finding as the retry cause:
nova-flow task retry build --cause review.a1 --note 'Address the review finding'
nova-flow task progress build --done 2 --total 5 --note 'Checking edge cases'
nova-flow task add verify 'Verify combined changes' --kind gate --after build --after review
```

Causes reference existing, earlier settled attempts. Starting an attempt records the exact completed prerequisite attempts. Browser edges follow those references; later retries do not rewrite the review’s inputs. Retry causes appear in both views, with dashed browser edges. Terminal indentation remains a compact task dependency projection; the explicit cause label is authoritative. A review cause can reopen its prerequisite; other already-started downstream tasks still prevent reopening. A completed review remains evidence about its recorded inputs, not approval of a later retry: explicitly retry the review after the fix when needed.

Progress belongs to one attempt, permits `0 <= done <= total` with a positive total, and never marks a task done automatically. Retries start with no progress count. Completion continues to require evidence.

Reads and writes are bounded to 16 MiB per run, 4,096 graph items (milestones, tasks, attempts, and agents), and 32,768 events. Over-limit or invalid updates leave the existing file intact. Archive settled runs before approaching these bounds; rejected files are not silently truncated. Cycle validation uses an iterative traversal, including attempt inputs and causes.

Task details default to compact token totals. Press `u` in the terminal to show or hide individual usage records; browser records are collapsed under each attempt. At narrower browser widths, model and token totals appear beneath the task title. Independent tasks remain separate graph nodes until dependencies are declared.

## Repository sessions and workspaces

By default, Flow resolves JJ workspace repository pointers and Git's common directory to one project `.nova` store. Separate clones remain separate even when their remote URL matches. Session runs live under `.nova/runs/RUN_ID/run.json`. Each run archives beside its store under `archive/RUN_ID/run.json`. `--dir` explicitly overrides discovery.

For older stores, run `./tools/nova-flow --dir /path/to/project/.nova migrate` from this source checkout. This moves the legacy root `run.json` and root `archive/*/run.json` records into their corresponding `runs/RUN_ID/` stores without changing JSON contents. Existing destination records are never overwritten. A successful repeat does nothing. Session hooks find the relocated records by session identity; when multiple runs exist, use `--run RUN_ID` for task mutations. Legacy records remain readable until explicitly migrated. This command does not change task grouping or run ownership.

The default viewer combines active runs. The browser run selector and terminal `[` / `]` select individual active or archived runs. Combined rows namespace IDs for display; use original task IDs with `--run RUN_ID` for mutations. When multiple runs exist, select the run explicitly or use the launcher's `NOVA_RUN_ID` environment. The legacy root run remains the default for unscoped commands when present.

Launch independent sessions from any workspace:

```sh
nova-flow track --harness codex -- codex
nova-flow track --harness agy -- agy
nova-flow track --harness claude -- claude
```

Use your actual installed harness executable and arguments after `--`. To collaborate on an existing run:

```sh
nova-flow --run RUN_ID track --harness agy -- agy
```

The launcher supplies `NOVA_RUN_ID` and `NOVA_SESSION_ID` to its child. It registers the workspace and observes process exit. Native Codex hooks join that run and collect the available telemetry; Agy/Claude receive lifecycle tracking through the launcher, but token reporting still requires their own adapter or explicit `usage` records. No model/effort is guessed from the command name.

Portable integrations may call `lifecycle start|end --harness NAME --session ID` and optionally `--run RUN_ID` to join. Harness and session together define identity. Only report `end` after final telemetry has been consumed. A normal reply/Stop event is not a session exit.

Once all participating sessions close, settled tasks cause automatic finish and archive. Unfinished tasks retain an active run with lifecycle `interrupted`; starting the same session identity resumes it. Other runs are unaffected. The launcher does not infer task outcomes from an exit code. Killing the launcher without cleanup can leave an unconfirmed session: report its confirmed end with `lifecycle end`; silence alone is not treated as exit. Existing sessions started before this launcher do not acquire process-exit tracking retroactively.

The command is now `nova-flow`. Existing `.nova` stores and the version-1 schema marker remain readable; no archive migration is required.

The terminal footer shows only arrow navigation, Tab for panels, brackets for runs, and quit. j/k navigation is removed. Page Up / Page Down scroll long details; the scroll hint appears only when needed. Browser search remains available.


## Task context and continuous reporting

Use `task add ID TITLE --parent PARENT_ID` to group work; parenthood never creates a prerequisite. `task parent ID PARENT_ID` regroups existing tasks without changing attempt history (`-` clears it). `session context SESSION --parent PARENT_ID` remembers the current scope. `task rename ID TITLE` names provisional work.

Tool/invocation hooks update a bound task's `last_activity`, throttled to five seconds for identical activity. These are activity facts, separate from semantic progress. If work arrives without a valid binding, the hook creates and binds one provisional child under the session's parent context (or a default scope). It reuses that child until settled and asks the agent to name it. Helpers inherit their parent's assigned task or scope when parent identity is supplied by the harness. Hooks do not infer completion or percentages. CLI updates containing nova-flow are excluded from fallback task creation.

Terminal: `h` hides/shows done and canceled tasks; the footer displays the shortcut. Parent branches group related tasks, while explicit dependencies remain in task details and browser edges. The Codex Interrupt handler requests its supported three-second timeout.

Group tasks (`--kind group`) are containers. Their displayed progress derives from non-group descendants, including nested groups. They have no model assignment, are excluded from task totals, and do not prevent completion or archival. Actual unfinished tasks and open sessions still apply.

Stable references separate identity from titles: groups display `G01`, tasks `T01`, and retries `T01.a2`. References are allocated once under a repository-wide lock in `.nova/references/index.json`; preserve this registry with run history. Existing internal IDs and dependency links remain unchanged. Task commands accept the short references within the selected `--run`. The combined viewer hides its internal namespace and displays run context once above tasks. Use `nova-flow references` to backfill existing run records and archives; new writes assign references automatically. Numbers may have gaps and never reflect sort order.
