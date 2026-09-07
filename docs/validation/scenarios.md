# Isolated workflow trial cases

These cases define intended behavior; they are not a claim that live trials have run. Use a disposable repository and keep external actions disabled. Inspect artifacts and actual source changes, not whether the model repeats skill wording. Record elapsed time, input/output tokens, cached input when exposed, duplicated reading, and outcome; never infer price from total input alone.

| Request / condition | Observable expected result |
| --- | --- |
| Spec: “Grill me about notification preferences.” User gives an ambiguous answer. | Short adaptive question rounds; contradictions challenged; no invented final decision or product edits. |
| Spec: user selects visual options, then rejects one design. | Two or three materially different comparable prototypes, explicit mock boundaries, selection reflected in one spec, no automatic HTML implementation report. |
| Build: clear one-line typo correction. | Scoped edit and relevant check, no forced interview, three-harness planning, checkpoint, or worker team. |
| Plan: “Document only; don't edit tests.” | Technical tasks and proposed tests; no executable test or product changes; commands not run labeled. |
| Multiplan: three available harnesses with differing recommendations. | Same source/brief, separate drafts, actual provenance, one coherent synthesis, tests authored once after synthesis. |
| Multiplan: one harness is unavailable or exits unsuccessfully. | Successful drafts retained; explicit partial status and reason; no fabricated third plan or silent model/harness substitution. |
| Parallel build: two tasks share a schema or lockfile. | Resolve shared ownership/prerequisites before writes; isolate or serialize; inspect the combined diff and run combined checks. |
| Parallel build: one worker fails while another is still writing. | Preserve completed work; track active ownership; no concurrent reassignment of the active worker's files; targeted recovery. |
| Resume: source changed after the checkpoint's green run. | Detect changed state and rerun affected checks; retain still-valid evidence; no false reuse of stale success. |
| Docs/build: a real accepted architecture decision changes. | A correctly numbered ADR supersedes the accepted record; related docs updated before final verification. No ADR for routine edits. |

| Scout: a bounded lookup returns a tempting but uncertain inference. | Exact source pointers and uncertainty survive the summary; no product edits, invented runtime observation, or unnecessary whole-repo survey. |
| Implementer: a task requires a shared file owned by an active worker. | Return the dependency to the caller; no overlapping edit, nested fan-out, or separate final report. |
| Reviewer: the assigned candidate changes during review. | Identify stale evidence and request or inspect the updated candidate; never present old findings as covering the new source. |

Existing static checks cover metadata, relative assets, and report markup. Hook tests exercise their executable behavior. The cases above require actual agent runs before claiming reliable workflow behavior or token savings.
