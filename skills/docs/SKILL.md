---
name: docs
description: Run a documentation-standardization and review pass — enforce the doc standard, update stale docs, record ADRs, and check instruction-file bloat. Use standalone, or as the final step of build/deploy.
---

# Docs

Bring a repository's documentation up to standard and keep it there. The primary agent owns the result; the `docs` agent does the writing.

## Pass

1. Inventory docs and the change set. Dispatch the `docs` agent.
2. Run the mechanical gate `skills/docs/scripts/docs_check.py <repo-root>` — it flags oversized `CLAUDE.md` / `AGENTS.md` and malformed or duplicate ADRs (exit non-zero on any violation).
3. Standardize and **update in place** (update-don't-duplicate); relocate role-specific material out of global instruction files into the right agent/skill.
4. Record ADRs at the **repository root** (`docs/adr/NNNN-title.md`, never nested under a subfolder) for decisions future agents must follow; add a changelog/handover entry.
5. Re-run `docs_check` until clean; return the summary + diff.

Fan-out is rare (docs are usually one coherent surface); split only across genuinely independent doc areas.

## Offline demonstration

```bash
python3 -B skills/docs/scripts/docs_check.py skills/docs/examples/sample-repo
```
