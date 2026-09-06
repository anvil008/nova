# 7. The primary agent is a pure orchestrator

Planning ownership is superseded by [ADR 0028](0028-planner-owned-research-and-three-harnesses.md): one planner authors the plan; the orchestrator frames and reviews it. The execution boundaries below remain applicable.

## Status
Superseded for planning and source access by [ADR 0027](0027-developer-workflows-and-orchestrator-owned-planning.md). Historical decision follows.

## Context
Every shared skill named the primary agent as both the dispatcher and a worker. The build
skill had it integrate a wave "by serial merge plus retest" and run "a combined GREEN
verification". The planner skill had it read "repository guidance, relevant code, tests,
architecture, and current state" and write the folio itself, with no agent involved at
all. Code-review had it own "the consolidated report and verdict", research "the synthesis
and the conclusion", deploy the release execution. Only the docs skill drew the line
correctly: "The primary agent owns the result; the `docs` agent does the writing."

Mixing the two roles costs three things. Context that belongs to one issue's
implementation crowds out the wave state the orchestrator needs to schedule the next one.
Work the orchestrator performs itself is unattributed: it produces no handoff record, no
command-linked evidence, and nothing a later reader can audit. And the boundary is
unenforceable, because a rule that says "delegate, except when you are also the worker"
has no test that can fail.

The previous design justified the overlap on integrity grounds: the primary agent retested
independently because a builder's report of its own success is not trustworthy, and it
"must never infer completion from a builder report alone". Removing the orchestrator's own
test run removes that check, so something has to replace it.

## Decision
The primary agent orchestrates and never performs target-project work.

It may spawn agents, hold human gates, run `git`, `jj`, and `gh` for merge, branch, and
issue-state operations, read mechanical gate output, and read agent handoff records. It
may not read or edit target-project code, run its test suites, or author plans, findings,
implementations, or documentation.

The line is *producing evidence* versus *transforming it*. A skill's own deterministic
scripts — `waves.py`, `merge_findings.py`, `render_plan.py`, `render_review.py`,
`render_research.py`, `reconcile_github.py` — are pure functions over evidence agents
already produced, and the orchestrator runs them. They involve no judgment and never touch
target-project code, so running one is closer to reading a gate than to doing the work.
Producing the evidence they consume is always an agent's job.

Independent verification survives the change by moving from judgment to mechanism. The
orchestrator no longer re-runs the suite and forms an opinion; it reads evidence that a
machine produced and an agent cannot author: `tdd-guard status --json`, `gh pr checks`,
and CI conclusions. A builder's prose claim of GREEN remains worthless, exactly as before.
An `integrator` agent runs the combined wave verification and returns command-linked
evidence, and the orchestrator accepts or rejects the wave on the gate output rather than
on that agent's summary.

The orchestrator remains the sole completion authority. Deciding is orchestration;
producing is not.

## Consequences
Four agents exist that previously did not: `planner`, `test-author`, `integrator`, and
`deploy`. Each shared skill becomes a dispatch and gate contract rather than a procedure
the primary agent executes, and each names the agent that does the work.

Test authorship separates from implementation. A `test-author` agent writes the failing
tests, proves RED, and seals; the `builder` then implements against tests it did not write
and cannot edit, because the guard denies `PreToolUse` edits to sealed paths. The builder
is no longer both prosecutor and judge over its own Definition of Done.

The mechanical gates now carry weight they did not carry before. A gap in `tdd-guard`
coverage is no longer backstopped by an orchestrator who would have noticed while running
the tests, so gate correctness matters more than it did.

Orchestrator context stays small and long-lived, holding wave state rather than
implementation detail. The cost is more handoffs: work that was one agent reading a file
is now a dispatch, a report, and a gate read, which is slower for small changes and is the
deliberate trade.
