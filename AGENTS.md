# Nova workspace placement

Task workspace isolation is mandatory: every task session (including independent terminal sessions) must immediately isolate its work by creating and operating within a dedicated workspace under `.workspaces/<task>/` (e.g. `jj workspace add -r main --name <task> .workspaces/<task>`), rather than authoring directly in the primary checkout. For this checkout, that is `/home/anvil/repos/nova/.workspaces/<task>/`.

Reuse a suitable workspace when possible. From a secondary workspace, resolve the primary checkout through JJ/Git repository metadata and use its absolute path; do not create nested `.workspaces/` directories inside task workspaces. Keep `.workspaces/` ignored by version control and excluded from recursive build or search operations that do not honor ignore rules.

From the primary checkout, create a JJ workspace with `jj workspace add -r <base> --name <task> .workspaces/<task>`. If using plain Git, use `git worktree add -b <branch> .workspaces/<task> <base>`. Choose the base according to the existing trunk and isolation instructions.

Existing workspaces can remain at their registered locations until their tasks finish; this convention does not authorize moving or deleting them.

Parent-owned integration applies to JJ workspaces and Git worktrees: follow `instructions/development.md` (the shared development instructions for the JJ skill) and `instructions/integration.md`. Child completion is a handoff; the parent integrates verified results into local main:
- Always inspect local `main` to see if concurrent sessions have advanced it.
- Rebase the task's commits onto the current tip of local `main` (`jj rebase -s <task-root-change> -d main`).
- Check for conflicts (`jj log -r 'conflicts() & @'`).
- If conflicts exist, DO NOT guess or silently resolve them: pause and ask the user how they want to resolve the conflicts.
- After resolving any conflicts and verifying tests on the rebased tree, advance the local `main` bookmark (`jj bookmark set main -r <rebased-commit>`).
- Safely clean up the workspace (`jj workspace forget <task>` and remove the directory).

Preserve active or dirty primary checkouts and report concrete blockers.
