## Gates on Codex

Workcell wires Codex `PreToolUse`, `PostToolUse`, and `Stop` hooks for `build-guard`, `build-hooks`, formatting, and linting. Codex runs plugin hooks only after the user trusts them with `/hooks`. In an untrusted or ad-hoc session, use the explicit commands as the fallback: `build-guard codex` before each mutating command, `tdd-guard seal` once RED is real and honest, and `tdd-guard handoff --to builder` when you finish. Run `tdd-guard status` before handing off; a hand-off whose status shows no seal is incomplete.
