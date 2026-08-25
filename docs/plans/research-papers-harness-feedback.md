# Research-paper feedback for the Anvil Coding Fleet harness

Scope: five papers in `research-papers/`, read against the harness in this repo
(`harness-agents/canonical/catalog.json`, `guard/`, `controlplane/`, `runplane/`,
`codingfleet/render.go`) and the directives we just adopted
(`docs/plans/agentic-harness-directives-adoption.md`, source
`agentic-harness-directives.md`).

---

## 0. Premise correction: there are no annotations in these PDFs

The task briefed these as "annotated PDFs" whose "handwritten annotations are the
reason they were selected," and instructed me to call out what the annotations
emphasize. **That premise is false for all five files, and I verified it three ways
rather than inventing annotation content:**

1. Rendered every page of all five PDFs (122 pages) to images and inspected them
   (contact sheets + full-resolution reads of the design-critical paper, TDD-Agent).
   No handwriting, highlights, underlines, circles, or margin notes appear anywhere.
2. Decompressed each PDF (`qpdf --qdf --object-streams=disable`) and grepped for
   markup annotation objects (`/Ink /Highlight /FreeText /Text /Popup /StrikeOut
   /Underline /Square /Caret /Stamp`). **Zero** in every file. Every `/Annot` object
   is a `/Subtype /Link` (the arXiv hyperlinks). No annotation `/Contents` text
   exists.
3. Checked producer metadata: all five are clean arXiv originals
   (`Creator: arXiv GenPDF …`, figures by Matplotlib). Meta-Harness was additionally
   passed through Ghostscript (a common annotation-flattening path), so I looked
   hardest there — still nothing flattened onto the pages.

The `-with-annotations` suffix in the filenames does not correspond to any content
in the files. The rest of this report is therefore built on the papers' own
substance (abstract/method/results/ablations/limitations), which is what should
drive harness changes anyway. Where the brief asked "what do the annotations
highlight," I substitute "what the paper's own emphasis is that plausibly motivated
its selection," and say so.

If the intent was to react to specific highlighted passages, the annotation layer
needs to be re-exported — the current files are pristine.

---

## 1. TDD-Agent: Test-Driven Reasoning for Code Generation

**(a) Mechanism/claim.** A *single agent* that (Phase 1) writes executable unit
tests before any implementation, then (Phase 2) runs a *dual-track* loop that
refines **both code and tests** from execution feedback until it self-terminates or
hits an iteration cap (§2.1, Fig 2). Tests are treated "not as fixed validators but
as evolving reasoning artifacts" (§4.3). On LiveCodeBench a bare test-first prompt
beats CoT/SCoT/Self-Planning (Table 1); the full agent beats mini-SWE-agent/RAG/
RepoCoder on RepoEval (Table 2, e.g. DeepSeek 90.77 vs 84.18).

**(b) What the paper emphasizes (no annotations exist).** Two results are the load-
bearing ones for us. **Ablation Table 4:** the "Single-track" variant — test-first
but with tests *frozen during refinement* — markedly underperforms the full dual-
track agent (GPT 70.11→78.24, DeepSeek 79.56→90.77, Qwen 57.36→59.34). **Failure
analysis Fig 6:** the dominant failure mode is *matched failures* (90.9% / 92.9% /
70.8% of failures) — code passes the agent's own generated tests but fails the
held-out repository oracle. They call this "false-positive verification": tests and
code "co-evolve into an internally consistent but incomplete state" (§4.5).

**(c) Concrete proposals for our harness.**
- **Reframe `reseal` from an exception into a first-class dual-track step.** Our
  contract (`agentic-harness-directives-adoption.md` §3.2: "Amending a sealed test
  is allowed *only via* `reseal --reason`") treats test amendment as a rare,
  slightly-suspect escape hatch. TDD-Agent's Table 4 is direct evidence that
  *refining tests during implementation is where a large share of the gain lives* —
  freezing them (our current default) is exactly the "Single-track" arm that loses
  8–11 points. Keep the audit trail (`TestSeal.Amendments` in
  `controlplane/verification.go:79`, Code Review must inspect it), keep the red-
  property (a reseal's new test must have failed before the fix), but stop treating
  a reseal as a smell. Touch: adoption §3.2 wording, `guard/` `reseal` UX, the
  Builder and Code Review rendered definitions.
- **Add a test-strength signal after GREEN.** §4.3 shows iterative refinement lifts
  coverage and mutation score, and §4.1's early-termination analysis shows models
  stop too early on self-test success. Add an optional coverage/mutation check to
  `anvil-guard verify` (or the toolchain verifiers) so "GREEN" can be qualified by
  test strength, and prompt the Builder to strengthen tests before finishing.

**(d) Relation to adopted directives.**
- **Corroborates** the single-agent decisions (Debugger folded into Builder,
  implement-in-parent; adoption Phase 3) — TDD-Agent is deliberately single-agent
  "without the complexity overhead of coordinating multiple agents" (§1), matching
  directives 3.3/3.6.
- **Corroborates** directive 1.4 / 1.3 / §7: agent-written tests carry a lower
  guarantee, and the validation-minus-holdout gap is the primary metric. Fig 6 *is*
  that gap, and it is enormous with self-generated tests.
- **Does not contradict** directive 1.2 (forbid modifying committed tests), because
  1.2 assumes *human/held-out* tests are the gate. But it **corrects our framing**:
  our seal protects agent-generated tests in the bounded direct route (adoption
  Phase 3: "RED — write or extend tests" then seal), so we are freezing the agent's
  own possibly-incomplete spec — the precise thing TDD-Agent shows co-evolves into
  false-positive verification. The fix is not to unfreeze in-loop (that reopens
  reward-hacking); it is (i) make reseal a normal dual-track move under review, and
  (ii) lean harder on the held-out oracle to catch matched failures.

**(e) Rating.** Effort **M** · Impact **H** · Confidence **H** (Table 4 is a clean
ablation; the matched-failure result is directly measured and Tier-A-consistent).

---

## 2. CodeSpec: Dual Executable Specifications for Long-Horizon Feature Development

**(a) Mechanism/claim.** For feature work in an existing repo, CodeSpec builds an
*evidence-grounded functional chain* (pairs each sub-requirement with repository
evidence — design patterns, call relations, dependencies) and compiles each chain
into **two executable specifications**: an *architecture spec* of structural
conformance checks (`CheckUnit`, `CheckRelation`, `CheckDataFlow`) and a *behavior
spec* of tests (`CheckOutput`, `CheckBoundary`, `CheckState`). Both run every
iteration and emit localized violation feedback; the agent iterates under their
joint constraint until both pass or budget K is exhausted (Algorithm 1). On
FeatureBench it beats Claude Code / Mini-SWE-Agent / OpenHands / RTADev
(70.7/55.0/49.9 vs Claude Code 59.8/47.0/41.1, Table 1).

**(b) What the paper emphasizes.** **RQ3 (Fig 3) is the crux:** `CodeSpec (Text)`
uses the *same* functional-chain reasoning but represents the design as **text**
instead of executable checks. On short tasks all approaches tie; the gap *widens
with task length* — 71.8% vs 43.8% on 3,000–5,000-word instructions, +14–15 points
beyond 200 turns. Textual plans are "passive context … overlooked during extended
interactions"; executable specs give "lightweight executable feedback throughout."
Ablation Table 3: removing all specs 70.7→62.6; behavior spec matters more than
architecture spec, but both are complementary.

**(c) Concrete proposals for our harness.**
- **Make the Planner's spec stage produce executable checks, not prose — for the
  multi-file/feature regime.** Our Planner emits `plan.md` (short prose) or the HTML
  plan pipeline. CodeSpec's RQ3 says prose plans are precisely the weak "passive
  context" that decays over long horizons — the regime where our bounded review loop
  is already weakest. For multi-file feature work, the Planner should emit a small
  set of executable behavior tests **plus** structural assertions.
- **Add an architecture-conformance check kind to the guard/toolchain.** We have the
  behavior half (guard tests) but nothing like CodeSpec's architecture spec. Wire
  the structural-search tooling we already list but never gate on (`ast-grep` in
  `scripts/bootstrap-tools.sh`; directive 5.2 / adoption gap **G10**) into a
  mechanical check: e.g. "`on_start` must call `create_mlflow_span`", "module X must
  import Y", expressed as `ast-grep` patterns or LSP find-references assertions,
  checked like tests. This is net-new: `guard/guard.go` records only seal-red /
  green / diff-review today. It would add a `GuardRecord` kind and a
  `controlplane/result.go` evidence type beside `DiffReview` / `TestSeal`.

**(d) Relation to adopted directives.**
- **Corroborates and sharpens** our amendment "evidence must resolve to guard
  records, not agent text" — CodeSpec is literally "make the design resolve to
  executable checks, not prose."
- **Extends** directives 2.1–2.3/2.5 (plans on disk, treat specs as code): CodeSpec
  says for long-horizon feature work the spec should be *executable*, and this is
  where the largest measured gain sits. It upgrades the confidence on directive
  Tier-B "spec-driven development helps" specifically along the executable-vs-textual
  axis (a controlled comparison the directives noted was missing).
- **Realizes** directives 5.1/5.2 (symbol resolution / AST rewrite) as a gate rather
  than a convenience.

**(e) Rating.** Effort **H** · Impact **H** (feature/greenfield regime) · Confidence
**M-H** (clean RQ3 ablation; modest cost, +$0.01–0.03/task).

---

## 3. Agentic Harness Engineering (AHE): Observability-Driven Automatic Evolution

**(a) Mechanism/claim.** A closed loop that *automatically evolves* a coding-agent
harness while the base model is frozen, via three "observability pillars":
**component** (harness = seven editable file-level component types with git-commit
rollback), **experience** (an "Agent Debugger" distills ~10M raw trajectory tokens
into a ~10K layered, drill-down evidence corpus), and **decision** (a change
manifest pairs every edit with a self-declared prediction of fixes *and* at-risk
regressions, verified against next-round task deltas; ineffective edits reverted at
file granularity). Ten iterations lift Terminal-Bench 2 pass@1 69.7%→77.0%, beating
human-designed Codex (71.9%) and self-evolving ACE/TF-GRPO; the frozen harness
transfers to SWE-bench-verified with **12% fewer tokens** and +5.1–10.1pp
cross-family (§4.2–4.3).

**(b) What the paper emphasizes.** Three findings bear directly on us. **Component
ablation (Table 3):** the gain lives in **tools, middleware, and long-term memory**;
**system-prompt-only is the sole regression (−2.3pp)** — "factual harness structure
transfers … whereas prose-level strategy does not." **Non-additivity (§4.4.1):**
three positive single-component gains sum to +11.1pp but full AHE is only +7.3pp,
and on Hard tasks memory-only *beats* full AHE — stacking edits that push the same
"closure-style verification" wastes turns on redundant re-checks. **Regression
blindness (§4.4.2, Fig 4):** the loop's fix-prediction is evidence-driven (precision
33.7% / recall 51.4%, ~5× random) but its regression-prediction is near-random
(11.8% / 11.1%, ~2× random) — "it cannot reliably name the tasks the same edit is
about to break." Prompt-only self-evolvers (ACE/TF-GRPO) actually *regress below the
seed on transfer while spending 11–29% more tokens* (§4.2).

**(c) Concrete proposals for our harness (bears on the externalized eval/Factory).**
- **The externalized improvement process must gate on a held-out regression signal,
  not on the improver's self-prediction.** AHE's central negative result is that an
  otherwise-good improver is *blind to what it breaks*. Our decision to keep a
  held-out SWE-bench holdout (LXC 135) is the right instrument — but only if
  catalog/tier changes are *accepted or reverted by that holdout*, not by an agent's
  rationale. This is a design constraint on the separate process, not on this swarm.
- **Concentrate harness investment in structural surfaces (guard, hooks, skills,
  toolchain verifiers, middleware), and treat agent-prose edits as suspect.**
  Table 3 is strong evidence that the leverage is not in `catalog.json` role
  instructions. This *validates* our recent build direction (the `anvil-guard`
  binary, the three-harness hooks, skills-on-foreign-dispatch) and argues for moving
  *more* behavior out of agent prose into executable middleware/hooks.
- **Watch for non-additive interference among our verification layers.** We stack
  guard PreToolUse + PostToolUse + Stop-check + a Code Review pass + a 2-pass
  verification budget. AHE shows overlapping verification stages cap aggregate gain
  and burn budget. The external eval should score the *whole-harness aggregate* on
  LXC 135, not sum single-component wins.

**(d) Relation to adopted directives.**
- **Strongly corroborates** directive 3.1 (persona/prose adds no capability) and G1/
  G9 (persona subagents, prompt bloat) — the 44→10 collapse is the right move, and
  the system-prompt regression says prompt tuning is the *lowest*-value surface.
- **Corroborates** the trust boundary: AHE's improver has read-only verifier/model/
  config and a non-deletable seed prompt, exactly our "orchestrator forbidden from
  consuming scorers or hidden tests" and the externalized Factory/eval.
- **New, not in the directives:** *regression foresight* is unsolved by prediction —
  handle it with a held-out gate (see Self-Harness), and *non-additivity* means more
  scaffolding is not monotonically better (echoes directive §9: re-test whether
  stages still pay for themselves).

**(e) Rating.** Effort **H** (design of the external loop) · Impact **H** ·
Confidence **H** (regression-blindness and component ablation are cleanly measured).

---

## 4. Meta-Harness: End-to-End Optimization of Model Harnesses

**(a) Mechanism/claim.** An outer loop whose *proposer is a coding agent* (Claude
Code + Opus-4.6) with **full filesystem access to every prior candidate's source,
scores, and execution traces** (grep/cat, ~82 files/iteration). The thesis: existing
text optimizers compress feedback to scalars/summaries/short templates (0.002–0.026
MTok/iter, Table 1); harnesses act over long horizons, so compression removes the
signal needed to trace failures to earlier decisions. Meta-Harness gives the proposer
~10 MTok/iter of raw experience. Beats ACE by 7.7pts with 4× fewer context tokens on
text classification, +4.7pts across five held-out models on math retrieval, and #1
Haiku-4.5 / #2 Opus-4.6 on TerminalBench-2 (Tables 2, 6, 7).

**(b) What the paper emphasizes.** **Interface ablation (Table 3) is decisive:**
scores-only 34.6/41.3 and scores-plus-summary 34.9/38.7 vs full-with-traces
50.0/56.7 — "access to raw execution traces is the key ingredient … summaries do not
recover the missing signal, and may even hurt by compressing away diagnostically
useful details." Also: code-space search is *self-regularizing* (coding models
propose coherent algorithms, not brittle hacks) and *inspectable* (brittle if-chains
are visible, unlike weight-space overfitting); and the proposer, when structural +
prompt edits both regressed, *isolated the prompt confound and pivoted to a safe
structural edit* (§4.3) — the same lesson as AHE.

**(c) Concrete proposals for our harness.**
- **Architecture template for the externalized improvement process:** it is
  essentially Meta-Harness — point a coding agent (our own fleet) at the harness's
  own source (`catalog.json`, rendered defs, `guard/`, hooks) with full-trace access,
  let it propose edits, gate on the LXC 135 holdout. We already have the substrate
  (git) and the proposer (the fleet).
- **Do not over-compress the *diagnostic* evidence path.** Our recent moves —
  "Research returns pointers not prose" (G6), "evidence must resolve to guard
  records not agent text," `CommandEvidence` storing argv + stdout **digests**
  (`controlplane/result.go:35`) — are right for *localization* and *anti-forgery*,
  but Meta-Harness Table 3 warns that *diagnosis* needs raw traces. The `runplane`
  supervisor already captures worker streams; retain them (not just digests) for the
  Code Review / Debugger-in-Builder / external-eval consumers.

**(d) Relation to adopted directives.**
- **Corroborates** directives 4.1/4.2 (externalize state to filesystem, access
  adaptively) and the anti-prompt stance.
- **Refines** directive 3.4/3.5 and our "pointers not prose": those are correct for
  *localization* (compresses well), but Meta-Harness shows *diagnosis/root-cause*
  does **not** compress — keep raw traces available for that consumer. This is a
  nuance, not a contradiction: pointers for "where," traces for "why."

**(e) Rating.** Effort **H** (if we build the loop) · Impact **H** · Confidence
**M-H** (Table 3 ablation is clean; the TerminalBench-2 run searched and evaluated on
the same 89 tasks, which the authors flag and audit — a caveat on that specific
number).

---

## 5. Self-Harness: Harnesses That Improve Themselves

**(a) Mechanism/claim.** A fixed model improves *its own* harness (no stronger
external agent) via a three-stage loop (Algorithm 1): **Weakness Mining** clusters
failed traces by a *verifier-grounded failure signature* φ = (terminal verifier
cause, causal status of the agent behavior, abstract mechanism) into an evidence
bundle that deliberately does **not** prescribe an edit; **Harness Proposal**
generates K *diverse-yet-minimal* candidate edits, each tied to one mechanism and one
editable surface, no broad rewrites; **Proposal Validation** promotes an edit only if
`Δ_held-in ≥ 0 ∧ Δ_held-out ≥ 0 ∧ max(Δ) > 0` (§3.4). Across 9 model×benchmark
combos every final harness improves both splits (Table 1), up to +40.6pp / +132%,
with no promoted harness degrading either split.

**(b) What the paper emphasizes.** The **acceptance rule** is the answer to AHE's
regression blindness: rather than *predicting* regressions, it *gates* on a held-out
split the proposer never sees (§3.4, Algorithm 1 lines 11–13). Model and evaluator
are held fixed so record changes are attributable to the harness; the evaluator is
kept *distinct from the optimizer*. Retained edits are structural and model-specific
(Fig 4–6): tool-error-triggered middleware guards, runtime caps ("redirect after 50
tool calls"), dependency-verifier skills, artifact-ensure subagents, local-test
enforcement — explicitly "more than making the prompt longer" (§1). The initial
harness (Fig 3) is a minimal file exposing *named editable surfaces* (system prompt,
memory, subagents, skills, bootstrap/execution/verification/failure-recovery
instructions, runtime-control policy).

**(c) Concrete proposals for our harness.**
- **Adopt the Self-Harness acceptance rule verbatim in the externalized process:**
  promote a catalog/tier/guard change only if held-in does not regress *and* held-out
  does not regress *and* at least one improves. This is the concrete gate for LXC
  135. It is strictly safer than AHE's predict-and-revert.
- **Cluster our own failures by a verifier-grounded signature.** Our guard already
  produces the raw material (verifier cause via `CheckEvidence`/exit codes; the diff;
  the seal). A Weakness-Mining pass over guard records + retained runplane traces
  would turn per-run evidence into reusable failure patterns for the external
  improver — and its φ (verifier cause vs agent mechanism) is a good schema for the
  Code Review pass to emit, too.
- **Expose the catalog as named editable surfaces with per-edit rollback.**
  `catalog.json` + git already gives this; Self-Harness/AHE confirm it is the right
  substrate and that edits should be *minimal and single-surface*, not rewrites.

**(d) Relation to adopted directives.**
- **Corroborates** the trust boundary (evaluator distinct from optimizer; held-out
  gate) — our externalization of evaluation + Factory is the same architecture.
- **Corroborates** minimal-seed and structural-over-prose.
- **New:** the model-specificity claim ("effective harness design is inherently
  model-specific") bears on our tiers — see roadmap item 6.

**(e) Rating.** Effort **M-H** · Impact **H** · Confidence **H** (nine consistent
combos; the acceptance rule is simple and directly transferable).

---

## 6. Was externalizing evaluation + Factory the right call?

**Directionally yes, for the trust reason — but "externalized" must mean "runs the
loop elsewhere," not "no loop."** All three self-improvement papers enforce the same
invariant we did: the thing being improved must not control its scorer (AHE's
read-only verifier/model/config; Self-Harness's evaluator-distinct-from-optimizer;
Meta-Harness's proposer never sees the test set). Keeping evaluation and the Factory
out of this swarm, and forbidding the orchestrator from consuming scorers/hidden
tests, is exactly that invariant. Keeping the LXC 135 held-out is exactly
Self-Harness's regression gate and directive 1.3.

The risk is under-building the external process. The papers show harness improvement
is a measured +7 to +40pp lever, and they pin down *how* it has to work:

1. **Gate on held-out non-regression, not on self-prediction** (Self-Harness §3.4
   beats AHE §4.4.2).
2. **Feed the improver raw traces, not summaries** (Meta-Harness Table 3).
3. **Edit structural surfaces — tools/middleware/memory/guard/hooks — not prose**
   (AHE Table 3; Meta §4.3; Self-Harness §1).
4. **Minimal seed, minimal single-surface edits, git rollback, auditable manifest**
   (all three).
5. **Score the whole-harness aggregate; expect non-additivity** (AHE §4.4.1).

If the external process does only "run SWE-bench and eyeball," we have kept the trust
boundary but discarded the mechanism the papers actually validate. The Meta-Harness
architecture — a coding agent proposing edits to `catalog.json`/rendered defs/`guard`
with full-trace access, gated by the holdout — is the template, and we already own
both the substrate (git) and the proposer (the fleet).

---

## 7. Prioritized cross-paper roadmap

Ordered by (impact × confidence) / effort. Each names its mechanism, the component it
touches, and a rating.

1. **Held-out non-regression gate for the externalized improver.**
   *Mechanism:* Self-Harness acceptance rule (`Δin≥0 ∧ Δho≥0 ∧ max>0`, §3.4) as the
   fix for AHE regression blindness (§4.4.2). *Touches:* the separate eval process +
   LXC 135 holdout; the swarm side only needs to keep guard records + traces
   consumable. *Effort M · Impact H · Confidence H.*

2. **Reframe `reseal` as first-class dual-track test refinement (stop freezing the
   agent's own spec).** *Mechanism:* TDD-Agent Table 4 (single-track/frozen loses
   8–11pts) balanced against Fig 6 (matched failures). *Touches:* adoption §3.2
   wording, `guard/` reseal UX, `controlplane/verification.go` `TestSeal.Amendments`,
   Builder + Code Review rendered defs. *Effort M · Impact H · Confidence H.*

3. **Preserve raw execution traces for diagnostic consumers.** *Mechanism:*
   Meta-Harness Table 3 (traces are the key ingredient; summaries hurt). *Touches:*
   `runplane` supervisor (retain worker streams), `controlplane/result.go` (keep raw
   alongside `CommandEvidence` digests), Code Review / Debugger-in-Builder / eval
   intake. Keep pointers/digests for localization/anti-forgery. *Effort M · Impact M
   · Confidence M-H.*

4. **Concentrate harness investment in structural surfaces; treat prose edits as
   low-value.** *Mechanism:* AHE Table 3 (system-prompt-only regresses; gain is in
   tools/middleware/memory), Meta/Self corroborating. *Touches:* keep `catalog.json`
   role instructions lean; move behavior into `anvil-guard`, hooks, skills, toolchain
   verifiers. Validates the persona-collapse and the guard/hooks build. *Effort L-M ·
   Impact M-H · Confidence H.*

5. **Executable architecture-conformance check for multi-file/feature work.**
   *Mechanism:* CodeSpec dual executable specs; RQ3 executable≫textual, gap grows
   with horizon (Fig 3). *Touches:* new `GuardRecord` kind in `guard/guard.go`, new
   evidence type in `controlplane/result.go` beside `DiffReview`/`TestSeal`, Planner
   contract, toolchain-* verifiers, wire `ast-grep`/LSP (closes gap **G10**). *Effort
   H · Impact H (feature regime) · Confidence M-H.*

6. **Tier-aware scaffolding + measure verification-layer interference.** *Mechanism:*
   AHE cross-model (weaker/cross-family bases gain most: +10.1 deepseek vs +2.3
   GPT-5.4) + directive §9 (cheaper model → widen holdout) + AHE non-additivity
   (§4.4.1). *Touches:* create the not-yet-existent named-tier file (`routingTier` is
   still only `advanced|standard` in `catalog.json`); give Quick/Workhorse tiers more
   guard/middleware structure and a tighter holdout weight; measure whether guard
   Pre/Post/Stop + Code Review + 2 passes overlap. Also weigh whether the external
   process should emit per-provider harness variants (harness is model-specific —
   Self-Harness §1, AHE §1). *Effort M · Impact M · Confidence M.*

7. **Surface the matched-failure (validation-minus-holdout) gap as the primary
   metric, with a test-strength signal.** *Mechanism:* TDD-Agent Fig 6 + §4.3 +
   directives 1.3/§7. *Touches:* external eval computes the gap per run; optional
   coverage/mutation check in `anvil-guard verify`; Builder prompted to strengthen
   tests before finishing. *Effort M · Impact M-H · Confidence H.*

---

## 8. Where the papers suggest we got something wrong

- **`reseal`-as-exception is the clearest miscalibration.** TDD-Agent Table 4 shows
  frozen-test refinement ("Single-track") is the losing arm; our adoption frames test
  amendment as "allowed *only via* `reseal --reason`" and as Code-Review-scrutinized
  evidence. The seal is correct as anti-hacking, but the *framing* under-weights the
  dual-track gain. Fix per roadmap #2. (Nuance: do not unfreeze in-loop — that
  reopens reward hacking; make reseal normal-but-audited and lean on the holdout.)

- **Freezing agent-generated tests without an in-loop holdout signal is a hidden
  tax.** In the bounded direct route the Builder writes the tests and seals them, so
  we freeze the agent's own possibly-incomplete spec (TDD-Agent's matched-failure
  mode, Fig 6). The holdout that would catch it lives only in the externalized eval,
  so the swarm declares success while the matched-failure tax is invisible until a
  later external run. At minimum, weight the holdout more heavily for agent-generated
  tests (directive 1.4) and consider a lightweight test-strength gate (#7).

- **Compressing the *diagnostic* evidence path risks starving it.** "Pointers not
  prose" and "digests not text" are right for localization and anti-forgery, but
  Meta-Harness Table 3 shows diagnosis/self-improvement need raw traces and that
  summaries can *hurt*. Ensure the Code Review / Debugger / eval consumers keep raw
  traces (#3).

- **Externalizing the improvement loop is right only if the external process is a
  real propose→validate→accept loop.** If it degenerates into "score and eyeball," we
  keep the trust boundary but forfeit the measured +7–40pp lever, and any future
  automated catalog edits will hit AHE's regression blindness. Build the loop with
  the held-out gate (#1), raw traces (#3), structural edits (#4), and aggregate
  scoring (#6).

- **Possible (unmeasured) over-stacking of verification layers.** AHE non-additivity
  suggests our guard hooks + Code Review + 2-pass budget may partly re-verify the
  same thing and cap gains. Flagged for measurement (#6), not asserted.
