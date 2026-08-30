# Code-review report rendering contract

This reference is for maintainers of `render_review.py` and its templates. Operators keep using the renderer command in `SKILL.md`.

Sections are fixed: 01 Summary, 02 Findings, 03 Touched Files, 04 Refuted Candidates, 05 Method. Findings filter by severity and by lens, and each expands to its failure scenario, the refutation attempt, and the evidence. All CSS and JavaScript are inline; there are no external resource loads.

Every report includes two non-interactive visuals derived solely from the validated review JSON and render context: a review topology showing lens fan-out through verification to verdict, and a verified-impact map grouped by file and severity. Both remain present for zero-finding reviews, include equivalent text for assistive technology, work without JavaScript or network access, and remain legible in print. They summarize the report; they never replace the detailed findings, refutations, filters, or reconciliation data.

Styling comes from two files. [`templates/report.css`](../templates/report.css) is the shared Foundry Zero report design system and is **byte-identical** to `skills/planner/templates/report.css` and `skills/research/templates/report.css`; change all three together or none. [`templates/review.css`](../templates/review.css) holds review-only components. The report is theme-aware, responsive, and prints: filters are suppressed, hidden rows are restored, and disclosure rows open.
