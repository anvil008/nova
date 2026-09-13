# Global development instructions

## Trunk-based development and version control

Use jj for version control unless the user or repository explicitly requires plain Git. Inspect working-copy state and history before changing revisions. In an existing Git repository adopting jj, use colocated initialization and preserve existing work.

Trunk-based development applies across all repositories:
- **Deployable trunk:** `main` (or the repository's configured default branch) is the single integration trunk and remains continuously deployable. Default branches are protected by the `main-trunk` ruleset: every change lands through a pull request, linear history is required, commits must be SSH-signed, and direct push, force-push, and branch deletion are blocked. Never push directly to trunk.
- **Short-lived changes:** Base independent work on a freshly fetched current trunk (`origin/main` or JJ `main@origin`). Stack only changes that genuinely depend on each other. Branches and task changes live under two days; name branches `<type>/<slug>` (`feat|fix|chore|docs|refactor|release`). Ship incomplete work behind flags, dark, or unreferenced — never on a long-lived branch.
- **One change, one PR:** Open PRs targeting trunk (`gh pr create --base main`). Squash-merge or rebase; delete the branch immediately on merge (`delete_branch_on_merge` is enabled).
- **Linear history:** Rebase onto trunk before opening a PR and update if stale. Never merge `main` into a branch.
- **Commit signing:** Sign every commit (SSH-signed); unsigned commits are rejected by repository rulesets.
- **Releases are tags:** Releases are annotated tags on `main` (`vYYYY.MM.DD[.N]`), never release branches. A published GitHub Release is the deploy trigger.
- **Housekeeping:** Stale branches are pruned regularly: branches merged into trunk and remote branches with no activity over 30 days.

## File placement and task cleanup

- Do not create task scripts, SQL, package manifests, binaries, or reports directly in `/home/anvil` unless the user explicitly requests that location. Normal application configuration belongs in its standard configuration directory.
- Keep project changes in the repository or an isolated task workspace. Set an explicit working directory before running commands that create files.
- Put temporary task files in `~/.cache/agent-work/<project>/<task>/`. Use disk-backed home storage, not `/tmp`, for large builds; reuse established build caches where appropriate.
- Install dependencies inside the project or task workspace. Never initialize npm, Go, or Python projects in home.
- Before finishing, account for files created outside the repository. Remove disposable files created by this task once they are no longer needed, and report retained artifacts and their purpose.
- Never delete pre-existing files as part of task cleanup. Preserve work needed for review or resumption.

## Workspace placement

Create additional JJ workspaces and Git worktrees under the primary checkout's `.workspaces/<task>/`, unless the user or repository explicitly specifies another location. Keep `/.workspaces/` ignored. From a secondary workspace, resolve the primary checkout and use its absolute path; do not nest task workspaces.

## Parent-owned task integration

For both JJ workspaces and Git worktrees, a child reporting done means ready for integration. The parent must collect immutable result commits and verification evidence, review and test the combined candidate, and carry the authorized delivery path through integration without waiting for another user reminder. Read-only subagent work needs no merge. Workspaces belonging to other tasks are outside this obligation.

This user's standing preference authorizes local integration of verified task results. Preserve repository PR protections and explicit review-only, no-merge, or no-publish limits. When remote PR delivery is authorized, complete required checks/review and merge through that path, then fetch and synchronize local main. When only local delivery is authorized and repository rules permit it, integrate the verified candidate locally. Do not request the same authorization again. If a real review, permission, or CI boundary remains, finish all independent work and report awaiting review or blocked with the exact reason; do not call the task complete.

For JJ, integrate the child revisions into one tested candidate and advance the local main bookmark to the verified integrated revision. For Git, integrate the child branches into one tested candidate and fast-forward local main to the integrated commit. Account for squash/rebase commit mappings; record the resulting immutable main commit. Updating a bookmark or ref alone does not update the primary checkout's files: safely synchronize that checkout too. Never reset dirty files, move an active task off its revision, force-update divergent main, rewrite published history, or bypass protections. Report any primary-checkout synchronization blocked by unrelated work.

Before removing a task workspace, prove its work reached the integration target and preserve dirty, untracked and ignored files. A clean status, empty JJ child commit, stopped process, or successful subagent exit is not integration evidence. The final response states integrated (with main commit and local synchronization status), awaiting review, or blocked. A child handoff includes its workspace, immutable commit, checks, and unresolved issues; the parent owns the remaining work.
