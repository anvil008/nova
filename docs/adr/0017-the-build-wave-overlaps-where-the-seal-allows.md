# 17. The build wave overlaps where the seal allows

## Status

Accepted

## Context

The build loop ran a milestone as a sequence of declared waves, and it ran them to the
letter: a wave was dispatched, every issue in it had to finish, and only then was the next
wave considered. `wave` was a barrier. That is a stronger guarantee than the loop actually
needs — the thing that makes an issue safe to start is that the work it depends on has
landed, and `dependsOn` already says exactly that. When one issue in a wave was slow, every
issue in the next wave waited on it whether or not it had any dependency on it at all.

The same shape cost the loop twice more. Documentation was dispatched after the merge, so a
merged wave was briefly a wave whose README described the previous one, and the docs branch
then had to be gated on its own. And a `specifier` — an agent that writes failing tests and
proves RED, touching nothing a builder will touch — sat idle through the integrator's run
even though the issues it would seal were already known.

None of that is the part that has to be serial. What has to be serial is the authorship
boundary: the agent that defines "done" is not the agent judged against it, and nothing
reaches `main` except through a gate a machine ran over the whole combined state. Those
constraints are about _who writes what_ and _what is proven before a merge_, not about the
calendar the waves were laid out on. This ADR takes the overlap the seal already permits.

## Decision

**Selection is gated on dependencies, not on the declared wave.** Every not-done issue whose
`dependsOn` are all done is a candidate for the current round, whatever `wave` the planner
put it in, so one straggler no longer freezes work that is already unblocked. `wave` demotes
from a barrier to a planning hint — it is the order candidates are considered in — and to
the reporting anchor `waves.py` publishes as `currentWave`.

**An ownership overlap defers the candidate; it does not fail the round.** A candidate whose
`ownershipHint` glob overlaps one already selected is left out of `unblocked`, named in
`deferred` with the `overlapsWith` key it collides with, and dispatched in a later round.
Overlapping work is never dispatched concurrently. Because candidates are considered
earliest declared wave first, a deliberately coarse late hint — a repository-wide
documentation pass, this one included — defers itself rather than starving the issues it
overlaps.

**A declared same-wave overlap is still a plan defect.** `waves.py` rejects it outright
instead of deferring it, because the planner asserted a parallelism its own hints cannot
deliver, and a plan that says something false should be sent back rather than quietly worked
around. Deferral covers the pull-forward the scheduler does; it does not cover a plan that
asked two builders to write the same files. Wave 0 is the ungrouped bucket, so an overlap
there is warned about and then held back by the same in-flight check as any other candidate.

**The `documenter` is dispatched alongside the `integrator`, not after the merge.** Both
start from the same base once the wave's builders are done, each in its own workspace. Doc
authoring needs nothing but the changed-file and pull-request list, and that exists the
moment the pull requests open, so it has no reason to wait behind a merge. This is wired
today in `skills/new-feature/SKILL.md`, the entry workflow that drives the wave loop.
`skills/build/SKILL.md` dispatches no `documenter` and has no documentation step of its own:
its loop ends at the merge, and documentation for a milestone driven straight from `build`
comes from the `docs` skill, invoked separately.

**Documentation merges only inside a combined GREEN that includes it.** Wherever a
`documenter` is dispatched beside an `integrator`, the docs branch never lands on its own
authority. If the `documenter` returns before the serial merge begins, its branch joins that
round and one combined run covers everything; if it returns later, one more `integrator`
round runs over it on the merged base. That round is also the docs gate —
`skills/docs/scripts/docs_check.py`, and `scripts/render-diagrams.py --check` where the
README's visuals are generated ([ADR 0010](0010-readme-diagrams-are-generated-svg.md)) —
reported beside the combined suite.

**Speculative `specifier` dispatches are permitted and opportunistic.** While the integrator
runs the combined suite, the orchestrator may seal tests for issues that are not unblocked
yet: the ones that become ready once the in-flight set lands. Phase 1 runs unrelaxed — real
failing tests on the current base, honest RED, a seal. If the speculation turns out wrong,
the whole cost is a seal no builder consumes.

**A speculative `builder` is never dispatched.** Phase 2 for a speculated issue starts only
after its dependencies have merged, in a workspace on the merged base, where the builder
re-proves that the sealed tests still fail for the right reason before implementing. A seal
written against a base that moved is cheap to throw away; an implementation written against
one is not.

**`ownershipHint` is exactly one narrow path or glob.** A single token — never prose, a comma
list, or two paths joined by "and" — and the narrowest glob covering every file the issue
changes plus the tests its `specifier` will write for it. When an issue's files span
unrelated subtrees, split the issue rather than widening the glob to their common parent:
under the deferral rule a coarse hint serializes everything it touches, so broadening the
hint buys no parallelism and spends the parallelism a split would have kept.

### What deliberately stays serial

`specifier` then `builder`, per issue, stays serial. The two phases never run concurrently
and no builder is dispatched for an issue that has no seal, because a builder without one is
a builder grading its own homework. The two-phase seal is the authorship boundary this whole
ADR is bounded by, and it is unchanged.

The `integrator`'s merge stays serial — one pull request at a time onto the scratch ref, or
onto the named integration branch in single-PR mode — with the full suite run on the
combined state that results.

Nothing merges before a combined GREEN covering every branch in the round, documentation
included, and the orchestrator still decides on the gate output rather than on any agent's
report ([ADR 0007](0007-primary-agent-is-a-pure-orchestrator.md),
[ADR 0011](0011-merge-authority-is-the-main-conversation.md)).

## Consequences

A milestone finishes in fewer rounds, and the rounds are uneven: an issue planned into wave 3
can be in flight beside one from wave 1 if its dependencies happen to be done. Wave numbers
are still what reports are grouped under, so the shape of a run is still legible, but a
reader who treats `wave` as "when this ran" will be wrong. The planner keeps writing waves
because they are how a human reasons about a plan; the scheduler stops obeying them.

`ownershipHint` quality now decides throughput rather than just tidiness. A hint that is
wider than the issue serializes every issue it overlaps, and there is no error message for
that — the work simply lands in `deferred` round after round. This is why the granularity
rule tightened at the same time, and why the planner review step treats a coarse hint as a
reason to send a plan back.

Speculative sealing spends specifier work that may be discarded, and a seal taken on a base
that later moves must be re-proved before its builder starts. That re-proof is the price of
the overlap; it is paid by the builder, in the workspace, before any implementation exists.

The overlap is not yet symmetric across the entry workflows, and that is a known gap rather
than a decision: `new-feature` dispatches the `documenter` beside the `integrator`, while
`build`'s own loop stops at the merge and leaves documentation to a `docs` pass someone has to
invoke. Wiring the same overlap into `skills/build/SKILL.md` is follow-up work; until it
lands, "alongside the integrator" describes the policy and the `new-feature` implementation of
it, not every path into the wave loop.

The documenter now writes against pull requests rather than against `main`, which means it
reads a state no one has merged yet. That is the same state the integrator is testing, so
the two agree by construction — but a documenter that finishes after the merge round has
begun costs an extra integrator round rather than joining the current one.

This ADR does not change what `tdd-guard` enforces, who may write tests, or what the
orchestrator is allowed to do. It changes only when work is allowed to start.
