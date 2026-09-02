# Research report rendering contract

This reference is for maintainers of `render_research.py` and its templates. Operators keep using the renderer command in `SKILL.md`.

[`templates/report.css`](../templates/report.css) is the shared Foundry Zero report design system and must stay **byte-identical** to the planner and code-review copies; change all three together or none. [`templates/research.css`](../templates/research.css) holds the research-only rules. Keep the output self-contained, theme-aware, responsive, useful without JavaScript or network access, and legible in print.
