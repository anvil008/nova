# Agent handoff contract

This contract defines the brief a caller sends to a Workcell agent and the one record the agent returns. The caller is the orchestrator, or the authorized planner for its researcher children. Fields that do not apply to a dispatch are `null` or empty as described below; they are not silently reinterpreted.

## Dispatch brief

- `issue`: the GitHub issue number, or `null` when the work has no issue.
- `brief`: an object whose `goal` is the goal in prose. For a no-issue dispatch, it also carries `acceptanceTests[]`, each with `name`, `kind`, and `oracle`. `brief.testOwnership[]` optionally authorizes explicit test-only paths or globs for the specifier outside implementation ownership. For planned issues, derive these from approved `acceptanceTests[].testPath`. Include them in scheduling collision checks; they never authorize the builder to edit sealed tests.
- `workspace`: the assigned workspace path. A standard specifier creates it; agents dispatched after that creation and non-standard modes receive an existing path. Whoever creates a jj workspace names it with the dispatch's `branch`.
- `branch`: the branch or bookmark assigned to the work and, when a jj workspace is created for it, that workspace's name. A standard specifier creates both; other agents receive them pre-created.
- `base`: the pinned source commit, `trunk()`, or named integration branch from which the work was based. Single-change records pin an immutable commit; milestone runs also record the accepted integration ref.
- `ownership`: the glob delimiting files the agent may change. For an issue dispatch it is copied from the issue's `ownershipHint`; for a no-issue dispatch it is authoritative on its own.
- `mode`: `standard` by default; builders may use `refactor` or internal repair mode `loop`, and integrators may use `baseline`. `brief.planning` carries `choicePath` and artifact ownership from `skills/plan/references/planning-modes.md`. Its saved single/multiple choice controls plan output, not researcher count. Planners direct research within the user's scope and constraints; the orchestrator proxies dispatch where needed. Target source stays read-only during planning.
- `sealedTests`: the sealed test globs, or an empty array when the dispatch has no seal. A seal records `kind: red|baseline`; both kinds protect the same paths and use the same downstream verification and Stop gates.
- `redCommand`: the argv that demonstrated RED for a `kind: red` seal, or `null` when RED does not apply.
- `baselineCommand`: the argv that demonstrated GREEN and is bound by a `kind: baseline` seal for a refactor/baseline dispatch, or `null` when a green baseline seal does not apply.
- `devServer`: reviewers only; `none`, a non-production URL, or `start: <command>`.
- `runtime`: builders only; an optional hint object `{launch, url, healthPath}` telling the builder how to run the surface it changed — `launch` is the command that starts it, `url` is where it answers, `healthPath` is a service's health path. It is `null` or absent when the orchestrator has no hint, and the builder then discovers the run command from the repo. A production URL is never a valid hint.
- `approval`: deployer only; an object naming `who`, `when`, `target`, and `commit`. It is `null` for every other agent.
- `model`: optional model string assigned for the agent dispatch (e.g. `claude-sonnet-5`, `gemini-3.7-flash`), or `null` when unset.
- `effort`: optional reasoning effort level (`low`, `medium`, `high`), or `null` when unset.

## Dispatch brief example

```json
{
  "issue": null,
  "brief": {
    "goal": "Reject empty API tokens without starting a request.",
    "acceptanceTests": [
      {
        "name": "empty_token_is_rejected",
        "kind": "unit",
        "oracle": "An empty token raises ValueError before the transport is called."
      }
    ]
  },
  "workspace": "/work/workcell-empty-token",
  "branch": "empty-token",
  "base": "trunk()",
  "ownership": "src/auth/**",
  "mode": "standard",
  "sealedTests": ["tests/test_auth.py"],
  "redCommand": ["python3", "-m", "unittest", "tests.test_auth"],
  "baselineCommand": null,
  "devServer": "none",
  "runtime": null,
  "approval": null,
  "model": "claude-sonnet-5",
  "effort": "high"
}
```

## Handoff record

Every agent returns one `anvil.agent-handoff/v1` JSON object with these fields:

- `schema`: exactly `anvil.agent-handoff/v1`.
- `agent`: the Workcell agent name.
- `issue`: the GitHub issue number, or `null` for a no-issue dispatch.
- `model`: optional model string identifying the model that performed the work, or `null` when unset.
- `effort`: optional reasoning effort level (`low`, `medium`, `high`), or `null` when unset.
- `disposition`: exactly one of `done`, `blocked`, or `needs-decision`.
- `result`: one paragraph stating the outcome.
- `branch`: the assigned branch or bookmark, or `null` when the agent has none.
- `changeId`: the Jujutsu commit change ID (e.g. from `jj log -r @ -T "change_id\n"`), optional or `null` when unset.
- `commitId`: the immutable source commit ID from `jj log --no-graph -r @ -T commit_id` or `git rev-parse HEAD` for a plain Git single change; required for local builder handoffs consumed by `build_run.py`, optional for other agents. A stable `changeId` alone does not pin the tested revision.
- `pr`: the pull-request URL or number, or `null` when the agent does not open one (in local trunk handoff, `pr` is `null`).
- `workspace`: the workspace path used for the work.
- `changedFiles[]`: repository-relative paths changed by the agent.
- `commands[]`: command evidence entries, each containing `argv`, `commandId`, `exitCode`, and `summary`.
- `evidence`: an agent-specific object, such as an acceptance-test map, findings envelope, benchmark distributions, or demonstrated root cause.
- `evidence.runtime`: required whenever the change touches a runnable surface — `{surface: "ui|service|cli|none", commands: [{argv, commandId, exitCode}], observations: "...", consoleErrors: 0, screenshots: [paths]}`. It is the proof the change was exercised rather than only tested. `surface: "none"` claims the change has no runnable surface, and must carry a one-line justification for that claim in `observations`.
- `openQuestions[]`: unresolved questions for the orchestrator; use an empty array when there are none.

A record with a `disposition` outside that enum, or a command entry without a `commandId`, is malformed and the orchestrator treats it as `blocked`.

Local builders retain their workspace until the orchestrator accepts the integration receipt. A single change instead records completion against its exact verified source and retains its workspace until PR merge or explicit abandonment; see `skills/build/references/single-change.md`. Keep handoff files and review findings outside source workspaces. The integrator verifies fresh guard status against `commitId`; the orchestrator records accepted local completion separately from GitHub closure. See `docs/build-runs.md`.

Runtime evidence is judged apart from that: its absence makes a record **incomplete**, not malformed, and the orchestrator re-dispatches the builder with a `runtime` hint rather than blocking. A record is incomplete when `evidence.runtime` is missing, when `surface: "none"` carries no justification in `observations`, or when `surface: "none"` is claimed while `changedFiles` contains a file under the brief's `ownership` that is an entrypoint, route, page, component, or CLI command.

## Handoff record example

```json
{
  "schema": "anvil.agent-handoff/v1",
  "agent": "builder",
  "model": "claude-fable-5-1",
  "effort": "high",
  "issue": 142,
  "disposition": "done",
  "result": "Empty API tokens are now rejected before transport, and the sealed acceptance test plus the project suite pass.",
  "branch": "issue-142-empty-token",
  "changeId": "kpqxyvwnloqtuslrzuvlztkzzuorptvn",
  "pr": null,
  "workspace": "/work/workcell-issue-142",
  "changedFiles": ["src/auth/token.py"],
  "commands": [
    {
      "argv": ["python3", "-m", "unittest", "tests.test_auth"],
      "commandId": "verify-acceptance-1",
      "exitCode": 0,
      "summary": "The sealed token test and neighboring authentication tests passed."
    },
    {
      "argv": ["python3", "-m", "example", "--token", ""],
      "commandId": "runtime-cli-1",
      "exitCode": 2,
      "summary": "The real CLI rejected an empty token before opening a connection."
    }
  ],
  "evidence": {
    "tests": [
      {
        "name": "empty_token_is_rejected",
        "test": "tests.test_auth.TokenTests.test_empty_token_is_rejected",
        "commandId": "verify-acceptance-1"
      }
    ],
    "runtime": {
      "surface": "cli",
      "commands": [
        {
          "argv": ["python3", "-m", "example", "--token", ""],
          "commandId": "runtime-cli-1",
          "exitCode": 2
        }
      ],
      "observations": "The CLI exited 2 and printed `empty API token` before opening a connection.",
      "consoleErrors": 0,
      "screenshots": []
    },
    "reviewPasses": [
      {
        "pass": 1,
        "outcome": "No findings."
      }
    ]
  },
  "openQuestions": []
}
```
