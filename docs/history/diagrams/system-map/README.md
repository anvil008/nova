# Workcell system explorer

A dependency-free local HTML explorer of the implemented Workcell workflows, architecture, agents, and evidence gates. The registry contains 12 public skills, 10 agent roles, and three harnesses.

[Decision tree](http://127.0.0.1:8787/#tree) is the home page. Plan, review, debug, profile, and refactor appear as peer workflows with their own completed outcomes. Supported, scoped, and authorized changes can continue through shared build. There is no workflow-imposed minimum, maximum, or default team size; the orchestrator chooses useful assignments within runtime capacity and explicit user limits.

The controls show:

- One plan or multiple plan ideas. This is an output choice, separate from team size. Planners own their research and final plan authorship; the orchestrator compares and reviews.
- The build team or a close-up of one task. This changes diagram detail, not agent allocation.
- Feature, bug fix, refactor, and optimization verification paths.
- The individual registered paths for each execution workflow, with expandable stage diagrams.

The standalone `/research` skill has been removed. Native research and exploration can answer an independent question without initiating planning or offering another workflow. `/plan` retains the researcher role, evidence contract, deterministic merger, and optional report renderer under `skills/plan/research`. A planner uses supported native nesting or asks the orchestrator to proxy dispatch while retaining ownership of questions and synthesis.

Markdown is the default report output; HTML is an explicitly requested companion. Plan, review, profile, and refactor assessment finish with their own artifacts and offer build only for actionable work when implementation was not already requested and the user did not limit the request to a report. Shared build preserves those decisions and evidence. Documentation can run independently or join build before final verification. Debug returns a diagnosis report or documented inability to reproduce. Investigation-only requests finish there; a supported cause and repair authorization are both required to enter build. A debug-and-fix request already authorizes that transition. Refactor proposals establish the behavior and tests to preserve; authorized implementation seals a passing baseline before any builder starts. Structural simplification does not imply a measured performance gain.

[Execution flow](http://127.0.0.1:8787/#flow/build) shows the current workflow diagrams. [Decision tree](http://127.0.0.1:8787/#tree) presents the top-down choice of outcomes. Setup, deployment, wiki, and auxiliary skills remain accessible. Agent details, architecture, and mechanical gates use the same current repository snapshot.

Serve from the repository root:

```sh
python3 -m http.server 8787 --bind 127.0.0.1 --directory docs/diagrams/system-map
```

Open [the local explorer](http://127.0.0.1:8787/). There are no external assets or package dependencies. Source links use `source.html` and a local snapshot. The repository link identifies the baseline commit; working-tree source records describe the implementation. Installed plugins still require their normal rebuild and refresh.

`execution-diagrams.js` renders execution diagrams and the decision tree, with styles in `execution-diagrams.css`. `app.js` owns routing, inspector details, and the catalog stage renderer. `workflows.js` matches the public skill registry; `workflow-design.js` supplies its display grouping and legacy diagram aliases. Both catalogs remain JSON object literals for deterministic validation.

Refresh the source snapshot and check syntax:

```sh
python3 docs/diagrams/system-map/snapshot_sources.py
python3 docs/diagrams/system-map/snapshot_sources.py --check
node --check docs/diagrams/system-map/workflows.js
node --check docs/diagrams/system-map/workflow-design.js
node --check docs/diagrams/system-map/execution-diagrams.js
node --check docs/diagrams/system-map/app.js
```

The snapshot helper checks registry coverage, roles, paths, aliases, and local source freshness. It does not prove a live agent run or the installation state of the user's harness. Native-capability links describe the named products; Workcell does not assume identical Deep Research modes across harnesses.

Direct links:

- `#tree`: the current workflow decision tree.
- `#flow/debug/diagnose`: investigation ending with a diagnosis report.
- `#flow/debug/bounded`: diagnosis and an authorized repair.
- `#flow/refactor/assess`: standalone refactor assessment and proposal.
- `#flow/refactor/bounded`: selected simplification through baseline-protected build.
- `#flow/build/refactor`: shared build with refactor verification selected.
- `#flow/<workflow>/<path>`: current execution path, including `/profile`; `/perf` remains a legacy diagram alias.
- `#flow/build/detail` or `#flow/build/team`: diagram detail; earlier `bounded` and `coordinated` paths remain compatible.
- `#agents/<role>`: current repository role details.

The design-comparison page has been removed. Old comparison links redirect to the current workflow or decision tree. `#flow/research` explains the retired command and retained capability.

The diagrams are code-native and do not depend on temporary screenshot files. Scenario toggles are local UI state: no agents, plans, issues, pull requests, or deployments are created by this explorer.
