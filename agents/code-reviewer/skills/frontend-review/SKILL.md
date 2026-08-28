---
name: code-reviewer-frontend-review
description: Read-only UI/UX review of a built or running frontend — responsiveness, accessibility, design-system conformance, and visual QA. Produces evidence-backed findings; never changes code. Owned by the code-reviewer.
---

# Frontend review (read-only)

Review a frontend the way a design- and accessibility-minded engineer would — and only review. Never modify code, styles, components, tokens, tests, or config.

## Lenses
- **Responsive** — layout holds across viewports (≈360 · 768 · 1280) and orientations; no overflow, clipping, or broken reflow; touch targets adequate.
- **Accessibility** — semantic structure, labelled controls, visible focus, full keyboard path, colour contrast (WCAG AA), `alt` text, text error messaging, heading order.
- **Design-system conformance** — uses the project's tokens / components / spacing / type rather than one-off values; flag generic or off-scale styling.
- **Visual QA** — alignment, spacing rhythm, state coverage (hover / focus / disabled / empty / error / loading), dark & light if themed.

## Method
1. Inspect the changed components and styles statically first.
2. If a dev server is available, capture runtime evidence across the viewports above (screenshots / DOM checks) — ask before starting any server; never touch production.
3. Report findings, each with: the surface, the issue, the evidence, and a severity. No fixes; no task-board writes.

## Boundaries
UI only — no backend/API review, no repo-wide architecture, no security audit, no e2e test authoring, and no code changes. Return findings and control to the caller.
