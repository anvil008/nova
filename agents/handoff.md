# Agent handoff contract

This contract defines the one brief an orchestrator sends to a Workcell agent and the one record the agent returns. Fields that do not apply to a dispatch are `null` or empty as described below; they are not silently reinterpreted.

## Dispatch brief

- `issue`: the GitHub issue number, or `null` when the work has no issue.
- `brief`: an object whose `goal` is the goal in prose. For a no-issue dispatch, it also carries `acceptanceTests[]`, each with `name`, `kind`, and `oracle`.
- `workspace`: the assigned workspace path. A standard test-author creates it; agents dispatched after that creation and non-standard modes receive an existing path. Whoever creates a jj workspace names it with the dispatch's `branch`.
- `branch`: the branch or bookmark assigned to the work and, when a jj workspace is created for it, that workspace's name. A standard test-author creates both; other agents receive them pre-created.
- `base`: `trunk()` or the named integration branch from which the work was based.
- `ownership`: the glob delimiting files the agent may change. For an issue dispatch it is copied from the issue's `ownershipHint`; for a no-issue dispatch it is authoritative on its own.
- `mode`: `standard` by default; a builder may instead receive `refactor` or `loop`, and an integrator may instead receive `baseline`.
- `sealedTests`: the sealed test globs, or an empty array when the dispatch has no seal.
- `redCommand`: the argv that demonstrated RED, or `null` when RED does not apply.
- `devServer`: reviewers only; `none`, a non-production URL, or `start: <command>`.
- `approval`: deploy only; an object naming `who`, `when`, `target`, and `commit`. It is `null` for every other agent.

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
  "devServer": "none",
  "approval": null
}
```

## Handoff record

Every agent returns one `anvil.agent-handoff/v1` JSON object with these fields:

- `schema`: exactly `anvil.agent-handoff/v1`.
- `agent`: the Workcell agent name.
- `issue`: the GitHub issue number, or `null` for a no-issue dispatch.
- `disposition`: exactly one of `done`, `blocked`, or `needs-decision`.
- `result`: one paragraph stating the outcome.
- `branch`: the assigned branch or bookmark, or `null` when the agent has none.
- `pr`: the pull-request URL or number, or `null` when the agent does not open one.
- `workspace`: the workspace path used for the work.
- `changedFiles[]`: repository-relative paths changed by the agent.
- `commands[]`: command evidence entries, each containing `argv`, `commandId`, `exitCode`, and `summary`.
- `evidence`: an agent-specific object, such as an acceptance-test map, findings envelope, benchmark distributions, or demonstrated root cause.
- `openQuestions[]`: unresolved questions for the orchestrator; use an empty array when there are none.

A record with a `disposition` outside that enum, or a command entry without a `commandId`, is malformed and the orchestrator treats it as `blocked`.

## Handoff record example

```json
{
  "schema": "anvil.agent-handoff/v1",
  "agent": "builder",
  "issue": 142,
  "disposition": "done",
  "result": "Empty API tokens are now rejected before transport, and the sealed acceptance test plus the project suite pass.",
  "branch": "issue-142-empty-token",
  "pr": "https://github.com/example/workcell/pull/187",
  "workspace": "/work/workcell-issue-142",
  "changedFiles": ["src/auth/token.py"],
  "commands": [
    {
      "argv": ["python3", "-m", "unittest", "tests.test_auth"],
      "commandId": "verify-acceptance-1",
      "exitCode": 0,
      "summary": "The sealed token test and neighboring authentication tests passed."
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
