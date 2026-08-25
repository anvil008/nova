# External improvement loop — held-out non-regression acceptance (design)

Status: **design for review — not yet built.** Phase 4 Lane B. Author: implementer track.

This specifies the externalized `propose → validate → accept` loop that the five
research papers (`docs/plans/research-papers-harness-feedback.md`) say is the *only*
justification for having externalized evaluation + Factory out of the coding swarm.
It runs on **LXC 135** (`ssh anvil@10.0.20.135`, hostname `llm-evaluations`; always
`export LC_ALL=C`) against the datacurve **pier** DeepSWE harness. It reuses the
new-fleet benchmark layout a prior implementer already set up there.

The loop implements **Self-Harness's acceptance rule** — promote a proposed
catalog/tier/guard change only if

```
Δ_held-in ≥ 0  ∧  Δ_held-out ≥ 0  ∧  max(Δ_held-in, Δ_held-out) > 0
```

evaluated on a held-out task split the proposer never sees (Self-Harness §3.4). This
is the fix for AHE's regression blindness (§4.4.2): rather than *predicting*
regressions, we *gate* on a sealed split.

Everything below is a concrete spec (paths, commands, data flow). It does **not**
build the full loop; it is for the user to review first. Where the current
infrastructure does not yet satisfy a paper requirement, it is called out as a
**GAP** with the minimal change needed.

---

## 0. What is actually on LXC 135 today (verified)

| Thing | Path on 135 | Notes |
|---|---|---|
| pier DeepSWE harness source | `/opt/deepswe-smoke/pier-src/`, installed into `/opt/evals/venv` | `pier view jobs` CLI available |
| DeepSWE task pool | `/opt/deepswe-smoke/deep-swe/tasks/` | **117 tasks** + `dataset.toml`, `README.md`, `PROVENANCE.md` |
| New-fleet bridge adapter | `/opt/deepswe-smoke/pier_swarm_adapter_v2/` | `agent.py` (pier `BaseAgent`), `bridge.py`, `runtime_env.py` |
| Shared swarm engine | `/opt/evals/swarm/engine.py` (1712 lines) | middleware / runtime-control / verification surface; no Langfuse/OTEL wiring |
| Rendered fleet catalog (what the eval consumes) | `/opt/evals/agents-v2/<role>/agent.md` | 15 roles, "antigravity rendered agent.md prompts" |
| Benchmark run configs | `/opt/deepswe-smoke/configs/*.json` | e.g. `deepswe-v1.1-swarmv2-gemini37-10-seed0.json` |
| Completed baseline run | `/opt/deepswe-smoke/jobs/deepswe-v1.1-swarmv2-gemini37-10-seed0/` | 10 trials (5 tasks × `n_attempts=2`), 1h18m, $14.40 |
| Orchestrator launch logs | `/opt/evals/logs/launches/*.log` | operational, not per-trial trajectories |
| Eval summaries / projections | `/opt/evals/results/`, `/opt/evals/evaluation_projection.py` | `latest_evaluation_summary.json`, schema |

Container capacity: 8 vCPU / 16 GiB, **~14 GiB free RAM**, 17 G free disk. No Docker
daemon *for the improver* — pier spins its own task containers via `public.ecr.aws`
images. The `load average ~58` seen over SSH is the **Proxmox host's** aggregate
(LXC `/proc/loadavg` reports the host); this container itself is near-idle.

**Baseline result (new 15-role fleet, gemini-3.7-flash):** reward **0/5** distinct
tasks (every task `f2p_passed = 0`), partial-credit mean ≈ **0.72**, 1 `RuntimeError`
trial. This is the number the loop must move.

---

## 1. Trust invariants (non-negotiable, from all three self-improvement papers)

1. **Model held fixed.** `gemini/gemini-3.7-flash`, `thinking_budget=65535`,
   `MESSAGE_LIMIT=200` — identical across baseline and every candidate. Only the
   harness changes, so a reward delta is attributable to the harness (Self-Harness
   §3.4; AHE frozen-base).
2. **Evaluator held fixed and distinct from the proposer.** The verifier is pier's
   own per-task test oracle (`reward.json` / `ctrf.json`), never an LLM judge and
   never the proposing agent. The proposer is a coding agent from *this* fleet; it
   may read harness source and **held-in** traces only.
3. **Held-out split is sealed from the proposer.** The proposer's filesystem view,
   its trace corpus, and its prompt must contain **zero** held-out task content —
   not the task dirs, not held-out traces, not held-out scores. Enforced by running
   proposal generation under a user that cannot read the held-out task/trace paths
   (see §6.3).
4. **Minimal, single-surface edits with git rollback.** Every candidate is one
   coherent edit to one editable surface, on its own git branch, revertible at file
   granularity (AHE §4.4; Self-Harness §3.3; Meta-Harness §4.3).
5. **Aggregate scoring, not summed single-component wins** (AHE non-additivity
   §4.4.1). The gate scores the whole harness on both splits.

---

## 2. The harness-under-eval, and its editable surfaces

The thing being improved on 135 is **the rendered fleet catalog + the swarm engine**,
because that is exactly what pier executes:

```
pier trial → pier_swarm_adapter_v2.agent → bridge.py subprocess
           → engine.py (SwarmFleetRegistry over /opt/evals/agents-v2)
           → executes the 15-role fleet against the task's docker workspace
           → returns final patch; pier's verifier scores it
```

**Editable surfaces a proposal MAY touch** (in descending research-backed value —
AHE Table 3 says structure ≫ prose):

| Surface | Location on 135 | Canonical source in repo | Value |
|---|---|---|---|
| Engine middleware / runtime caps / verification enforcement | `/opt/evals/swarm/engine.py` (`max_tool_rounds`, terminalization reserve, `MessageBudget`, `record_command`) | `guard/`, `controlplane/`, `runplane/` (Go) — see GAP-1 | **High** (tools/middleware/caps) |
| Model tiers | `modelTiers` in `catalog.json` (`quick`/`workhorse`/`powerhorse` × provider) | `harness-agents/canonical/catalog.json` | Medium-High |
| Role boundaries / activation / capabilityMode / harnessTargets | per-role fields in `catalog.json`, rendered into `agent.md` | same | Medium |
| Role `instructions` (prose) | per-role in `catalog.json` → `agent.md` | same | **Low** (system-prompt-only was AHE's *only* regression) |
| Authority profiles | `authorityProfiles` (5) in `catalog.json` | same | Medium |

`catalog.json` schema (verified): top-level `apiVersion, catalogVersion,
generatedAt, source, authorityProfiles, modelTiers, roles[15], knowledgeRoles`.
Each role: `id, name, class, summary, status, instructions, activation, boundaries,
evidence, tags, routingTier(quick|workhorse|powerhorse), capabilityMode,
harnessTargets`.

`catalog.json` → rendered `agent.md` is deterministic via
`codingfleet.Render(repoRoot, document)` (`codingfleet/render.go:66`). A proposal
that edits `catalog.json` must re-render before scoring so the eval consumes it.

### GAP-1 — the eval harness and the production harness are two implementations

The **eval** runs a Python `engine.py`; the **production** swarm runs the Go
`guard/` + `controlplane/` + `runplane/`. A change to the Go **guard** binary is
*not exercised* by the 135 eval, and a change validated only against `engine.py`
does not automatically hold for production. Two honest options, **user decision
required (D-1)**:

- **(a) Gate on the surfaces the eval truly exercises** — `engine.py` middleware +
  `catalog.json` roles/tiers (rendered). Guard/hook changes are validated
  *indirectly* by porting the same behavioral rule into `engine.py`, scoring it,
  and only then hand-porting the accepted rule into the Go guard. Cheapest; keeps
  the loop runnable now.
- **(b) Make the eval run the production harness** — replace the bridge so pier
  drives the real Go `runplane` + `guard`. Faithful for guard/hook proposals, but a
  larger build (the bridge currently talks to `engine.py`, not `runplane`).

This doc specifies **(a)** as the near-term loop and marks (b) as the faithful
end-state. Accepted `engine.py`/catalog edits that correspond to a production
surface are recorded in the manifest with a `portTo` field naming the Go file to
mirror.

---

## 3. Held-in / held-out task split

**Pool:** the 117 dirs under `/opt/deepswe-smoke/deep-swe/tasks/` (exclude
`README.md`, `dataset.toml`, `PROVENANCE.md`, `LICENSE`).

**Split:** deterministic, seeded, 50/50, computed once and frozen:

```bash
# scripts/split_pool.py (to be added under /opt/evals/improver/)
# held-out membership = sha256("deepswe-split-v1:" + task_name) low bit
export LC_ALL=C
ls /opt/deepswe-smoke/deep-swe/tasks/ \
  | grep -vE '^(README\.md|dataset\.toml|PROVENANCE\.md|LICENSE)$' \
  | python3 split_pool.py --seed deepswe-split-v1 \
      --held-in  /opt/evals/improver/splits/held_in.txt \
      --held-out /opt/evals/improver/splits/held_out.txt
```

- The split file is written **once**, committed to the improver's git repo, and
  never regenerated (regenerating would leak held-out tasks into future held-in
  proposer views). ≈ 58/59 tasks per side.
- **Working subsets** for cost control: the gate does not need all ~58 per side
  every round. Define fixed, seeded subsets `held_in.N.txt` / `held_out.N.txt`
  (e.g. N=15 each) sampled deterministically from the frozen split, so held-in and
  held-out are always disjoint and stable across rounds. The current 5-task config
  is a smoke subset only — too small for a non-regression signal (see §5.3 on
  statistical adequacy).
- **Attempts:** keep `n_attempts=2` (as in the baseline config) so per-task reward
  is `mean over attempts`, reducing single-sample noise. Score at pass@1 (mean
  reward), not pass@k, to match the acceptance rule's intent.

Rationale for a *task-level* (not attempt-level) split: the proposer mines failure
patterns from whole tasks' traces; a held-out task it has never seen the traces of
is the true regression probe.

---

## 4. Proposal generation (Meta-Harness template)

One candidate = one coding-agent session that reads the harness and the **held-in**
evidence bundle and emits **one minimal single-surface edit** + a manifest.

### 4.1 Proposer inputs (full raw-file access — Meta-Harness Table 3)

The proposer is launched with read access to, and is explicitly pointed at:

- **Harness source under eval:** `/opt/evals/agents-v2/**` (rendered defs),
  `/opt/evals/swarm/engine.py`, and the canonical `catalog.json` + `guard/` in a
  checked-out copy of this repo.
- **Held-in raw traces** (see §7): per-trial `result.json`, `artifacts/model.patch`,
  `verifier/reward.json`, `verifier/ctrf.json`, `verifier/test-stdout.txt`,
  `verifier/run.log`, `trial.log`, and (once GAP-2 is closed) the swarm
  `transcript.jsonl`. Access is by `grep`/`cat` over files, **not** summaries —
  Meta-Harness §4: "summaries do not recover the missing signal, and may even hurt."
- **The held-in weakness-mining bundle** (§8): φ-clustered failure signatures.
- **NOT** anything under the held-out task or held-out trace paths.

### 4.2 Proposer instruction (template)

> You are improving a coding-agent harness whose model is frozen. Here is the
> harness source (paths above) and the held-in failure evidence (φ clusters +
> raw traces). Propose **exactly one** minimal edit to **one** surface that you
> predict will fix one named failure mechanism without breaking working tasks.
> Do not rewrite; prefer a structural edit (middleware / cap / tier / boundary)
> over a prose edit. Emit the edit as a git patch plus a `manifest.json`
> (schema in §9) naming the mechanism, the surface, the predicted-fixed φ
> cluster, and the tasks you predict are at risk. You will be scored on a
> held-out split you cannot see; a self-favorable rationale earns nothing.

Generate **K diverse-yet-minimal candidates** per round (Self-Harness: diverse,
each tied to one mechanism/surface). K=3–5 is a reasonable start; each is an
independent branch.

### 4.3 GAP-3 — the proposer must be a *distinct* agent instance

The proposer is a fleet coding agent, but it must be a **separate run** from any
agent inside the harness being scored, and must never receive the evaluator's
hidden signal. Enforced operationally: the proposer session runs on 135 (or the
main box) with the held-out paths `chmod 000` for its user; the scoring harness
runs the fixed engine with no proposer in the loop.

---

## 5. Scoring a candidate

### 5.1 Apply the candidate

```bash
# per candidate branch:
cd /opt/evals/improver/harness      # git working copy
git checkout cand/<id>
# if catalog.json changed, re-render into agents-v2:
go run ./codingfleet/cmd/render ... # or the repo's render entrypoint → /opt/evals/agents-v2
# if engine.py changed, it is used in place by the bridge.
```

### 5.2 Run held-in and held-out through pier

Generate two pier configs from a template (same shape as
`configs/deepswe-v1.1-swarmv2-gemini37-10-seed0.json`), one per split subset,
writing to isolated job dirs:

```bash
export LC_ALL=C
# held-in
pier run --config /opt/evals/improver/configs/cand-<id>-heldin.json     # jobs/cand-<id>-heldin/
# held-out
pier run --config /opt/evals/improver/configs/cand-<id>-heldout.json    # jobs/cand-<id>-heldout/
```

Each config differs from the baseline only in `job_name`, `trials_dir`, and its
`tasks[]` list (the split subset). Model/agent/env/verifier blocks are byte-identical
to baseline.

### 5.3 Aggregate the score

Primary metric per split = **mean reward** (pier's `reward` ∈ {0,1} per trial,
averaged over trials incl. `n_attempts`). Secondary, reported but not gating:
`f2p`, `partial`, and the **validation-minus-holdout gap** (TDD-Agent's matched-
failure signal; roadmap #7). Read from
`jobs/<job>/result.json → stats.evals.*.metrics[0].reward` and per-trial
`verifier/reward.json`.

```
Δ_held-in  = reward(candidate, held-in)  − reward(baseline, held-in)
Δ_held-out = reward(candidate, held-out) − reward(baseline, held-out)
```

**Statistical adequacy:** reward is coarse (currently 0/5). With small N a one-task
flip swings the mean. The gate therefore requires (a) N ≥ 15 per split, and (b) the
non-regression comparison uses the *same fixed task subset and seed* for baseline
and candidate, so Δ is a paired comparison, not two independent means. The baseline
scores for each subset are computed **once** and cached
(`/opt/evals/improver/baseline/{held_in,held_out}.reward.json`) so every candidate
is scored against the identical baseline.

---

## 6. Acceptance gate + rollback

### 6.1 The rule (Self-Harness §3.4, verbatim)

```
accept  ⇔  Δ_held-in ≥ 0  ∧  Δ_held-out ≥ 0  ∧  max(Δ_held-in, Δ_held-out) > 0
```

Ties (Δ = 0 on both) are **not** accepted (no strict improvement). Any regression
on either split is **rejected**, regardless of how large the gain on the other.

### 6.2 Accept / revert flow

```bash
# gate.py reads the two result.json files + cached baseline, computes Δ, decides.
if accepted:
    git -C harness checkout main
    git -C harness merge --no-ff cand/<id>       # promote
    # re-render committed; record accepted manifest
    cp manifest.json /opt/evals/improver/accepted/<catalogVersion>-<id>.json
    # bump catalog.json catalogVersion; this becomes the new baseline harness
else:
    git -C harness branch -D cand/<id>           # discard (git revert semantics)
    cp manifest.json /opt/evals/improver/rejected/<id>.json   # keep for audit
```

Rejected candidates are **kept as audit records** (manifest + Δ), never silently
dropped — a rejected edit is evidence for the next round's weakness mining
(Meta-Harness feeds prior candidates + scores back to the proposer).

### 6.3 Held-out seal enforcement (operational)

- Proposal generation runs as a user/namespace where
  `/opt/deepswe-smoke/deep-swe/tasks/<held-out>` and
  `/opt/evals/improver/traces/held_out/**` are unreadable (`chmod 000` / bind-mount
  omission / separate account).
- The scoring harness is launched by a **different** process than the proposer, and
  never returns held-out per-task detail to the proposer — only the final
  accept/reject boolean and the *held-in* deltas may flow back into the next round.

---

## 7. Raw-trace retention (deliverable #2)

Meta-Harness Table 3: the improver needs **raw traces as files it can grep**, not
summaries. Retention is documented per producer.

### 7.1 What pier already stores durably (verified) — per trial

Under `/opt/deepswe-smoke/jobs/<job>/<trial>/`:

| File | Content | Role for the improver |
|---|---|---|
| `config.json` | agent import path, `model_name`, task path + `task_checksum`, env/verifier config | provenance / reproducibility |
| `result.json` | `agent_info`, `agent_result` (tokens, `cost_usd`, `llm_call_count`), `verifier_result`, `started/finished_at`, `exception_info` | run metadata + usage |
| `artifacts/model.patch` | the git diff the fleet produced | **the action** — what the harness did |
| `artifacts/manifest.json` | artifact manifest | — |
| `verifier/reward.json` | `reward, f2p_total, f2p_passed, p2p_total, p2p_passed, partial` | **the verifier signal** (φ verifier cause) |
| `verifier/ctrf.json`, `reports/{new,base}_ctrf.json` | per-test results (CTRF standard) | which tests failed |
| `verifier/test-stdout.txt` | raw verifier test output | **why** a test failed |
| `verifier/run.log` | verifier execution log | verifier-side errors |
| `trial.log` | docker + collect-hook orchestration | thin; env setup errors |
| `exception.txt` | present on agent/infra failure | crash cause |
| `docker-compose-mounts.json` | mount map | env reproducibility |

These are plain files on the LXC's own disk (not in the deleted docker container —
`environment.delete=true` removes the *container*, not the jobs artifacts). The
10-trial baseline is **5.9 MB**; ~1 KB–1 MB per trial. Retention is essentially
free (17 G free).

### 7.2 GAP-2 — the multi-agent trajectory is NOT retained

**Verified:** `result.json.step_results` and `agent_result.rollout_details` are
**null** for the bridge adapter. The bridge (`bridge.py: run_bridge`) returns only a
`{"type":"final","result":<string>,"usage":{…}}` frame — `result` is the
orchestrator's *final text*, and `agent.py` asserts it "must be text". The swarm's
per-agent messages, tool calls, sub-agent dispatches, and command/guard records live
only in memory inside `engine.py` during the run and are **discarded** when the
bridge exits.

This is precisely the raw trace Meta-Harness requires and it is currently thrown
away. **Minimal fix (specify, do not build yet):** have `engine.py` /
`SwarmFleetExecutionSession` write a JSONL transcript, and the bridge copy it into
the trial dir:

- `engine.py` already accumulates the material (`record_command`,
  `self.commands.append`, per-chat histories, `_send_message`). Add a
  `transcript_path` sink that appends one JSON line per event:
  `{ts, agent_role, kind: message|tool_call|tool_result|dispatch|command|final,
  content_or_digest, tokens}`.
- The bridge writes it to a path the pier trial dir can pick up, e.g.
  `jobs/<job>/<trial>/agent/transcript.jsonl` (the `agent/` dir already exists per
  trial and is currently empty).
- Size bound: cap per-line bytes as `bridge.py` already does for frames
  (`MAX_FRAME_BYTES`); rotate/truncate tool outputs to digests+head/tail like
  `_bounded_text`. Keep **raw** text for reasoning/messages (diagnosis needs it),
  digests only for large binary/stdout blobs (anti-forgery, per repo convention).

Until GAP-2 is closed, the improver's "why did it fail" signal is limited to
`model.patch` + verifier output + the final text — enough for *localization*, thin
for *diagnosis*. Closing GAP-2 is the single highest-leverage retention change and
should precede real proposal rounds.

### 7.3 Production runplane event logs (for completeness)

The production swarm's `runplane` writes to `~/.local/state/swarm-runplane/`
(override `SWARM_RUNPLANE_STATE`): `jobs/<id>.json` (job state) and
`events/<id>.jsonl` (event stream). **These are bounded** — `newStateStore` rings
the event log to `maxEvents` (default **500**) and a byte cap
(`runplane/store.go:125` `appendEvent` trims oldest). They are **operational
telemetry, not durable raw traces**, and are not present on 135 (the eval uses the
bridge, not the runplane supervisor; `~/.local/state/swarm-runplane` is empty
there). The recent `fix: drain worker streams before reaping` ensures worker stdout
is fully read before reaping, but it is still summarized into bounded events. **Do
not rely on runplane events for the improver.** If production runs are ever to feed
the improver, add an unbounded per-run trace sink beside the bounded event ring.

### 7.4 Retention policy (specify)

- **Never delete** `/opt/deepswe-smoke/jobs/**` or `/opt/evals/results/**`. Existing
  benchmark artifacts stay intact (Lane B constraint).
- The improver copies (does not move) the trace files it mines into
  `/opt/evals/improver/traces/{held_in,held_out}/<job>/<trial>/` so the held-out
  seal (§6.3) can be enforced by directory permissions without touching the
  canonical `jobs/` tree.
- A round's inputs (split files, configs, candidate branches, manifests, baseline
  cache) all live under `/opt/evals/improver/` and are themselves git-tracked for
  audit.

---

## 8. Weakness mining (P4.1b) — φ failure clustering

Turns per-run evidence into reusable failure patterns for the proposer
(Self-Harness Weakness Mining §3.2). The bundle **describes** failures; it must
**not prescribe** edits (that is the proposer's job).

### 8.1 The signature φ = (verifier cause, agent-behaviour causal status, mechanism)

Computed per failed trial (reward < 1) from guard records + raw traces:

| φ component | Source | Values (examples) |
|---|---|---|
| **verifier cause** | `verifier/reward.json` + `ctrf.json` + `test-stdout.txt` + `exception.txt` | `f2p-unmet` (target tests still fail), `p2p-regressed` (broke passing tests), `verifier-error`, `agent-timeout`, `no-patch`, `infra-exception` |
| **agent-behaviour causal status** | swarm `transcript.jsonl` (GAP-2) + `model.patch`; in production, guard records `seal-red`/`green`/`diff-review` (`controlplane/guard.go`) | `caused` (agent action produced the failure), `uncaused` (env/infra), `masked` (agent's own tests passed but oracle failed — TDD-Agent "matched failure"), `no-op` (agent never edited the relevant file) |
| **mechanism** | transcript + patch inspection | abstract, e.g. `wrong-file-localized`, `test-not-run-locally`, `premature-termination`, `budget-exhausted`, `tool-error-loop`, `spec-misread`, `sealed-own-incomplete-tests` |

### 8.2 Clustering procedure

```
for each failed trial in held-in:
    read reward.json, ctrf.json, test-stdout.txt, exception.txt   → verifier cause
    read transcript.jsonl (or guard records) + model.patch        → causal status, mechanism
    emit φ tuple + pointers (file:line into the trace) into clusters[φ]
write /opt/evals/improver/mining/<round>/clusters.json:
    [ {phi:{verifier_cause,causal_status,mechanism}, count, trials:[...],
       evidence_pointers:[{file, span}], no_edit_prescription:true} ]
```

The cluster file carries **pointers into raw traces** (Meta-Harness: pointers for
"where", raw traces for "why"), an occurrence count (so the proposer targets the
dominant mechanism, echoing TDD-Agent Fig 6's matched-failure dominance), and
deliberately **no suggested fix**.

`masked` clusters (agent tests pass, oracle fails) are the matched-failure tax and
should be surfaced as the primary metric per round (roadmap #7): report
`validation_minus_holdout_gap` alongside the cluster.

### 8.3 φ as a Code-Review emission schema (secondary use)

The same φ schema is a good structured output for the production Code Review pass to
emit per finding, so production failures and eval failures cluster in one vocabulary.
Not required for the loop; noted for alignment.

---

## 9. Change-manifest schema (auditable)

Every candidate carries a `manifest.json`; accepted ones are archived under
`/opt/evals/improver/accepted/`, rejected under `/rejected/`.

```jsonc
{
  "candidate_id": "cand-0007",
  "round": 3,
  "created_at": "2026-08-25T18:00:00Z",
  "proposer": { "agent": "anvil-wf-executor", "model": "gemini-3.7-flash", "session": "…" },
  "base": { "catalogVersion": "…", "harness_git_sha": "…", "engine_sha256": "…" },
  "surface": "engine.py",            // one of: engine.py | catalog.roles | catalog.modelTiers | catalog.authorityProfiles | agent.md
  "edit": {
    "git_branch": "cand/0007",
    "diff_digest": "sha256:…",
    "files": ["/opt/evals/swarm/engine.py"],
    "summary": "redirect agent to run target tests locally after 50 tool calls"
  },
  "targets_phi": { "verifier_cause": "f2p-unmet", "causal_status": "masked", "mechanism": "test-not-run-locally" },
  "predicted_fixed_trials": ["…"],
  "predicted_at_risk_trials": ["…"],   // AHE self-prediction — RECORDED, never trusted as the gate
  "portTo": "guard/guard.go",          // production file to mirror if accepted (GAP-1)
  "scores": {
    "baseline": { "held_in_reward": 0.13, "held_out_reward": 0.07 },
    "candidate": { "held_in_reward": 0.20, "held_out_reward": 0.07 },
    "delta": { "held_in": 0.07, "held_out": 0.00 },
    "n": { "held_in": 15, "held_out": 15, "attempts": 2 }
  },
  "decision": "accept",                 // accept | reject ; rule: Δin≥0 ∧ Δho≥0 ∧ max>0
  "decision_rule": "delta.held_in>=0 && delta.held_out>=0 && max(delta)>0"
}
```

The manifest deliberately records the proposer's own fix/regression prediction
(AHE) **and** the held-out measured delta (Self-Harness), so future analysis can
measure how blind the proposer's self-prediction was — the exact AHE §4.4.2 result,
now observable in our own runs.

---

## 10. End-to-end data flow (one round)

```
                 held-in traces (grep-able files, §7)          held-out tasks (SEALED, §6.3)
                        │                                              │
        ┌───────────────┴─────────────┐                              │
        ▼                             ▼                              │
  weakness mining (§8)         harness source                        │
  φ clusters.json          (engine.py, agent.md, catalog.json)       │
        │                             │                              │
        └───────────►  PROPOSER (§4)  ◄┘    (cannot read held-out) ◄──┘  seal
                    K candidate branches + manifests
                             │
                             ▼
              for each candidate:  apply + re-render (§5.1)
                             │
             ┌───────────────┴───────────────┐
             ▼                               ▼
     pier run held-in subset          pier run held-out subset
     jobs/cand-<id>-heldin/           jobs/cand-<id>-heldout/
             │                               │
             └───────────────┬───────────────┘
                             ▼
              GATE (§6):  Δin≥0 ∧ Δho≥0 ∧ max>0
                   ┌─────────┴─────────┐
                accept                reject
             git merge, bump        git branch -D,
             catalogVersion,        keep manifest
             new baseline           in /rejected
                             │
                             ▼
              accepted manifest → next round's evidence
```

---

## 11. Build order (when the user approves building)

1. **Close GAP-2** (transcript retention) — highest leverage; without it the
   proposer is starved of the "why". `engine.py` sink + `bridge.py` copy + one
   pier trial to confirm `agent/transcript.jsonl` appears.
2. **Split + baseline cache** — `split_pool.py`, freeze `held_{in,out}.txt`, run
   baseline on the N=15 subsets once, cache rewards.
3. **Config templater + `pier run` wrapper** — generate per-candidate held-in/out
   configs from the baseline template.
4. **Weakness miner** — φ clustering over held-in traces → `clusters.json`.
5. **Proposer harness** — launch a fleet coding agent with the §4.2 template and
   sealed held-out; collect K branches + manifests.
6. **Gate + accept/revert** — `gate.py` implements §6.1 exactly; wire git
   merge/branch-D and manifest archival.
7. **(Later, D-1 option b)** faithful production-harness eval so guard/hook
   proposals are measured directly.

---

## 12. Open decisions for the user

- **D-1 (§2 GAP-1):** near-term gate on `engine.py`+catalog surfaces with hand-port
  to Go guard (a), or invest in making pier drive the production Go harness (b)?
  Recommend (a) now, (b) as end-state.
- **D-2 (§5.3):** N per split. Recommend N=15 × 2 attempts (≈ the 10-sample run's
  cost × 6 ≈ **$85/round** at the observed $14.40/10-trial rate; a full 58×58×2
  round would be ≈ $1k). Confirm the cost ceiling per round.
- **D-3 (§3):** freeze `deepswe-split-v1` seed now? Once frozen it must never
  change or held-out leaks.
- **D-4 (§7.2):** approve closing GAP-2 (transcript retention) as the first build
  step — it modifies `engine.py`/`bridge.py` on 135, which is eval-side, not the
  swarm-coder repo.

---

## 13. Langfuse — human eval-trace explorer

The improvement loop above reads raw trace FILES; Langfuse is only the human
debugging explorer and is **not** on the loop's critical path.

### 13.1 Outcome: assessed, ready-to-run plan prepared, deployment held for a decision

**Capacity: adequate.** Proxmox host **Forge** (`10.0.20.10`, PVE 9.2.5, Ryzen
5900X, 24 vCPU / 62 GiB): live `free -g` shows **used 40, available 22 GiB** — the
~8-10 GiB Langfuse app tier fits. Disk is the pinch: `local-lvm` thin pool is
**96% full (32 GiB free)** — too tight to safely carve a new VM disk there; the
`local` dir store has **81 GiB free** and is the right target for a new guest disk.

**All stateful backends already exist and are live** (verified by the homelab
assessment): ClickHouse CT210 `10.0.20.210:8123`/`:9000` (holds the `langfuse` DB —
835 sessions, 3,819 trace roots, 171,196 observations, project `Agents` =
`a7b75c7f-18da-4553-9634-eda1c54330f4`); Postgres CT200 `:5432` (TLS); Redis CT220
`:6379`; RustFS/S3 CT240 `:9000` (bucket `langfuse`). The retained deploy manifest
is `/home/anvil/repos/homelab/compose/forge/langfuse.yml` (images pinned **4.1.0**).

**Why deployment was not executed in this pass (three real blockers):**

1. **No Docker host exists.** The old Langfuse ran on **VM110 `svc`, which was
   destroyed** after retirement (its VMID is now the `prod` LXC). Forge has no
   Docker daemon, and homelab policy forbids Docker-in-LXC. Deploying therefore
   requires **creating a new guest** (recommended VMID **115**, Debian + Docker,
   4 vCPU / 10 GiB, disk on `local`) — a production-mutating operation.
2. **The original secrets are only inside encrypted VM110 backups.** The compose
   requires `SALT`, `ENCRYPTION_KEY`, `NEXTAUTH_SECRET`, the S3/Redis/CH/PG
   credentials, and `LANGFUSE_INIT_*` from `/opt/forge/secrets/langfuse.env`, which
   lived on the destroyed VM. It is recoverable from
   `/mnt/pve/unas-backups/proxmox/vzdump-qemu-110-2026_08_04-02_11_43.vma.zst`, but
   extracting one file from a VMA image is itself a production operation.
   **`SALT`/`ENCRYPTION_KEY` must match the originals** to reuse the existing
   Postgres `langfuse` DB (they key its hashed API keys and encrypted columns); a
   fresh key against the old DB breaks auth.
3. **A faithful redeploy runs migrations against the production ClickHouse that
   holds 3,819 real traces.** Same-version (4.1.0) redeploy makes them no-ops, but
   any version drift risks the live trace data. This is exactly the "heavy,
   long-lived, data-touching" deploy the Lane B brief said to **stop and report**
   rather than do blindly, and the harness permission layer denied the setup steps
   (`pct exec`, backup inspection) — an independent signal to get an explicit
   go-ahead before mutating production.

**Ready-to-run plan (safe branch — faithful 4.1.0 rollback, zero schema risk):**

1. Create guest **CT/VM 115** on Forge, disk on `local` store, 4 vCPU / 10 GiB;
   install Docker CE + compose plugin. (Debian VM, not LXC, per policy.)
2. Recover secrets: extract `/opt/forge/secrets/langfuse.env` and
   `/opt/forge/certs/langfuse-postgresql-ca.crt` from the `vzdump-qemu-110`
   2026-08-04 backup; place at the same paths on the new host.
3. Fix the one dead reference: the retained compose's `langfuse-web` uses a
   vanished locally-built image `forge/langfuse@sha256:… (pull_policy: never)`.
   Repoint it to upstream **`docker.io/langfuse/langfuse:4.1.0`** (the worker
   already uses the public pinned image).
4. Open CT210 firewall for the new host: add
   `ip saddr 10.0.20.115 tcp dport 9000 accept` to
   `infra/phase12/clickhouse/clickhouse.nft` (native `9000` is currently pinned to
   `10.0.20.110` only; `8123` is already LAN-open). Confirm CT200/CT220/CT240 accept
   the new source IP.
5. `docker compose -f langfuse.yml up -d`; wait for `langfuse-web` health; it will
   listen on `10.0.20.115:3033` (adjust the published-IP bind in the compose from
   the old `10.0.20.110:3033`).
6. Verify: `curl -sI http://10.0.20.115:3033` → 200/302; log in with the recovered
   `LANGFUSE_INIT_USER_*`; confirm the `Agents` project shows the 3,819 migrated
   traces. Optionally add an ingress/Tailscale route.

**Fallback branch (if secrets are unrecoverable):** deploy 4.1.0 with *fresh*
`SALT`/`ENCRYPTION_KEY`/`NEXTAUTH_SECRET` against a **new** Postgres DB
(`langfuse2`), and set `LANGFUSE_INIT_PROJECT_ID=a7b75c7f-18da-4553-9634-eda1c54330f4`
so the fresh project matches the ClickHouse rows and the migrated traces render.
Reuse ClickHouse/Redis/RustFS read paths; do **not** point a fresh-keyed instance at
the old Postgres `langfuse` DB.

**Decision needed — D-5:** approve the safe-branch deployment (creates VM 115,
extracts secrets from the VM110 backup, opens one CT210 firewall rule, brings up
4.1.0 against the existing backends). This is the heavy long-lived container the
brief flagged; it is fully planned above and can be executed on a go-ahead.

### 13.2 Raw-trace retention status (deliverable #2)

Retention of the **existing** pier artifacts is confirmed and secure: they are plain
files under `/opt/deepswe-smoke/jobs/**` on CT135's own disk (5.9 MB for the 10-trial
baseline; 17 G free), untouched by `environment.delete` (which removes only the task
*container*). Nothing on 135 deletes them; the Lane B "do not delete" constraint is
respected — I made no changes to any job artifact. The one substantive retention
*build* — closing **GAP-2** (§7.2) so the swarm's multi-agent transcript is written
to `jobs/<job>/<trial>/agent/transcript.jsonl` — is specified but not implemented in
this pass: it modifies `engine.py`/`bridge.py` on the eval box and can only be
verified by a paid docker re-run, so it is left as the **first build step** (§11) for
explicit go-ahead (D-4), not landed half-wired.
