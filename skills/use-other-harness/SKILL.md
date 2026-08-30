---
name: use-other-harness
description: ONLY when the user explicitly asks to run a subagent in a DIFFERENT coding harness (Claude Code, Codex, or Antigravity) via headless mode. The user must name the harness, the model, and the effort. Never invoke this for automatic cross-harness routing — it is an explicit, user-triggered escape hatch, not a router.
---

# Use another harness (headless)

Spin up a one-shot subagent in another harness by calling its headless CLI directly.
This replaces the old `workcell-runplane` run-plane and its MCP: **no service, no control
plane, no foreign-dispatch protocol** — just a direct headless process you launch, wait
on, and read back.

## When to use

Only when the **user explicitly asks** to run work in another harness, and only after they
have specified:

- **harness** — `claude` (Claude Code) · `codex` (Codex) · `antigravity` (`agy`)
- **model** — the exact model id for that harness
- **effort** — the reasoning effort (where the harness supports it)

If any of the three is missing, ask for it. Do not guess a model or effort, and do not
pick a harness on the user's behalf.

## Headless invocation per harness

Run in the target repo/dir; pass the task as the prompt (long briefs via stdin/a file);
capture the result; launch in the background for long jobs and report back when it exits.

**Claude Code**
```bash
claude -p "<task prompt>" --model <model> --effort <low|medium|high> \
  [--agent <name>] --dangerously-skip-permissions
```

**Codex**
```bash
codex exec --cd <dir> -m <model> \
  -c model_reasoning_effort="<low|medium|high>" \
  --approve-for-me -o <out.txt> "<task prompt>"   # long brief: append  < brief.md
```

**Antigravity (`agy`)**
```bash
agy -p "<task prompt>" --model <model> --effort <low|medium|high> \
  --dangerously-skip-permissions
```

## Notes

- Each command auto-approves tools inside a workspace sandbox (`--approve-for-me` /
  `--dangerously-skip-permissions`), so scope it to one repo/dir and review the diff after.
- For long runs, launch in the background and wait for the process to exit rather than
  polling; then read the captured output (`-o` file or stdout) and summarize it.
- Structured result: Codex `-o <file>`; `agy --json-schema <schema>`; Claude
  `--output-format json`.
- This is a leaf capability. The spawned agent does one bounded job and returns its output;
  it does not orchestrate, and you own integrating whatever it produced.
