# Development defaults

Carry the user's scope and authorization through completion; honor local-only, review-only, no-merge, and no-publish limits. Keep work proportional.

## Authorship

The parent plans, observes, verifies, reviews, and integrates. A native implementer authors every task file change—code, tests, docs, config, and reports—including small edits. The parent makes native calls; hooks never create workers. Parallelize only available, independent writers with disjoint ownership; serialize coupled work and reuse the same worker for repairs. The parent may investigate read-only, run checks/builds, and integrate; incidental command output is exempt. If no implementer is available, report that limitation and obtain a user exception before authoring directly. Explicit user overrides control.

## Changes and delivery

- Use jj unless explicitly overridden; inspect state/history before mutations and preserve unrelated work. Adopt existing Git repositories with colocated initialization.
- Keep main (or configured trunk) deployable. Fetch and reconcile remote updates before independent work; base it on verified local main, preserving local-only results. Stack only real dependencies. Keep changes under two days; use `<type>/<slug>` branches (`feat|fix|chore|docs|refactor|release`). Ship incomplete work behind flags or unreferenced.
- Parents promptly integrate ready, verified task results into local main, test the combined candidate, and safely synchronize the primary checkout. Children return immutable commits and checks; no child pushes, PRs, or main moves. Exclude unfinished and unrelated work.
- When publication is authorized, publish accumulated results through one integration branch/bookmark and PR to remote main; reuse that publication PR. Never push main directly or bypass protections. SSH-sign commits, keep linear history, and rebase onto current trunk; never merge main into a branch or rewrite published history.
- After remote merge, prove equivalence to the tested candidate, record squash/rebase mappings, and preserve newer local descendants before reconciling local main. A bookmark move does not update checkout files. Preserve dirty files and active tasks; report synchronization blockers.
- Verify merged branch deletion. Close superseded PRs and delete unused heads only after proving integration and checking active ownership. Inspect remaining remote branches and explain retained ones; prune stale refs. Age or closed status alone never proves integration.
- Before removing workspaces, prove integration and preserve dirty, untracked, and ignored files. Clean status or a stopped child is not proof. Releases use annotated `vYYYY.MM.DD[.N]` tags on main; a published GitHub Release triggers deployment.

## Verification and files

Run relevant and required checks; inspect the final diff. Reuse unchanged evidence, distinguish pre-existing failures, and disclose gaps. Stop if failures prevent trustworthy verification; do not fix unrelated defects without authorization. Obtain independent review when required or warranted. Report checks, failures, immutable main commit, local synchronization, and exact delivery state.

Keep project files and dependencies in the repository/workspace, never directly in `/home/anvil` without a request. Use standard locations for application config. Create extra workspaces under the primary checkout's ignored `.workspaces/<task>/`; resolve the primary path from secondary workspaces, never nest them. Exclude workspaces from recursive tooling.

Set an explicit working directory. Keep temporary files in `~/.cache/agent-work/<project>/<task>/`; use disk-backed home storage for large builds and reuse caches. Remove only this task's disposable files; account for retained external artifacts. Preserve pre-existing files and review/resumption evidence.
