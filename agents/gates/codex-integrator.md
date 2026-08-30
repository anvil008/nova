## Gates on Codex

The swarm-coder plugin wires no `PreToolUse` / `PostToolUse` / `Stop` hooks for Codex, so nothing runs `build-guard` for you. Call `build-guard codex` yourself before each mutating command — the merges you run are exactly the operations it exists to check.
