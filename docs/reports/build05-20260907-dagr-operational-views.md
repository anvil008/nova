# Build 05 — Dagr operational views

Implemented the five gaps prioritized in the Herdr comparison, using Workcell's own state and renderer:

- Stable attempt rows (`T1.a1`, `T1.a2`) retain failed outcomes, retry reasons, models and per-attempt usage. New settled attempts record their outcome note; older runs can derive it from matching task events.
- Multi-input tasks render as join boundaries and identify unmet dependencies. Browser selection highlights visible incoming/outgoing edges; full prerequisite IDs remain in details when rows are filtered or folded.
- Attempt duration freezes on completion. Semantic task progress age is separate from stored report age. Neither is treated as evidence that a process died.
- Search and settled-task folding work in the terminal and browser. Unfinished/blocked/failed tasks remain visible when settled work is folded. Terminal selection uses stable row IDs across refreshes.
- Diagnostics explain the selected store/run, observed sessions, model/effort, task binding, transcript cursor, and warnings. `workcell-dagr doctor` works with missing run data and does not claim to know personal hook installation status.

Terminal controls: `/` search, Enter accepts search, `z` folds settled tasks, `d` opens diagnostics, `j/k` select, `J/K` scroll details, Tab cycles panels. Browser controls are labeled above the graph and below the main content.

## Verification

`python3 -m unittest discover -s tests`: 54 tests passed. After a final model-search correction, `python3 -m unittest discover -s tests -p test_dagr_views.py`: all four focused tests passed. Plugin bundles rebuilt.

The new persistent tests cover attempt identity, failed history, blocker IDs, search/folding, unknown telemetry, settled duration, real PTY interaction, resize, and terminal-mode restoration. Browser fixture checks confirmed both retry rows survive search, only settled tasks disappear on fold, and a join still names its hidden prerequisite while highlighting the visible edge. No browser JavaScript errors were reported during the initial view check.

The LAN terminal preview is a capture of an explicitly labeled fixture, not real task history. The primary LAN viewer continues to show this project's actual run. Changes remain local; no personal installation or publication was performed.
