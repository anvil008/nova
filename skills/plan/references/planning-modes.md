# Planning choice, research, and resume

The orchestrator owns the user's goal and decisions, chooses the team, and evaluates the result. Planner agents investigate and author plans. An accepted-plan resume reuses the existing artifacts and needs no new planning round.

## One plan or multiple plan ideas

Ask this choice once per new plan unless the user's request or an applicable saved decision supplies it. While an answer is pending, ground the request without launching speculative alternative plans. A request for one plan, a concise brief, or a specified set of alternatives already supplies the choice. Do not replace this question with a research opt-in or a team-size question.

**One plan** means one coherent proposed approach. The orchestrator can assign supporting planners and researchers where useful; it designates the planner responsible for the final artifact. It does not author the plan itself.

**Multiple plan ideas** means meaningful alternative approaches to the same goal. The orchestrator frames distinct directions, constraints, and comparison criteria, then assigns planner work accordingly. No fixed number of plans or agents is required. Planners return proposals with evidence and tradeoffs; the orchestrator compares them and may select or combine compatible ideas. Product, compatibility, or scope decisions that depend on the user's preference go to the user. A designated planner expands the chosen direction into the executable plan and records why other approaches were rejected.

The orchestrator chooses and can resize planner and researcher teams according to the work. There is no workflow minimum, maximum, default team size, or prescribed retry count. Respect actual runtime capacity and explicit user limits. Queue useful independent assignments when capacity is occupied. Stop or revise an ineffective investigation based on evidence, unresolved access, or a user constraint; do not repeat unchanged attempts indefinitely or invent a numerical budget.

## Output format and saved state

Produce Markdown by default. Do not ask a format question. An explicit visual/HTML request produces Markdown **and** an HTML companion. An explicit Markdown-only request produces no HTML. Carry the format through nested workflows and resume.

Substantial plans render both requested formats from one strict sidecar. A concise task brief can be Markdown without a synthetic milestone or issues. Add HTML for an explicitly requested visual brief without inventing a larger project. Alternative proposals can remain concise; do not force every idea through a full issue sidecar before choosing an approach.

Save `planning-choice.json` beside the run artifacts, outside tested source, with:

- Goal, scope, pinned source revision, `choice` (`single` or `multiple`), and the user's request or response supplying that choice.
- `format` (`md` by default or `html` when explicitly requested), plus whether build was already requested and the instruction authorizing that transition.
- Planner IDs, assigned directions, output paths, completion state, and the planner responsible for the final artifact.
- Research questions, dispatch owner, researcher IDs, evidence paths, completion state, and any limits the user actually specified.
- Review outcomes, accepted decisions, remaining questions, and selected or combined alternatives.

Keep this state outside the strict sidecar; reference evidence and rationale in its `summary`. Preserve plan IDs and issue keys on revision. Existing research packets and older choice records remain evidence, but a saved research mode is not a single-versus-multiple output choice. Resolve only the missing choice and retain completed work. If the source changes, identify which findings or plan assumptions need revalidation rather than silently calling stale evidence current.

## Planner-owned research

Research is an internal capability of planning, not a standalone workflow dependency. The planner identifies independent questions, writes focused briefs, receives findings, directs useful follow-ups, and decides how evidence changes the plan. It may reuse relevant native research or previously supplied reports after checking their source and applicability. Researchers investigate evidence; they do not produce competing implementation plans.

Use the active harness's native agent tool and configured role/model settings. If nested research delegation is supported, the planner manages its researcher agents directly. If it is unavailable, the planner returns research assignments to the orchestrator; the orchestrator dispatches them and routes findings back to that planner. Preserve planner ownership and agent IDs in either case. Do not pretend a tool exists or create untracked background processes to bypass a runtime restriction.

The orchestrator selects team size; planners propose the research work and manage assignments within that allocation. Give each researcher a focused question, shared goal and constraints, pinned source, relevant source pointers, and the [evidence envelope](research.md). Share existing evidence that is relevant; keep unrelated transcripts out of the brief. The planner can seek independent corroboration when that is the purpose of an assignment. Researchers remain read-only and return findings to their caller rather than dispatching more roles.

Record the research questions in the merger's areas manifest (`areas`, each with `area`, `scope`, and `sources`). Each report has a unique area ID; related investigations can share a `topic` without overwriting each other. Save the `evidence` field from each researcher handoff as its envelope. The merger accepts those envelopes, not the surrounding handoff record.

Merge evidence with `skills/plan/research/scripts/merge_research.py`, verify critical findings against source, and preserve conflicts and missing coverage. The planner owns synthesis and plan authorship. The orchestrator receives the plan and packet references so it can evaluate claims without ingesting every transcript.

On resume, read saved artifacts and inspect or wait for existing agents before considering new dispatches. Failed or missing research remains a visible gap. Reassign when useful and within actual capacity and any user limits, finish with an explicit limitation where the plan remains defensible, or return an unresolved dependency. Do not claim that an investigation completed merely because a report exists.

## Review and build handoff

The orchestrator checks the original requirements, evidence, compatibility, feasibility, dependencies, and testability. Return **accept**, **revise** with actionable findings, or **needs-decision** for the human. Revisions use the existing planner and artifacts when possible. If further attempts are no longer producing useful evidence, surface the unresolved issue instead of silently approving it.

Acceptance means the plan is ready; it does not mean implementation has been verified. Present the reviewed Markdown and any explicitly requested HTML before asking a standalone `/plan` user whether to proceed to `/build`. Continue directly when an applicable request already authorized planning and implementation. Carry source revision, plan identity, decisions, evidence, and execution authorization into build. GitHub mutations and deployment still require authorization for those actions.
