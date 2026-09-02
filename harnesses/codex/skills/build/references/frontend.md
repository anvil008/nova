<!-- Read by the builder agent when a task touches UI; not a standalone skill. -->

# Frontend (basics done right)

Build UI that is correct, accessible, and responsive — not elaborate. Match the project's existing stack and conventions first; only reach for a framework or design system the repo already uses.

## Do
- **Semantic HTML** — real elements (`button`, `label`, `nav`, `main`, headings in order). Structure before styling.
- **Accessible by default** — every control labelled; visible focus states; sufficient colour contrast; keyboard-operable; images have `alt`; forms report errors in text.
- **Responsive, mobile-first** — fluid layout (flex/grid, `%`/`rem`/`clamp`), `max-width:100%` media, no fixed pixel widths that overflow; test narrow → wide.
- **Clean CSS** — a small spacing/type scale, system font stack unless the repo sets one, CSS variables for colour so themes are trivial. Prefer the repo's tokens.
- **Progressive** — the page works before JS; JS enhances, never gatekeeps core content.
- **Performance basics** — no giant blocking assets; lazy-load below the fold; size media to avoid layout shift.

## Don't
- No heavy UI framework or design-system dependency the project doesn't already use.
- No inline-style sprawl, no `!important` piles, no `div` where a real element exists.
- No inaccessible custom widget when a native element does the job.
- Don't over-art-direct — this is the *basic, solid* skill, not a brand system.

## Verify
Runtime proof happens in the builder's *Prove it runs, not just passes* step, not here and not twice: that step serves the UI, drives it in a real browser at ~390px and ~1280px, tabs through every control, and fails on any console error. Build so that step can pass, and hand back through the builder's normal TDD gate.
