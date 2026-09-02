# 10. README diagrams are generated theme-aware SVG

## Status

Accepted

## Context

The README's two "How it works" visuals were Mermaid fences. GitHub renders Mermaid
only inside its own Markdown viewer, and it renders it its own way: the diagram is
invisible on npm, in a packaged plugin, in an editor preview, in a PDF, and in any
mirror of the repository, and its size, colours, and line breaks are outside our
control. Both diagrams had also drifted toward the smallest thing Mermaid lays out
well — four boxes — rather than the flow a newcomer actually needs, which is the
whole path from a goal to a merge.

Committing hand-drawn SVG would fix the rendering but not the drift: nothing would
tie the picture to the words, and no reviewer could diff a change to it.

## Decision

The README's architecture diagrams are generated. `docs/diagrams/src/<n>.json`
declares nodes, edges, and groups; `scripts/render-diagrams.py` — Python 3 standard
library only, no Graphviz, Mermaid CLI, or npm dependency — lays them out and writes
`docs/diagrams/<n>-light.svg` and `docs/diagrams/<n>-dark.svg`. The README embeds
both through a `<picture>` element whose dark `<source>` and light `<img>` let GitHub
pick by colour scheme, with `alt` text naming the relationship shown.

Rendering is deterministic: the same source produces the same bytes, with no
timestamps and one fixed float format. `scripts/render-diagrams.py --check` fails and
names any SVG that differs from a fresh render, and CI runs it as `Diagrams in sync`,
so a hand-edited SVG fails the build instead of silently diverging from its source.
Node kind is carried by shape and stroke as well as colour, and each diagram embeds
its own legend, `<title>`, and `<desc>`.

ADR 0004 still governs: each diagram keeps its adjacent "In words" paragraph, which
is the text equivalent for screen readers, raw-Markdown readers, and agents. Mermaid
remains the right choice elsewhere — `docs/gates.md`, planner folios, and review
reports are unaffected.

## Consequences

The README's visuals survive outside GitHub's Markdown viewer, follow the reader's
colour scheme, and change only through a reviewable source diff. A new diagram means
one JSON file and a render; a changed label means an edit and a render, and forgetting
the render is a red build rather than a stale picture.

The layout engine is ours to maintain: it is a layered top-to-bottom placer with
orthogonal edges and estimated text metrics, so a very long label or an unusually wide
layer fails the render with a message rather than laying out badly, and shapes must be
kept simple enough for it. Diagrams that are genuinely not top-to-bottom flows do not
belong in it, and the checked-in SVGs add reviewable bytes to the repository.
