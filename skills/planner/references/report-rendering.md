# Planner report rendering contract

This reference is for maintainers of `render_plan.py` and its templates. Operators keep using the renderer commands in `SKILL.md`.

Use [`templates/plan.html.tmpl`](../templates/plan.html.tmpl) through the renderer. Keep the fixed folio section order — 01 Overview, 02 Architecture, 03 Task Breakdown, 04 Execution Waves, 05 Risks, 06 Milestone & Execution — and all CSS and Mermaid code inline. The HTML must remain useful without JavaScript: every Mermaid diagram starts as a Claude-Artifact-compatible `<pre class="mermaid">` source block and includes a source-details fallback that becomes visible if rendering fails.

Section 02 renders the strict `currentArchitecture` and `targetArchitecture` pair side by side as **Current** and **Proposed**, followed by responsive stacking on narrow screens. It also renders the escaped `changeSummary`, so the visual remains understandable to people while the sidecar remains precise enough for machine consumers.

Styling comes from two files. [`templates/report.css`](../templates/report.css) is the shared Foundry Zero report design system — colour tokens, severity ramp, chrome, print rules — and is **byte-identical** to `skills/code-review/templates/report.css` and `skills/research/templates/report.css`; change all three together or none. [`templates/plan.css`](../templates/plan.css) holds planner-only components (approval gate, wave lanes, risk matrix). The report is theme-aware, responsive, and prints: disclosure rows open for print and the chrome is suppressed.

The folio never renders acceptance tests; they belong to the GitHub issue body. Section 00 states the approval gate, and it always reads "Proposed — awaiting explicit human approval" because the folio is the artifact a human reads *before* approving.
