# Design heuristics

The shared vocabulary and judgment rules for module-design work: the `code-refactor` survey, the planner's architecture delta, and the reviewer's style criteria all use this file so their findings mean the same thing. Adapted from John Ousterhout (_A Philosophy of Software Design_, "design it twice") and Michael Feathers (seams), by way of [mattpocock/skills](https://github.com/mattpocock/skills); depth here is leverage, not Ousterhout's line-count ratio, because a ratio rewards padding the implementation.

## Vocabulary

Use these terms exactly; do not substitute "component", "service", or "unit" for module, "API" or "signature" for interface, or "boundary" for seam. Consistent language is what lets findings from different agents merge.

- **Module** — any unit with an inside and an outside: a function, class, file, or package.
- **Interface** — everything a caller must know to use the module: names, parameters, types, ordering constraints, error behaviour. Not a language keyword.
- **Implementation** — everything behind the interface that a caller need not know.
- **Depth** — leverage: how much behaviour sits behind how little interface. A module is **deep** when a small interface hides a lot; **shallow** when the interface is nearly as complex as what it hides.
- **Seam** — a place where behaviour can be swapped without editing callers.
- **Adapter** — one concrete implementation plugged into a seam.
- **Locality** — how much a reader can understand without leaving the module.

## Judging a module

- **Depth is a property of the interface, not the implementation.** To deepen: can the methods be fewer? the parameters simpler? more complexity hidden inside?
- **The deletion test.** Imagine deleting the module. If the complexity vanishes, it was a pass-through. If it reappears smeared across N callers, the module was earning its keep.
- **The interface is the test surface.** Tests belong at the module's interface and should survive internal refactors; a test that must change when the implementation changes is testing past the interface.
- **One adapter is a hypothetical seam; two adapters are a real one.** Do not build a seam for a second implementation that does not exist.

## What a dependency implies

What a module talks to decides whether a seam is warranted:

1. **In-process** (pure computation) — no seam, no adapter; test directly.
2. **Locally substitutable** (a test stand-in exists, e.g. an in-memory database) — the seam stays internal; test against the stand-in.
3. **Remote but owned** (your own service over the network) — a real seam: one adapter for production, one in-memory for tests.
4. **Truly external** (a third party) — an injected seam with a mock adapter; never test against the real thing.

## Designing for testability

1. **Accept dependencies, don't create them.** A module that constructs its own collaborators cannot be tested without them.
2. **Return results, don't mutate.** A value returned is asserted in one line; a side effect needs a probe.
3. **Keep the surface small.** Fewer methods and parameters mean fewer tests and simpler setups.

## Grading a candidate

A survey or review candidate carries one strength label: **strong** (friction is demonstrated at `file:line` and the deletion test bites), **worth-exploring** (real signal, unproven payoff), or **speculative** (a hunch; say so). A candidate that contradicts an ADR is surfaced only when the friction justifies reopening that ADR — name the ADR and the reason, or drop the candidate; do not relitigate settled decisions by default.
