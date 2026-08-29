# 4. Visuals require text equivalents

## Status
Accepted

## Context
Planner folios, code-review reports, and repository READMEs serve both people and
automation. Visuals can make architecture, workflow, and review topology easier to scan,
but they become decorative noise when they do not answer a reader question. They also
lose meaning in raw Markdown, print, screen readers, failed Mermaid rendering, and agent
contexts when the same information exists only as pixels or diagram syntax.

The planner, code-review, and docs skills need one durable communication rule without
forcing every output into the same kind of diagram.

## Decision
Every user-facing visual produced by a shared skill must communicate a named relationship
and have a nearby concise text equivalent derived from the same authoritative data when
the output is generated. Labels must be meaningful without relying on colour alone.

Choose the smallest format that fits the information: Mermaid for relationships and
flows, semantic HTML/CSS for report summaries, durable text diagrams when Mermaid adds
complexity, and tables for comparisons. A visual is not required when prose or a small
table is clearer.

Specific skill contracts refine the rule:

- Planner folios compare the current and proposed state and explain the delta in text.
- Code-review reports visualize the path from review lenses to verified findings and
  affected files, with the same outcome summarized in text.
- READMEs explain what the repository does, why it exists, and the shortest viable
  quickstart before presenting a meaningful architecture or workflow visual.

## Consequences
Reports and READMEs remain useful without JavaScript, successful Mermaid rendering,
colour, or visual browsing. Generated visuals and summaries should share validated source
data so they cannot drift independently. Authors must spend a small amount of extra effort
choosing a suitable representation and maintaining its text equivalent; decorative
diagrams are explicitly out of scope.
