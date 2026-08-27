# Swarm Coder

A small, native multi-agent coding system for **Claude Code, Codex, and Antigravity**.

Four single-purpose agents — **research · builder · code-reviewer · docs** — driven by
orchestration skills (**planner · research · build · code-review**), plus lifecycle
skills (**docs · deploy**) and a **use-other-harness** escape hatch. Two mechanical
gates keep it honest: **tdd-guard** (test-first for code) and **docs-check** (doc
hygiene). GitHub issues under a milestone are the durable, resumable task board.

- **Design, agents, and skills:** [`harness-agents/v3/`](harness-agents/v3/README.md)
- **TDD gate:** `cmd/anvil-guard` (built as `tdd-guard`) + `guard/` + `controlplane/`

## tdd-guard

```sh
go build -o ~/.local/bin/tdd-guard ./cmd/anvil-guard
tdd-guard seal   --tests <globs> --red-command <argv...>   # prove RED, record the seal
tdd-guard verify --green-command <argv...>                 # prove GREEN (must postdate seal)
tdd-guard diff-review record --findings <file>             # review the real diff before stopping
```

The agents and skills are plain Markdown + small Python helpers, installed natively per
harness. See [`harness-agents/v3/README.md`](harness-agents/v3/README.md).
