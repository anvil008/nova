# Local build runs

`skills/build/scripts/build_run.py` is the executable boundary between an
integrator's verification and an orchestrator's acceptance. It requires Python
3.10+, `tdd-guard`, and Jujutsu with `duplicate --onto` (tested with 0.45.1).

## State and inputs

Choose one durable directory outside the repository and all its workspaces.
Use that same directory when resuming; `mktemp` is appropriate for test runs,
not a milestone you need to recover after a reboot. The examples use
`NOVA_RUN` for that absolute path. Keep `plan.sidecar.json` unchanged after
approval: its canonical digest and the shared Jujutsu Git-store identity are
bound into the run. GitHub snapshots, handoffs, and logs also belong outside
the source tree.

Initialize once from the approved base:

```bash
python3 skills/build/scripts/build_run.py init plan.sidecar.json --state "$NOVA_RUN" --repo . --base 'trunk()'
python3 skills/build/scripts/build_run.py select plan.sidecar.json --state "$NOVA_RUN" --snapshot "$NOVA_RUN/issue-state.json"
```

For a run without GitHub issues, the sidecar may use `repo: null`. Select local
tasks with the same dependency and ownership checks:

```bash
python3 skills/build/scripts/build_run.py select plan.sidecar.json --state "$NOVA_RUN" --local
```

Local tasks carry `number: null`; their plan keys identify them. Accepted receipts
are the completion authority. The saved `trackingMode` is retained on resume;
do not switch an existing run between local and GitHub tracking. The snapshot
form above remains available when issue tracking is wanted. Reconciliation is
optional and rejects a sidecar without a real GitHub repository.

`init` creates `<planId>-integration`. It refuses to overwrite an existing
bookmark without its run ledger. Every source workspace in a round starts
from the current accepted integration commit. Resolve any speculative work
onto that base and reverify it before handing it to the integrator.

`sources.json` lists planner issue keys and absolute paths to builder handoffs:

```json
[
  {"key": "API", "handoff": "/absolute/run/API-handoff.json"},
  {"key": "UI", "handoff": "/absolute/run/UI-handoff.json"}
]
```

Each handoff follows `agents/handoff.md`, includes
`commitId`, and cites its current GREEN command ID. The helper reads fresh guard
status from the retained workspace. It checks the actual diff against
`changedFiles` and `ownershipHint`, allowing sealed acceptance-test files as
well. No two sources in the same round may change the same path. Include all
implementation and supplemental regression-test paths in the approved ownership
scope; an out-of-scope edit must be replanned rather than hidden from the handoff.

`checks.json` contains the project's required combined check set as argv arrays:

```json
[
  ["sh", "scripts/run-tests.sh"],
  ["sh", "scripts/lint.sh"]
]
```

These commands are examples: use the target project's actual documented commands.
The helper executes argv directly. Shell syntax requires an explicit shell entry.
`--timeout` sets a positive per-command limit in seconds; the default is 600.

## Prepare and accept

The integrator prepares in a new, unused candidate workspace:

```bash
python3 skills/build/scripts/build_run.py prepare plan.sidecar.json --state "$NOVA_RUN" --sources "$NOVA_RUN/sources.json" --checks "$NOVA_RUN/checks.json" --workspace /absolute/wave-candidate
```

Preparation duplicates the first source onto the accepted base, then each next
source onto the preceding candidate. It explicitly advances a candidate bookmark
after each addition. The original commits stay intact. Conflicts, failed checks,
changed source, or stale evidence produce a failed receipt without advancing the
accepted integration bookmark. Check records contain command IDs, argv, outputs,
exit codes, timestamps, and measured durations.

The orchestrator reviews the returned receipt, runtime evidence, and independent
review outcomes, then accepts its ID:

```bash
python3 skills/build/scripts/build_run.py accept plan.sidecar.json --state "$NOVA_RUN" --receipt <id>
python3 skills/build/scripts/build_run.py select plan.sidecar.json --state "$NOVA_RUN" --snapshot "$NOVA_RUN/issue-state.json"
```

Acceptance checks the candidate and sources again, advances the integration
bookmark, and persists local completion. `select` requires the bookmark to match
the ledger. Open issues with accepted receipts satisfy dependencies and are not
dispatched again. GitHub still closes issues only after the final PR merges.
Runtime correctness and review severity remain orchestrator decisions; the helper
does not turn a test pass into product approval.

## Recovery and cleanup

`status` reads the ledger, including prepared, failed, and interrupted rounds.
An exclusive run lock prevents concurrent preparation or acceptance. A process
exit releases the lock; there is no persistent lock to delete. A `preparing`
receipt after a crash is not accepted evidence. Retain it for diagnosis and
prepare again with a fresh candidate workspace.

If acceptance stopped after moving the bookmark but before writing the ledger,
repeat `accept` with the same receipt ID. It rechecks the candidate and original
sources and completes the write. Repeating an already accepted receipt is safe.
An unrelated bookmark movement or changed plan fails closed; restore the matching
ledger/ref from recovery evidence or start a new plan instead of editing success
fields by hand.

Keep source workspaces and candidate workspaces until acceptance. After the
receipt is accepted, the orchestrator may forget source workspaces with
`nova-ws forget <branch>` from the primary workspace. Preserve bookmarks and
commits. Inspect stranded workspaces before cleanup; `sweep --apply` is not a
recovery procedure for an unfinished round. Retain the run directory through the
final PR so the receipt and command outputs remain inspectable.

The ledger serializes integration operations. It does not launch agents or lease
writer slots; the orchestrator still owns dispatch, bounded retries, and cancellation.

## Final documentation and PR source

The issue ledger records accepted implementation waves. Final documentation is combined on a separate final branch so it cannot silently move the accepted integration bookmark.

1. The documenter returns an immutable docs commit and its retained workspace, changed files, and docs-check evidence. Verify those paths are docs-only and disjoint from code ownership. If the docs need updates against the accepted code, send that work back to the documenter before combining.
2. The orchestrator records the accepted integration commit and documenter commit in `<run>/finalization.json`, with state `preparing`, before creating a separate final workspace and branch. Use `nova-ws add feature/<planId>-final --base <accepted-commit>`. In that Jujutsu workspace combine the two pinned parents with `jj new <accepted-commit> <docs-commit> -m "Finalize code and documentation"`, then point its final bookmark at the resulting commit. Keep `<planId>-integration` unchanged. If there are conflicts, retain the workspace and delegate their repair to the owner of the affected files; never resolve product content in the orchestrator.
3. Dispatch an integrator to verify the already-combined final ref with all required project checks, including the docs gate. This uses the integrator's direct-ref procedure, not `build_run.py prepare`: a documenter handoff is not a sealed builder issue. Record the exact final source commit, accepted code commit, docs commit, check command IDs and artifact paths, and decision as `verified` only after successful checks. Source changes make this record stale.
4. Open or update the single final PR from that final branch, recording its URL and exact head in the finalization record. Check remote CI for that head before an authorized merge. Without a separate docs commit, the accepted integration branch may remain the final PR source. No special finalization record is needed for a docs-free build.
5. On resume, compare the retained final branch and both source commits with the record. Reuse existing workspaces and PRs; a `preparing` record or missing evidence is unfinished, and changed sources require renewed verification. Never reset or move the accepted integration bookmark to make a stale finalization appear accepted. Retain docs and final workspaces until merge or explicit abandonment.
