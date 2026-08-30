## Gates on Codex

Workcell wires Codex `PreToolUse`, `PostToolUse`, and `Stop` hooks, including `build-guard` for shell commands. They run only after the user trusts the plugin hooks with `/hooks`; in an untrusted or ad-hoc session, call `build-guard codex` yourself before each mutating command — instrumentation and bisect runs are exactly the operations it exists to check.
