# Nova workspace placement

Create additional JJ workspaces and Git worktrees under the primary Nova checkout's `.workspaces/<task>/` directory, rather than in sibling directories. For this checkout, that is `/home/anvil/repos/nova/.workspaces/<task>/`.

Reuse a suitable workspace when possible. From a secondary workspace, resolve the primary checkout through JJ/Git repository metadata and use its absolute path; do not create nested `.workspaces/` directories inside task workspaces. Keep `.workspaces/` ignored by version control and excluded from recursive build or search operations that do not honor ignore rules.

From the primary checkout, create a JJ workspace with `jj workspace add -r <base> --name <task> .workspaces/<task>`. If using plain Git, use `git worktree add -b <branch> .workspaces/<task> <base>`. Choose the base according to the existing trunk and isolation instructions.

Existing workspaces can remain at their registered locations until their tasks finish; this convention does not authorize moving or deleting them.

Parent-owned integration applies to JJ workspaces and Git worktrees: follow `instructions/development.md` (the shared development instructions for the JJ skill). Child completion is a handoff; the parent must integrate verified results and synchronize local main within existing authorization before declaring overall completion. Preserve active or dirty primary checkouts and report concrete blockers.
