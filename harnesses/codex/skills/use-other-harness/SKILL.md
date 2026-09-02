---
name: use-other-harness
description: Run one explicitly requested foreign-harness leaf task in headless mode.
---

# Use another harness from Codex

Use this leaf capability only for an explicit user request for a different coding harness that
names the target harness, model, and effort. Never use it as an automatic router or for automatic
cross-harness routing. Ask for any missing value instead of guessing.

Run the target harness's native headless command in the requested workspace. For Codex,
the compatible launch shape is:

```bash
codex exec --cd <dir> -m <model> -c model_reasoning_effort="<effort>" --approve-for-me "<task prompt>"
```

The foreign process performs one bounded job and returns its result. It must not orchestrate more
agents. Capture its exit status and output, then hand both back to the caller.
