# Optional helper agents

Skills remain the main workflow entrypoints. These helpers are reusable native configurations for bounded work inside those workflows. None is required for a direct, single-conversation task. The former research role is replaced by scout; no scout/research skill is added.

| Helper | Assignment | Return |
| --- | --- | --- |
| scout | Inspect one code or documentation question, read-only | Answer, relevant files/symbols, evidence, constraints, coverage, uncertainty |
| implementer | Implement one owned task and run its verification | Scoped changes, workspace/source state, criteria covered, checks and gaps |
| reviewer | Independently inspect a candidate without repairing it | Qualified verdict, evidence-backed findings, coverage and follow-up |

Native source files are `codex/NAME.toml`, `claude/NAME.md`, and `agy/NAME/agent.md`. Personal destinations are respectively `~/.codex/agents/NAME.toml`, `~/.claude/agents/NAME.md`, and `~/.gemini/config/agents/NAME/agent.md`. Claude and Agy definitions ship in native plugin agents/. Codex definitions ship as explicit setup resources; see ../docs/install.md. Reviewer settings inherit. Scout and implementer use the model selections below; no permission bypass is prescribed.

Expertise and assignment boundaries are embedded in each definition. The main conversation passes only relevant extra skill guidance, source context, and task constraints. Helpers do not need a separate agent-private skill catalog. Keep native bodies equivalent when updating their wrappers. Their descriptions occupy discovery context; full prompts load when invoked according to host behavior.

Scouts and reviewers omit native file-edit tools where configured. Shell access means their read-only contract is also an instruction boundary, not an enforced filesystem sandbox. Codex inherits the caller's tool/session configuration. Implementers may use available task tools, but must not delegate; Claude explicitly denies Agent and Agy omits invoke_subagent. No helper publishes, merges, deploys, or authors the overall report.

For parallel build, the main conversation establishes ownership and dependencies, assigns implementers, handles useful independent work, and combines their verified changes. It asks a reviewer to inspect the actual candidate when independent review is required or useful. Individual success does not prove integration. A scout is useful when a bounded lookup avoids repetitive exploration, but context isolation alone does not establish total token savings.

Validation covers native parsing, equivalent role bodies, and Agy package shape. See ../docs/reports/build01-20260907-native-plugin-migration.md for current native trial evidence. Model behavior and usage costs require separate trials. No new helper was launched merely to create these files.

## Model selection

| Helper | Agy | Claude Code | Codex |
| --- | --- | --- | --- |
| scout | gemini-3.8-flash-low | haiku; effort not overridden | gpt-5.6-luna; effort not overridden |
| implementer | gemini-3.8-flash-high | claude-opus-5; medium effort | gpt-5.6-terra; high effort |
| reviewer | inherit | inherit | inherit |

Agy uses the exact model IDs exposed by the installed `agy models` catalog, which encode effort. High was selected for its implementer because the requested Gemini model had no specified effort. Claude Haiku uses the requested family alias; Opus 5 uses its explicit model ID. Omitted effort settings follow native inheritance/default behavior. Do not silently substitute unavailable models; report the runtime configuration gap. Native parsing validates configuration shape, not model execution or account availability.
