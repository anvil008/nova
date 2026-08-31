# 12. Builders verify the change runs before any review pass

## Status

Accepted

## Context

The builder's definition of done was GREEN plus a recorded diff review. Both are statements about
the tests and the diff: `tdd-guard verify` proves the sealed suite passes on a tree that postdates
the seal, and `tdd-guard diff-review record` binds findings to that diff. Neither observes the
change working. A UI that renders a blank page, a service that fails to boot, or a CLI that throws
on its own `--help` can all satisfy the whole state machine, and the two review passes that follow
then judge a change nobody has run. The `code-reviewer` already receives `devServer` and drives a
browser for its `frontend` lens, so the harness could observe runtime behaviour — but only after
the builder had declared itself finished, and only as a review finding rather than a build failure.

## Decision

Runtime verification is a step in the builder's procedure, between GREEN and the review passes. The
builder identifies the runnable surface the issue changed and exercises it: a real browser for UI
(driven with the `mcp__playwright__browser_*` tools on Claude, headless Chromium from the shell
elsewhere), `curl` against a started service for an HTTP API, the real command on realistic input
for a CLI. Any console error fails the step, everything started is torn down, and a change with no
runnable surface states that explicitly rather than inventing a ceremony.

The dispatch brief may carry a `runtime` hint (`{launch, url, healthPath}`); absent, the builder
discovers the run command from the repository, and a production URL is never a valid target. The
handoff record carries the proof in `evidence.runtime`, and a record whose diff touches a runnable
surface while claiming `surface: "none"` is malformed, exactly as a command without a `commandId`
is. The Claude builder is granted the same nine Playwright browser tools the `code-reviewer` has;
other harnesses use the Bash fallback.

## Consequences

A change that passes its tests but does not run is blocked at the builder rather than surfacing as
a review finding or, worse, as a merged regression. Orchestrators gain one more piece of mechanical
evidence to accept a wave on, and `skills/build` collects it alongside the command-linked test
evidence.

This gate is contract-level: the Stop hook still gates only on `tdd-guard` state, so the guard
cannot enforce runtime evidence and its absence is caught by reading the handoff record. Builders
pay the cost of standing a surface up and tearing it down on every issue that has one, and
`skills/builder-frontend` no longer describes a verification pass of its own — it points at this
step so the check happens once, in one place.
