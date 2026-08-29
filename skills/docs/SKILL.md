---
name: docs
description: Run a documentation-standardization and review pass — enforce the doc standard, update stale docs, record ADRs, and check instruction-file bloat. Use standalone, or as the final step of build/deploy.
---

# Docs

Bring a repository's documentation up to standard and keep it there. The primary agent owns the result; the `docs` agent does the writing.

## README contract

Write for a newcomer first. Lead with what the repository does and why it exists, then give the shortest viable quickstart. Include one compact visual of the primary architecture or workflow when relationships matter; prefer GitHub-rendered Mermaid, or use a durable text diagram when Mermaid adds complexity. Pair every visual with meaningful labels and a nearby textual explanation that conveys the same flow to screen readers, raw-Markdown readers, and agents. Use concise, plain-language prose, remove repetition, and choose a small table instead of a decorative diagram when comparison is clearer than flow.

See [examples/visual-readme.md](examples/visual-readme.md) for the reference shape.

## Pass

1. Inventory docs and the change set. Dispatch the `docs` agent.
2. Run the mechanical gate `skills/docs/scripts/docs_check.py <repo-root>` — it flags oversized `CLAUDE.md` / `AGENTS.md` and malformed or duplicate ADRs (exit non-zero on any violation).
3. Standardize and **update in place** (update-don't-duplicate); apply the README contract and relocate role-specific material out of global instruction files into the right agent/skill.
4. Record ADRs at the **repository root** (`docs/adr/NNNN-title.md`, never nested under a subfolder) for decisions future agents must follow; add a changelog/handover entry.
5. Re-run `docs_check` until clean; return the summary + diff.

Fan-out is rare (docs are usually one coherent surface); split only across genuinely independent doc areas.

## Offline demonstration

```bash
python3 -B skills/docs/scripts/docs_check.py skills/docs/examples/sample-repo
```
