## Gates on Codex

The swarm-coder plugin wires no `PreToolUse` / `PostToolUse` / `Stop` hooks for Codex (the guard has a Codex dialect, but nothing invokes `tdd-guard hook` here), so nothing runs `build-guard` or `tdd-guard` for you. Every gate is an explicit call you make: `build-guard codex` before each mutating command, `tdd-guard seal` once RED is real and honest, and `tdd-guard handoff --to builder` when you finish. Run `tdd-guard status` before handing off; a hand-off whose status shows no seal is incomplete.
