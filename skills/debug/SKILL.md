---
name: debug
description: Take one reported symptom — a stack trace, a failing CI job, an incident, a flaky test — reproduce it, find the root cause, fix it test-first, and open one PR. Starts from a known failure, not a sweep.
---

# Debug

Something is known to be broken. Reproduce it, understand it, fix it, and prove the fix with a test that failed first. One PR to `main`.

You are the orchestrator ([ADR 0007](../../docs/adr/0007-primary-agent-is-a-pure-orchestrator.md)): you dispatch agents, hold the human gates, run `git` / `jj` / `gh` for branch, merge, and issue-state operations, and read gate output and handoff records. You never read or edit the target project's code, run its suites, or author its artifacts. Reading a file list or diffstat to choose a dispatch is orchestration; reading a file's contents to judge it is not.

This orchestrator treats reproduction as the admission gate and carries the debugger's evidence into the fix dispatch.

This starts where [`code-analysis`](../code-analysis/SKILL.md) ends: that skill sweeps for defects nobody has reported, this one begins with a symptom somebody already hit. If you have a report, start here — hunting is wasted effort when the failure is already in your hands.

## Reproduction is the gate

**No reproduction, no fix.** A `debugger` that cannot make the failure happen on demand returns what it tried and what it could not establish, and the run stops there. Do not route an unreproduced report to a builder: a change to code nobody has seen fail is a guess that will be believed because it shipped.

If the report is too thin to reproduce, the missing information is the finding — go back to whoever reported it with the specific gap, rather than inventing a plausible scenario and fixing that instead.

## Procedure

1. **Diagnose.** Dispatch a `debugger` with the report. It reproduces the symptom, shrinks it to a minimal case, forms and refutes hypotheses by experiment, bisects history when the code used to work, and returns the root cause with `file:line` evidence, the reproduction command, and a proposed fix location. It fixes nothing and leaves no instrumentation behind.

   For a **flaky** failure it returns a measured rate ("17/200 under `-race`") rather than a verdict, because a single green run proves nothing about nondeterminism.

2. **Decide the scope.** The diagnosis usually names one defect; sometimes it names a class. Fix the reported defect. If the root cause implies siblings, list them and ask the human whether to widen — do not quietly turn a bug fix into a sweep.
3. **Plan** only if the fix spans issues. A single-defect fix needs no folio: take the diagnosis straight to step 4. For a class of defects, dispatch the `planner` with the diagnosis and get approval as usual.
4. **Fix, test-first.** For the single-defect path, use a stable lowercase symptom slug as the single-PR mode's `<planId>`, then send both agents a dispatch brief conforming to [`agents/handoff.md`](../../agents/handoff.md) with `issue: null`. Its `brief` carries the debugger's reproduction command and minimal case as the single acceptance test, with `name`, `kind`, and `oracle`; its `ownership` is the debugger's proposed fix location. Dispatch a `test-author` against that oracle — it is already a failing case, which is exactly what a seal wants — then a `builder` to fix it against a sealed test it cannot edit. The builder's intermediate PR body names the symptom and the reproduction instead of `Closes #<n>`.

   For a flaky fix, the acceptance test must run enough repetitions to distinguish "fixed" from "got lucky", and the debugger's measured rate sets that count.

5. **Review** with the usual lens fan-out, weighted to `correctness` and to the area the defect lives in.
6. **Integrate and open the final PR.** Run [`build`](../build/SKILL.md) in **single-PR mode**, dispatch the `integrator` over each wave, and merge intermediate PRs to the integration branch only on the evidence. The final PR from that branch to `main` names the symptom, reproduction, root cause, introducing commit if there was one, and covering test. For the single-defect `issue: null` path it names the symptom and the reproduction instead of `Closes #<n>`; for planned defects it repeats every per-issue `Closes #<n>` line.

## Boundaries

Never ship a fix whose test did not fail first — that is the whole gate, and "the test passes now" is not evidence when it also passed before. Never fix code the diagnosis did not implicate, and never clean up while you are in there: an unrelated change in a fix diff is how a revert takes something else with it. Never close a flaky-test report by re-running until it passes. If the root cause turns out to be a design problem rather than a defect, say so and route it to [`new-feature`](../new-feature/SKILL.md) or [`code-refactor`](../code-refactor/SKILL.md) instead of patching around it.
