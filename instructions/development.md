# Development conventions

Apply the selected skill in this conversation. Carry the user's scope, decisions, and authorization through completion; no mandatory team, separate planning phase, or repeated approval. Reuse these instructions if already loaded, including as Antigravity's `rules/nova.md`.

## Work and verification

- Choose the smallest relevant skill. Spec clarifies unresolved intent; plan defines tasks and acceptance tests; build implements. Reuse existing decisions for clear tasks. Multiplan requires an explicit request for its three harnesses. Spec permits requirements and requested isolated prototypes; plan permits tests, not product behavior. Honor read-only limits.
- The parent plans, observes, verifies, reviews, and integrates. A native implementer authors every task file change—code, tests, docs, config, and reports—including small edits. Give each writer scope, source base, owned paths, acceptance checks, and a concrete handoff; reuse it for repairs. The parent may investigate read-only, run checks/builds, and integrate; incidental command output is exempt. Hooks never create workers: the parent uses native calls. Parallelize only available, independent writers with disjoint ownership, including fixtures, generated files, lockfiles, and docs; serialize coupled work. If no implementer is available, report the limitation and obtain a user exception before direct authorship. Explicit user overrides control.
- Run checks for changed behavior and required final checks. Reuse evidence while source and environment remain valid. Inspect the final diff and hook edits; hook silence is not verification. Do not enable new hooks as an implementation side effect. Separate pre-existing failures, disclose gaps, and stop if they prevent trustworthy verification. Do not repair unrelated defects without authorization. Obtain independent review when required or warranted.
- Reports default to Markdown; HTML needs an explicit visual/HTML request. Consolidate evidence and keep artifacts proportional. Summarize delivered changes with a visual workflow diagram, key deliverables with file links, verification evidence, and the immutable local main commit. Record actual architectural decisions in `docs/adr/NNNN-title.md` (Status, Context, Decision, Consequences); preserve accepted history and keep affected docs aligned.

## Parent-owned task integration

Use jj unless explicitly overridden. Preserve unrelated work. Parents promptly integrate ready verified task results into local main and safely synchronize the primary checkout; children return immutable local commits and checks without pushing, opening PRs, or moving main. Local main may lead remote main. Publish only when authorized, through one integration bookmark and PR for accumulated results; never push main directly. Preserve active work and newer local descendants, reconcile squash/rebase mappings, and verify branch cleanup. Explicit local-only/review-only limits remain binding.

## Read only when needed

Do not preload these references. Read the relevant one once and reuse it:

- Before revision changes, workspace integration, publication, releases, or cleanup: [integration procedures](../instructions/integration.md). Includes trunk protections, workspace placement, and safe reconciliation.
- For substantial reports or checkpoints/resumption: [reporting conventions](../instructions/reporting.md). Follow the selected skill's artifact format and honor user paths.
- For bulk reads or a routing-hook redirect: [read routing](../instructions/read-routing.md). Keep focused reads direct; use the documented fallback when helpers are unavailable.
- Only after an explicit Flow request: [Flow tracking](../instructions/flow.md). Flow is disabled by default: do not create tasks, bind sessions, report usage, or start viewers otherwise.
