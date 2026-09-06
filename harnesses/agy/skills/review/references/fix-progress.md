# Review progress inside build

`loop_state.py` records verified findings and orchestration decisions for an already-authorized build. It neither dispatches agents nor authorizes fixes, creates branches, merges, or publishes anything. Store its state and input reports in the durable run directory outside source workspaces.

```bash
python3 -B skills/review/scripts/loop_state.py --state "$WORKCELL_RUN/review-progress.json" init --branch <assigned-branch>
python3 -B skills/review/scripts/loop_state.py --state "$WORKCELL_RUN/review-progress.json" record "$WORKCELL_RUN/review.json"
python3 -B skills/review/scripts/loop_state.py --state "$WORKCELL_RUN/review-progress.json" status
```

There is no default iteration cap. Supply `--max-iterations N` only for an explicit user limit; an existing numeric limit is preserved on resume. `--min-severity` selects the threshold for this progress record, defaulting to `high`. Lower-severity findings remain visible and can still be selected work; `converged` means the threshold was met, not that the user's whole task or PR is complete.

The helper fingerprints `(file, claim)` so line movement or a changed collection order does not look like progress. Repeated unresolved findings produce `progress: unchanged` and `repeatedCount`. They do not automatically stop at a fixed number of passes. The orchestrator examines the evidence, chooses another approach when useful, or records stalled work with its reason:

```bash
python3 -B skills/review/scripts/loop_state.py --state "$WORKCELL_RUN/review-progress.json" decide --status stalled --reason "The remaining finding needs a compatibility decision"
```

After the missing decision or evidence arrives, `decide --status running --reason <decision>` resumes the same record. `abandoned` records explicit abandonment. Reaching an explicit user limit produces `exhausted`; a decision cannot bypass it. Retain the source evidence and surface unfinished findings to the user. No helper status substitutes for build's sealed tests, source-bound verification, review, and completion record.
