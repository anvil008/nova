---
name: si-global
description: Cross-project pattern synthesis and core skill evolution: aggregate patterns across registered repositories, cluster recurring systemic issues, and propose evaluated improvements to shared Nova skills.
---

Read [shared development instructions](../../instructions/development.md) when applying this skill; reuse them if already loaded in this conversation.


# Self-improvement (global)

Use bundled `scripts/si_global.py` via an absolute path resolved from this skill. It aggregates self-improvement data across local repositories registered in `~/.nova/known_projects.json` (or `NOVA_PROJECTS_REGISTRY`) and coordinates core skill evolution.

## Workflow

1. **Inspect registered projects**: Run `python3 <skill-dir>/scripts/si_global.py projects` to view all known local repositories and their store health.
2. **Scan cross-project patterns**: Run `python3 <skill-dir>/scripts/si_global.py scan` to aggregate pattern pages across all registered stores.
3. **Cluster systemic recurring issues**: Run `python3 <skill-dir>/scripts/si_global.py cluster --min-projects 2` to identify failure modes, flaky dependencies, or workflows that recur across 2 or more distinct projects.
4. **Formulate shared skill proposals**: Run `python3 <skill-dir>/scripts/si_global.py propose --min-projects 2` to generate candidate patches for Nova's shared skills (`skills/*`).
5. **Gate with evaluation suites**: Before adopting or publishing any proposed global skill change, verify that benchmark evaluation suites pass:
   ```bash
   python3 evals/run_evals.py
   ```
   No global skill modification may be applied without passing evaluation gates.
