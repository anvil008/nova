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
Prompting Reference: [`docs/models/claude-sonnet-5/prompting.md`](../../runtime/docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)

Handoff records and state operations conform to [`anvil.agent-handoff/v1`](../../runtime/handoff.md).

## Ordered Gates

Execution proceeds through three strict, ordered gates:
1. **inspect state**: Inspect current working copy, bookmark, revset, and operation log via `jj st`, `jj log`, and `jj op log`.
2. **mutate with message**: Apply required mutation explicitly with non-interactive flags and messages (`jj describe -m`, `jj commit -m`, `jj squash -m`).
3. **verify state**: Verify resulting repository and workspace state via `jj st` to ensure no unintended conflicts or broken revisions exist.

## Topics

| I need to... | Deep dive |
|--------------|-----------|
| Understand how jj relates to Git, or use raw git in a jj repo | [git-compatibility.md](references/git-compatibility.md) |
| Write revset, fileset, or template expressions | [revsets.md](references/revsets.md) |
| Push, pull, manage bookmarks, or work with GitHub | [bookmarks.md](references/bookmarks.md) |
| Split, rebase, squash, or resolve conflicts | [conflicts.md](references/conflicts.md) |
| Run parallel agents with isolated working copies | [parallel-agents.md](references/parallel-agents.md) |
| Configure jj, set up aliases, or customize diffs | [config-reference.md](references/config-reference.md) |

## Mental Model

**The working copy is a commit.** No staging area. Every file change is auto-snapshotted into `@` when you run any `jj` command. Instead of "stage → commit," just code and describe.

**Change IDs are stable. Commit IDs are not.** Every commit has two identifiers:
- **Change ID** — Stable across rewrites. Letters k–z (e.g., `tqpwlqmp`). Prefer these.
- **Commit ID** — Content hash, changes on any rewrite. Hex digits. This is the Git commit ID in colocated repos.

**History is mutable.** Commits can be freely rewritten. Descendants auto-rebase. Old versions stay in the operation log.

**Bookmarks are not branches.** Bookmarks don't advance when new commits are created. They follow rewrites but must be explicitly set before pushing.
→ Deep dive: [bookmarks.md](references/bookmarks.md)

**Conflicts don't block.** jj allows committing conflicted files. Resolve at your convenience by editing conflict markers directly, then verify with `jj st`.
→ Deep dive: [conflicts.md](references/conflicts.md)

## Agent Rules

Non-negotiable when operating as an automated agent:

1. **Always use `-m` for messages.** Never invoke a command that opens an editor. Commands that need `-m`: `jj new`, `jj describe`, `jj commit`, `jj squash`.
2. **Never use interactive commands.** `jj split` (without file paths), `jj squash -i`, `jj resolve` — all hang. Use file-path args or `jj restore` workflows.
3. **Verify after mutations.** Run `jj st` after `squash`, `abandon`, `rebase`, `restore`, or any destructive op.
4. **Use change IDs, not commit IDs.** Change IDs survive rewrites.
5. **Quote revsets.** Always single-quote: `jj log -r 'mine() & ::@'`.

### Agent-Specific Configuration

```toml
# agent-jj-config.toml
[user]
name = "Agent"
email = "agent@example.com"

[ui]
editor = "TRIED_TO_RUN_AN_INTERACTIVE_EDITOR"
diff-formatter = ":git"
paginate = "never"
```

Launch with: `JJ_CONFIG=/path/to/agent-jj-config.toml <agent-harness>`
→ Deep dive: [config-reference.md](references/config-reference.md)

## Core Workflow

The daily loop: **describe → code → new → repeat.**

```bash
jj describe -m "feat: add user validation"
# make changes — auto-tracked, no `add` needed
jj st && jj diff
jj new -m "feat: add error handling"
```

### Curating History

```bash
jj squash -m "feat: final clean message"   # fold working copy into parent
jj absorb                                   # auto-distribute hunks to right ancestor
jj abandon @                               # drop a failed experiment
```
→ Deep dive: [command-gotchas.md](references/command-gotchas.md)

### Non-Linear Work

When new work doesn't depend on the current chain, branch off trunk:

```bash
# Create sibling from trunk (doesn't move @)
jj new trunk() --no-edit -m "fix: correct timezone handling"
jj edit <bugfix-change-id>
# ... fix the bug ...

# Return to original work
jj log -r 'heads(trunk()..)'
```

## Harness Limitations

Native context forks and workflows are omitted with notes in Claude Code; procedures execute sequentially within the primary session.
