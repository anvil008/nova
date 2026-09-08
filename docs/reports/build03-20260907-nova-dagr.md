# Nova Dagr

Implemented a standalone nova-dagr command with an independent Nova schema. It records milestones, tasks/dependencies, phase names, parent/subagent assignments, attempt history, progress notes, evidence and source revision references. Terminal and browser views read the same validated state.

The CLI serializes updates with a file lock, validates before atomic replacement, preserves settled attempts across retries, and prevents invalid task transitions and dependency cycles. Finished runs can be explicitly archived without overwriting prior history. Archive linking/removal is recoverable across an interruption, with directory syncs for durability. The browser API is read-only and exposes no general file server.

Bootstrap now installs the self-contained executable into ~/.local/bin or an explicit --bin-dir, using receipt ownership checks. All three native plugin packages also carry the executable and tool guide. Shared instructions explain when to track work, how to record actual phases/agents/evidence, and how to finish/archive while keeping Markdown documents authoritative for the narrative.

Validation: full Python suite, native mount-isolated bootstrap install/rerun and installed executable init/check, terminal use, desktop/mobile browser rendering, task selection/evidence, parent/subagent fixture, script-like text rendering without HTML interpretation, read-only API checks, and active-to-archive browser selection. Exact final test count and archive verification are recorded below after final checks.

This implementation run itself is tracked locally under .nova/. It uses one real main agent; no fictional subagents are recorded. A temporary browser fixture tested child-agent rendering. No Herdr source or schema was copied. No external library, model runtime, or new mandatory orchestration service was introduced.

Limitations: Linux/macOS locking only; agent activity is reported, not process monitoring; evidence tiers are producer claims with references; archive retains references rather than copies of linked documents. Browser serving has no authentication and defaults to localhost. Personal installations remain unchanged; bootstrap was exercised only in isolated mounts. Work remains local and unmerged.

Final verification: 42 tests passed. Package build and guide-sync check passed. Native bootstrap installed and reran successfully for all three harnesses, and the installed executable created and checked a run. This actual implementation run was finished and archived as `.nova/archive/nova-dagr-v1/run.json`, revision 22. `check --archive nova-dagr-v1` passed. Browser inspection confirmed the direct archive link selects the completed run and shows 4/4 tasks done without errors.

The authorized LAN viewer remains at http://10.0.20.100:8910/?run=nova-dagr-v1 (read-only). Its server is an explicitly launched local process, not a plugin-installed daemon. The original system guide remains on port 8902.
