## Gates on Codex

The swarm-coder plugin wires no `PreToolUse` / `PostToolUse` / `Stop` hooks for Codex (the guard has a Codex dialect, but nothing invokes `tdd-guard hook` here), so nothing runs `build-guard` or `tdd-guard` for you. Every gate is an explicit call you make: `build-guard codex` before mutating commands, `tdd-guard seal` after RED, `tdd-guard verify` after GREEN (and again after each review-fix pass), `tdd-guard diff-review record` before the PR. Run `tdd-guard status` before handing off; a hand-off whose status shows no GREEN evidence postdating the seal is incomplete.
