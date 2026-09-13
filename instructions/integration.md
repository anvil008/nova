# Integration and publication

Read for revision changes, workspace integration, publication, releases, or cleanup. Reuse within the conversation.

## Version control and trunk

Use jj unless the user or repository explicitly requires plain Git. Inspect working-copy state and history first; preserve unrelated work. For an authorized adoption in an existing Git repository, use colocated initialization.

Trunk-based development applies across all harnesses and repositories:
- **Deployable trunk:** `main` (or the repository's configured default branch) is the single integration trunk and remains continuously deployable. Default branches are protected by the `main-trunk` ruleset: every remote change lands through a pull request, linear history is required, commits must be SSH-signed, and direct push, force-push, and branch deletion are blocked. Never push directly to trunk.
- **Short-lived changes:** Base independent work on verified local main after fetching and reconciling remote updates; preserve local-only integrated work. Stack only changes that genuinely depend on each other. Branches and task changes live under two days; name branches `<type>/<slug>` (`feat|fix|chore|docs|refactor|release`). Ship incomplete work behind flags, dark, or unreferenced — never on a long-lived branch.
- **One publication, one PR:** Keep intermediate workspace results local. Publish accumulated verified local-main work through one integration bookmark and PR to remote main. Verify branch deletion after merge; explicitly clean superseded PR branches after proving integration.
- **Linear history:** Rebase onto trunk before opening a PR and update if stale. Never merge `main` into a branch.
- **Commit signing:** Sign every commit (SSH-signed); unsigned commits are rejected by repository rulesets.
- **Releases are tags:** Releases are annotated tags on `main` (`vYYYY.MM.DD[.N]`), never release branches. A published GitHub Release is the deploy trigger.
- **Housekeeping:** Delete integrated unused remote branches; investigate stale branches without deleting unverified work based on age alone.

Reuse a suitable workspace. Isolate independent work when another task or unrelated changes would interfere. Use noninteractive commands with explicit messages, avoid rewriting published history, and check conflicts after revision changes. Report the immutable tested commit when available; a jj change ID identifies evolving work. Rerun affected checks when rebasing or conflict resolution changes tested source.

Unless the user or repository specifies another location, create additional JJ workspaces and Git worktrees under the primary checkout's `.workspaces/<task>/` directory. Keep `/.workspaces/` ignored by version control and exclude it from recursive tooling that does not honor ignore rules. From a secondary workspace, resolve the primary checkout through JJ/Git repository metadata and use its absolute path; do not nest task workspaces inside other task workspaces. Existing workspaces may remain at their registered locations until their tasks finish.

Verified results enter local main promptly. Remote publication uses one short-lived integration bookmark and PR; never push main directly. State whether work is integrated locally, pending publication, or merged remotely.


## Parent-owned task integration

Local integration and GitHub publication are separate steps. As soon as a task-owned JJ workspace or Git worktree result is ready, the parent collects its immutable commit and verification evidence, checks the combined candidate, and integrates it into local `main`. Do not wait for the whole batch or a user reminder. Read-only results need no merge; unfinished, failed, unrelated, and actively edited work must not be swept into main.

Keep intermediate JJ changes local and normally unbookmarked. Children commit in their assigned workspace and return the immutable commit, change ID, checks, and remaining issues; they do not push, open PRs, or move main. The parent serializes integration into local main, resolves conflicts, and runs the relevant combined checks. Git worktrees follow the same local handoff policy. Local main may be ahead of `main@origin`: the remote PR requirement applies to publication, not verified local integration.

Start independent work from current verified local main after fetching and reconciling remote updates. Preserve accumulated local-only work; never replace local main blindly with `main@origin`. Safely synchronize the primary checkout after integration. Moving a bookmark alone does not update its files. Preserve dirty files and active tasks, and report an exact synchronization blocker if the checkout cannot be moved safely.

When publication is authorized, gather the accumulated verified local-main work into one integration bookmark (`<type>/<slug>`) and one PR targeting remote main (`gh pr create --base main`). Reuse an existing publication PR for that batch; no child, intermediate, or per-workspace PRs. Fetch and reconcile with current remote main before publication, verify the resulting candidate, and push only the integration bookmark. Never push main directly or bypass remote protections. An explicit local-only, review-only, no-merge, or no-publish request still applies.

After the PR merges, record the immutable remote main commit and the mapping from the tested local candidate. A squash/rebase merge changes commit identity: prove equivalence, preserve any local commits added since publication, reconcile local main, and synchronize the primary checkout. Do not rewrite published history or discard newer local work. If equivalence or a safe reconciliation cannot be established, retain the revisions and report the blocker.

Branch cleanup is part of delivery. Verify the merged PR's remote head branch was deleted. For a superseded PR, first prove its work reached main and record the replacement PR or commit; then close it and delete its head only if no active work or other open PR needs it. Age or a closed PR alone is not proof of integration. Before reporting completion, inspect remaining remote branches: each must belong to active work, or be retained with a concrete unresolved reason. Preserve main and protected branches. Prune stale remote references after deletion.

Before removing a workspace, prove its result reached local main (accounting for squash/rebase mappings) and preserve dirty, untracked, and ignored files. A clean status, empty child commit, stopped process, or successful subagent exit is not integration evidence. Final status distinguishes integrated locally (pending publication when applicable), published/merged (with main commit and synchronization status), or blocked. Existing authorization persists; do not ask the user to repeat it.
