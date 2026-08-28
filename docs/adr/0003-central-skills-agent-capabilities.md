# 3. Central skills with agent-specific capabilities

## Status
Accepted

## Context
ADR-0001 associated skills with individual agent directories and assumed that research
and code-reviewer would remain skill-free. The centralized layout in ADR-0002 became the
single source for all harnesses, while agent definitions evolved: builders invoke `jj`
and `builder-frontend`, and code-reviewers invoke the frontend review method for that lens.
Research is itself dispatched through the `research` orchestration skill and may use
task-relevant installed skills without owning private copies.

## Decision
Skills are authored once under `skills/<name>/` and projected into every installed
harness by symlink. Agents carry skills through their harness-visible capability and
instructions: an agent definition names only the skills appropriate to its role and
states the boundary against orchestration it must not start. Agent ownership is therefore
an instruction-level capability over the central catalog, not a vendored
`agents/<agent>/skills/` tree.

Research and code-reviewer are not defined as skill-free. Research can use relevant
read-only skills while investigating its assigned area. Code-reviewer uses
`code-reviewer-frontend-review` for the frontend lens. Builder uses `jj` and
`builder-frontend`. These capabilities remain role-scoped even though all installed
skills are discoverable from the central harness directory.

## Consequences
There is one testable source for every skill and no per-agent skill copy to drift. The
installer can discover new skill directories without a hard-coded manifest. Role
isolation remains conventional rather than a filesystem security boundary, so agent
instructions and tool permissions must continue to prohibit inappropriate orchestration
or writes.
