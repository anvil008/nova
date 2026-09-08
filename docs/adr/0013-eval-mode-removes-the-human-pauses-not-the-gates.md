# 13. Eval mode removes the human pauses, not the gates

## Status

Accepted

## Context

Nova is built around a human: the planner stops for approval of its folio and sidecar,
`new-feature` interviews before it plans, work lands as pull requests a person reviews and the
main conversation merges. A benchmark run has none of that. A DeepSWE-style container holds a
task repository and hidden verifiers, there is no reviewer, usually no remote and no GitHub at
all, and the only deliverable is the diff the harness collects when the process exits.

Run unchanged in that container, the harness deadlocks on approvals it will never get and spends
turns on a GitHub that is not there. The tempting fix — an "eval" flag that skips the gates — would
measure a harness nobody ships: the TDD ceremony is most of what Nova _is_, so a score taken
without it says nothing about the product. The other tempting fix, prose in the skills ("if this
is an eval, do not wait"), is not a switch at all; every agent would have to be trusted to read
it the same way, and nothing mechanical would stop a `gh` call.

The two properties that mattered were that the switch be mechanical and that it be scoped. An
eval must not be something an agent can decide it is in, and marking a task repository must never
put the Nova checkout on the same machine into eval mode.

## Decision

Eval mode is one file in the task repository, `.nova/eval-mode.json`, written by
`scripts/bootstrap-eval.sh` and read by `build-guard`. The guard resolves it from the repository
each command targets — the same `-C`/`--git-dir`/cwd resolution it already uses to read the live
branch — and only where the bootstrap puts it: at that toplevel, exactly. There is no upward walk,
because one would relax every repository nested under any marked directory, and a path git cannot
resolve to a toplevel is not in eval mode at all. The bootstrap refuses to write a marker into the
Nova source tree, and refuses a directory that is not its repository's root, so the file only
ever exists where the guard will read it.

Writing that file is a human's act, so an agent's attempt to write it is denied like any other
policy violation: `build-guard` denies the shell vectors — a redirection target, and the file
operands of `tee`/`cp`/`mv`/`install`/`ln`/`dd`/`truncate` — and `build-hooks`, the hook wired to
`Edit`/`Write`, denies a `file_path` naming it, in every harness dialect. Both refuse in or out of
eval mode, so a marked repository cannot be used to mark another one.

Alongside the marker, an eval driver exports `NOVA_EVAL_TASK_DIR`. The marker is read from the
repository a command targets, which says nothing about a command run from elsewhere; the variable
travels with the process instead. When it is set, `gh` is denied from any working directory, and
the default-branch relaxation applies only to the repository it names.

Inside a marker-bearing repository the guard changes exactly two things. It **relaxes** `git`/`jj`
commit, merge, rebase, cherry-pick and push on `main`/`master`, because an eval's work has to land
on the task repository's default branch. It **tightens** `gh` to a blanket deny, the top-level
session's merges included: GitHub is out of scope for an eval, so the merge authority of ADR 0011
has nothing to act on. Every other rule — branch rewriting, `update-ref`, the xargs and inline-alias
obfuscation denials, the RAM-tmpfs rule — is untouched, and so is `tdd-guard`. Eval mode removes
the human pauses and the outward-facing surface, not the mechanical gates.

The instruction surface travels with the task repository rather than the harness: the bootstrap
prepends a delimited preamble to the task repo's `AGENTS.md` and `CLAUDE.md` stating that
approvals are pre-resolved, that there is no interview, that GitHub and deploy are out of scope,
that verifier and reference material must never be read, and that the deliverable is the committed
working tree. No skill or agent definition gains an eval-only branch.

## Consequences

A benchmark result is now a result for the harness that ships, gates and all, and the difference
between an eval run and an ordinary one is auditable: one file, one bootstrap script, two guard
rules.

The guard corpus gains a repository dimension alongside the payload-shape dimension ADR 0011
introduced. The `-eval` shapes in `scripts/hooks/tests/guard-corpus.txt` send their payloads from
a marker-bearing repository; `claude-nested` and `claude-stray` send them from a repository whose
parent carries a marker and from a plain directory that carries one, both of which must be
unaffected; and every unscoped probe runs outside all of them, which is what keeps "behaviour is
unchanged everywhere else" a checked claim rather than an assertion.

Two residuals are accepted and neither is closed by this decision: the marker-write denial covers
the vectors the tokenizer can see, so a path assembled inside a quoted script body or written by a
helper program the guard cannot read still gets through; and `NOVA_EVAL_TASK_DIR` is an
environment variable, which an agent can unset for a single command, making it defence in depth
rather than a boundary. Both are the same trade the tmpfs rule makes — `build-guard` stops mistakes
and drift, it is not an adversary-proof sandbox — and what the marker cannot do in any case is
widen anything: it removes protections only inside the one repository it sits in, and it adds a
prohibition (`gh`) rather than only subtracting.

A preamble written into an instruction file the task repository already tracks shows up in the
scored diff. `--remove` takes it back out and restores the file byte-for-byte, so the eval driver
runs it before collecting the patch; instruction files the bootstrap creates itself are
local-ignored and never appear at all.
