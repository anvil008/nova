# 1. Agent-owned skills

## Status
Accepted

## Context
The agents are single-purpose leaves (research, builder, code-reviewer, docs) that the orchestration skills drive. We want each agent to carry its own domain skills — e.g. `jj` for the builder — without every agent sharing the same set. Harnesses discover skills globally (`~/.claude/skills`, `~/.codex/skills`, `~/.agents/skills`); there is no frontmatter flag that hard-scopes a skill to one agent.

## Decision
An agent owns a skill by (1) carrying the `Skill` invocation tool, and (2) declaring the skill in a `## Skills` section of its `AGENT.md`, with a boundary forbidding use of the orchestration skills. A skill is either reused from the global install (e.g. `jj`) or vendored under `agents/<agent>/skills/<skill>/SKILL.md` and installed as `<agent>-<skill>`. Only agents that need skills get the `Skill` tool; leaves that do not (research, code-reviewer) stay skill-free.

## Consequences
Scoping is by convention plus instruction, not a hard boundary — an agent with `Skill` can technically see any installed skill, so the `AGENT.md` boundary is what keeps it in its lane. The builder is the first adopter: it owns `jj`. Adding a builder skill later means vendoring it under the builder's skills folder and listing it in the builder `AGENT.md`.
