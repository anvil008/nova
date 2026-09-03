---
name: jj
description: "Jujutsu (jj) — the Git-compatible VCS for Workcell VCS work, including adopting a git repo with `jj git init --colocate`, and for repositories where jj/jujutsu is explicitly chosen. Use for commit, push, pull, bookmark, rebase, squash, merge, diff, log, status, working-copy, change-ID, revset, fileset, template, configuration, and workspace operations. Exclude repositories where the human chose plain git."
compatibility: "Workcell VCS workflows and repositories where jj is present or explicitly chosen; not repositories where the human chose plain git"
metadata:
  version: "1.0.0"
---

# Jujutsu (jj) Version Control

Jujutsu is a Git-compatible VCS with mutable commits, automatic change tracking, and an operation log that makes every action undoable.

Invocation: `/workcell:jj`
Prompting Reference: [`docs/models/grok-4.6/prompting.md`](../../runtime/docs/models/grok-4.6/prompting.md)

**Target version: jj 0.36+**

Execute all `jj` operations via non-interactive shell commands. State goals, constraints, and target changesets explicitly. Handoff records conform to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

## Outcome, Constraints, and Success Criteria

- **Outcome:** Execute clean, traceable VCS operations leveraging Jujutsu's first-class conflict handling, automatic snapshotting, and immutable change IDs.
- **Constraints and Boundaries:** Never run interactive commands (always provide `-m` or file paths), never omit quotes around revset expressions, and verify state via `jj st` after mutations.
- **Success Criteria:** Mutations reflect cleanly in the working copy and log, bookmarks are updated before push, and recovery paths remain intact via `jj op log`.

## Ordered Gates

Execution proceeds through three strict, ordered gates:

1. **inspect state**: Inspect current working copy and log status (`jj st`, `jj log`) before planning mutations.
2. **mutate with message**: Apply changes or VCS operations using non-interactive commands with explicit messages (`-m`).
3. **verify state**: Verify resulting repository and working copy status (`jj st`) to confirm expected tree state and lack of unintended conflicts.

## References and Topics

- Understand how jj relates to Git: [git-compatibility.md](references/git-compatibility.md)
- Write revset, fileset, or template expressions: [revsets.md](references/revsets.md)
- Push, pull, manage bookmarks, or work with GitHub: [bookmarks.md](references/bookmarks.md)
- Split, rebase, squash, or resolve conflicts: [conflicts.md](references/conflicts.md)
- Run parallel agents with isolated working copies: [parallel-agents.md](references/parallel-agents.md)
- Configure jj, set up aliases, or customize diffs: [config-reference.md](references/config-reference.md)

## Mental Model and Core Operations

- **The working copy is a commit.** No staging area. Every file change is auto-snapshotted into `@` when you run any `jj` command.
- **Change IDs are stable.** Change IDs (e.g., `tqpwlqmp`) persist across rewrites; commit hashes change on rewrites.
- **Bookmarks must be explicitly set.** Bookmarks do not advance automatically on new commits; set them explicitly before push: `jj bookmark set <name> -r @`.
- **Conflicts do not block.** jj allows committing conflicted files. Inspect and resolve conflicts directly, then verify with `jj st`.

## Harness Limitations

Skill frontmatter fields `allowed-tools`, `model`, `effort`, `license`, and `compatibility` are unsupported for capability enforcement or routing under Grok Build; execution relies on native CLI flags (`--tools`, `--disallowed-tools`), agent definitions, capability modes, and specialist dispatch. API-only model controls and programmatic tool calling are unsupported in skill prompts.
