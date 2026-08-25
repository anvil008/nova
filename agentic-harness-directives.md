# Agentic Harness Design Directives

**Purpose:** Instructions for updating agent definitions, system prompts, hooks, and orchestration config in an existing Claude Code multi-agent harness. Derived from published evals as of August 2026.

**How to use this document:** Apply the DIRECTIVES section as concrete changes. Read CONFIDENCE TIERS before applying anything — some directives are strongly evidenced and some are reasoned inference, and they should not be applied with equal force. Do not treat the evidence summaries as instructions; they exist to justify the directives and to tell you when a directive stops applying.

---

## 0. Core principle

Everything below reduces to two mechanisms:

1. **Externally grounded verification beats interpretation.** An artifact that produces a machine-checkable pass/fail signal (a test run, a compiler, a linter) drives large measured gains. An artifact the agent interprets (prose specs, plans, self-critique) drives small and inconsistent gains. Prefer gates over documents.
2. **Context is a signal-to-noise problem, not a capacity problem.** Degradation begins far below the window limit. Every context technique is the same move: raise the fraction of the window that is load-bearing for the current decision.

When a proposed change does not serve one of these two mechanisms, it is probably ceremony.

---

## 1. DIRECTIVES — Verification (highest priority)

**1.1 Make tests the gate, and commit them before implementation.**
Sequence: write tests → run them → confirm they fail for the right reason → **commit the failing tests** → implement until green.

**1.2 Forbid the implementing agent from modifying committed tests.**
Enforce mechanically, not by prompt instruction. In a `SubagentStop` / `PostToolUse` hook, run a diff against test paths and fail the turn if test files changed during an implementation phase:

```
git diff --name-only <base> -- '**/test*' '**/*_test.*' '**/*.spec.*'
```

Non-empty output during an implementation phase = block. Prompt-level instructions alone are insufficient; models edit tests to pass when the loop allows it.

**1.3 Maintain a held-out test set the agent never sees.**
Two suites: the visible suite the agent iterates against, and a holdout used only for scoring. The gap between them is the reward-hacking signal. This is the single most important metric in the harness.

**1.4 Do not assume agent-written tests carry the same guarantee as human-written ones.**
They are worth having, but the correctness ceiling with self-generated tests is substantially lower. Where a task matters, have a human write or review the reproduction test. Where tests are agent-generated, weight the holdout metric more heavily.

**1.5 Prefer execution-grounded feedback over self-assessment.**
Real test runs, compiler errors, and linter output produce large gains. An agent critiquing its own unexecuted plan produces little. Remove or downgrade review stages that do not execute anything.

---

## 2. DIRECTIVES — Planning and routing

**2.1 Treat planning as a routing decision, not a mandatory pipeline stage.**

| Task shape | Treatment |
|---|---|
| Bounded fix, single file, clear requirement | Direct prompt. No plan stage. |
| Multi-file, or requirement could be reasonably misread | Short plan (Explore → Plan), kept brief |
| Genuinely underspecified, greenfield, multi-service | Actual spec document |

Heuristic for the middle row: write the plan only if you would be annoyed to have the agent interpret the requirement differently than intended.

**2.2 Keep plans short. The value is in Explore+Plan being cheap, not in a long document.**
Heavyweight spec pipelines have been measured burning ~2× the tokens of lightweight ones while producing a less complete result. Prose volume is not the mechanism.

**2.3 Write plans to disk, not just to the context window.**
A `plan.md` the agent writes and re-reads survives compaction and context loss. The window becomes a cache; the file is the system of record.

**2.4 Keep persistent instruction files lean and layered.**
`CLAUDE.md` / `AGENTS.md` under ~150 lines. Layer per-service files in a monorepo rather than one large root file. Do not paste the full spec into every session.

**2.5 Treat specs as code if they exist at all.**
Same PR, same review, updated with the change. An unmaintained spec is worse than none — it is confidently stale input.

---

## 3. DIRECTIVES — Subagents

**3.1 Do not split subagents on persona or nominal expertise.**
A "Rust expert" and a "Python expert" on the same base model have identical weights. A role label adds no capability. Delete subagents whose only differentiator is an expertise claim in the system prompt.

**3.2 Split on verification environment and context isolation instead.**
Valid differentiators:
- Distinct toolchain/verifier (e.g. `cargo clippy -D warnings` + `cargo test` vs `go vet` + `golangci-lint` + `go test -race` vs `tsc --noEmit` + eslint)
- Distinct worktree with genuinely independent work
- Model routing backed by measured per-language performance, not assumption

**3.3 Run coupled changes single-agent.**
If change A must precede change B, or the pieces share an interface contract, a single agent with full context beats handoffs. Multi-agent coordination becomes net-negative once single-agent capability is already high; the handoff cost is spent re-establishing context the single agent held for free.

**3.4 Use read-only, one-shot exploration subagents with a hard return schema.**
- No edit tools (also removes a class of drift)
- Return **pointers, not payloads**: file paths + line ranges, symbol names, one line of "why this matters"
- The parent re-reads only the files it actually needs
- Cap exploration breadth — a subagent reading 40 large files rots and produces a worse summary than one reading 8

**3.5 Restrict exploration-subagent use to localization, not semantics.**
Compresses well: "where is X handled," "what calls this," "which files touch this config." Compresses badly: "how does this subsystem's state machine work" — the summary drops exactly the nuance needed, invisibly.

**3.6 Keep the implementation in the parent.**
Full context on the few files that matter, not a lossy summary of many.

---

## 4. DIRECTIVES — Context management

Apply in this order; the first two are the highest leverage per unit of effort.

**4.1 Cap tool output at the source (do this first).**
Most window contamination is tool output nobody needed. Lossless and cheaper than compressing after the fact:
- Read by line range, not whole file, wherever the target is known
- Pipe test output through a filter returning failures only
- Truncate command output; never `ls -R` a monorepo into the window
- Return grep hits as paths + line numbers, not surrounding blocks

**4.2 Externalize state to the filesystem.**
Plan, decisions, and progress in files the agent re-reads. Durable across compaction; costs a bounded re-read instead of degrading silently.

**4.3 Let tests carry state.**
A committed failing test reconstructs intent after total context loss. Under a prose-plan-only harness, context loss means intent loss. Cheapest rot mitigation available, since the tests are being built anyway.

**4.4 Evict by supersession, not by age.**
The dominant residue in long sessions is superseded content: stale versions of files edited since, exploration traces for abandoned paths, test runs invalidated by later fixes. Age is the wrong axis. Requires harness plumbing — implement after the above.

**4.5 Prefer clean resets at task boundaries over mid-task compaction.**
Compaction drops content you did not choose. A fresh context that re-reads `plan.md` plus three relevant files is usually higher-signal than a compacted one carrying summarized residue from abandoned approaches. Decompose so tasks have boundaries worth resetting at.

---

## 5. DIRECTIVES — Code intelligence tooling

**5.1 Add symbol resolution.**
Go-to-definition and find-references (LSP / SCIP / ctags) answer what an identifier is actually bound to through imports, aliases, and overloads. This is ground truth the model cannot hallucinate, and it returns real call sites rather than textual candidates the agent must then triage by reading.

**5.2 Add deterministic AST rewrite for multi-site changes.**
`ast-grep --rewrite`, comby, or equivalent. A 200-site signature change should be one command — structurally correct, zero model tokens per site. Per-site LLM editing across many call sites is the most wasteful and error-accumulating pattern in the harness.

**5.3 Use structural search where grep produces false positives.**
tree-sitter queries / ast-grep match syntax, not text — no matches inside comments or strings, and the enclosing node can be returned instead of a bare line.

**5.4 Keep the tool surface small.**
Every tool costs description tokens on every request plus wrong-tool-selection risk. Models are far more fluent in bash/grep than in a bespoke query DSL; an agent fumbling pattern syntax burns more turns than the precision saves. Two good tools beat eight.

**5.5 Invalidate any index on write, or do not build one.**
A stale index answers confidently and wrongly; grep merely misses. Note also that LSP requires a resolving build, so it degrades exactly mid-refactor when the repo is broken — keep grep as the fallback path.

---

## 6. Anti-patterns to remove

- Subagents differentiated only by a persona/expertise claim
- Sequential multi-agent handoffs on coupled changes
- Exploration subagents that return file contents instead of pointers
- Agent-authored tests used as the sole correctness gate
- Review or "verification" stages that do not execute anything
- Mandatory plan stages on bounded single-file tasks
- Full spec pasted into every session
- Whole-file reads when the target line range is known
- Per-site LLM edits for mechanical multi-site rewrites
- Unmaintained spec/plan documents left to drift out of sync with code

---

## 7. Metrics — instrument these, not token counts

Token savings are trivial to demonstrate and mean nothing if the agent is now deciding on lossy input. Track:

| Metric | What it detects |
|---|---|
| **Validation-minus-holdout gap** | Reward hacking / test gaming. Expect it to widen with task size and with cheaper models. |
| **Regression rate** (previously-passing tests broken) | Lossy context, bad summaries |
| **Re-exploration rate** (second exploration pass over covered ground) | Return schema too aggressive; usually the dominant hidden cost of subagent isolation |
| **Cost per resolved task** | Whether added stages pay for themselves |
| **pass@1 at short vs long context, same task set** | The delta *is* the rot budget — tells you where in session length the harness starts losing |
| **Human intervention rate** | Real-world usability, uncaptured by pass rates |

Behavioral rot signals worth alerting on: agent re-reads files it already has; contradicts its own earlier decision; reverts a fix it made earlier in the session.

**Build a fixed 50–100 task suite from the actual target repos, graded by execution** (fail-to-pass plus pass-to-pass). Public benchmark numbers do not transfer — the same model varies 10–20 points across harnesses, and most published leaderboard scores are vendor self-reported.

---

## 8. Confidence tiers

Apply these directives with force proportional to the evidence.

**Tier A — measured, reproducible. Apply directly.**
- Test-first with human-written/held-out tests substantially outperforms self-generated tests (roughly 26-point spread in one controlled study on the same architecture)
- Reward hacking scales with code size (~27–28pp validation-vs-holdout gap growth per 10× LOC) and worsens with weaker models
- Hardened verification sharply reduces hacked resolutions and raises clean resolution rate
- Minimal harnesses gain *more* from a model upgrade than rigid, heavily structured ones
- Multi-agent coordination turns net-negative once single-agent baselines are already strong
- Context degradation begins well below window limits, across many models
- Heavyweight spec pipelines can cost ~2× the tokens of lightweight ones for a less complete result

**Tier B — plausible, unproven. Apply, but measure.**
- AST/LSP tooling improves resolve rate (no clean published ablation isolating it)
- Spec-driven development helps on genuinely underspecified greenfield work (the benchmarks that exist mostly *hand the agent a spec* in the form of an issue, so they structurally cannot measure this)
- Language-specific model routing (only valid with local measurement)
- Supersession-based eviction

**Tier C — do not treat as evidence.**
- Vendor leaderboard scores and framework comparison posts authored by the framework vendor
- Persona-prompting benefits
- Any claim that a specific framework is required

---

## 9. Where these directives stop applying

- **If the base model gets substantially stronger:** scaffolding value drops further, not rises. Re-test whether stages still pay for themselves rather than accumulating them.
- **If a cheaper model is routed in:** the reward-hacking gap widens. Tighten the holdout, do not loosen it.
- **If task horizon grows:** planning value rises with length, and so does rot. Both sides of the trade shift.
- **If the local eval suite contradicts a directive here:** the local suite wins. It is measuring the actual repos; every number behind this document was measured on someone else's.
