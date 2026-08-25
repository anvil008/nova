# swarm-runplane foreign dispatch

`codingfleet install` links this file to
`~/.local/share/anvil-coding-fleet/swarm-runplane-foreign-dispatch.md`, which is
the absolute path every rendered orchestrator prompt cites; the orchestrator
runs with a target project as its working directory, so a repository-relative
reference would not resolve.

Read this document only when a coding goal actually requires a different
provider than the current harness. Same-provider work always uses the native
subagent mechanism and never touches the run plane, so carrying this reference
in every orchestrator turn is pure context cost.

The orchestrator prompt keeps only three things inline: `health`,
`capabilities`, and the rule that the bounded brief travels in the
`--request` file while follow-up input travels on stdin. Everything else is
here.

## Service bootstrap

```sh
/home/anvil/.local/bin/swarm-runplane serve
```

| | Default | Override |
|---|---|---|
| URL | `http://127.0.0.1:8083` | `SWARM_RUNPLANE_URL`, `serve --listen` |
| State | `~/.local/state/swarm-runplane` | `SWARM_RUNPLANE_STATE`, `serve --state` |
| Token file | `~/.local/state/swarm-runplane/auth.token` | `SWARM_RUNPLANE_TOKEN_FILE` |
| Token value | read from the token file | `SWARM_RUNPLANE_TOKEN` |

The service rejects non-loopback listeners, non-loopback `Host` headers, and
missing or invalid bearer tokens. It is an explicitly started service, not a
hot-loaded daemon.

## Lifecycle

```sh
swarm-runplane health
swarm-runplane capabilities
swarm-runplane start --request route.json
swarm-runplane list
swarm-runplane status JOB_ID
swarm-runplane events --after 10 JOB_ID
printf '%s\n' 'bounded follow-up' | swarm-runplane send JOB_ID
printf '%s\n' 'bounded resumed turn' | swarm-runplane resume JOB_ID
swarm-runplane cancel JOB_ID
swarm-runplane evidence JOB_ID
```

`send` and `resume` accept assignment text only on stdin. The provider command
is always launched as an argv array, never through a shell, and assignment text
is never added to provider argv.

## Durable goal checkpoints

```sh
printf '%s' '{"goalId":"goal-1","checkpoint":{"objective":"…","nextAction":"…"},"plan":"# plan\n"}' \
  | swarm-runplane goal checkpoint
swarm-runplane goal show goal-1
```

The `goal` verb writes `checkpoint.json` and a short `plan.md` under
`~/.local/state/swarm-runplane/goals/<goalId>/` (or `$SWARM_RUNPLANE_STATE`).
It is served from local state with no HTTP service, no token, and no network:
the orchestrator holds `Filesystem write: none`, so this verb -- also exposed as
the `goal` operation of the `swarm_runplane_lifecycle` MCP tool -- is the only
executable way for it to persist a checkpoint.

## Start document

`anvil.run-plane/v1`:

```json
{
  "route": {
    "sourceHarness": "codex",
    "targetHarness": "agy",
    "exactModel": "gemini-3.7-flash-low",
    "effort": "low",
    "canonicalRoleId": "workflow-research",
    "parentGoalId": "goal-id",
    "capabilityMode": "read-only",
    "repositoryRoot": "/absolute/target/repository",
    "fileOwnership": [],
    "evidenceContract": {"requiredChecks": ["report findings"], "requiredArtifacts": []}
  },
  "brief": "Bounded assignment"
}
```

## Fail-closed rules

- Run `health`, then `capabilities`, before every foreign dispatch. Admission
  requires an observed exact model/effort pair and exact installed canonical
  role bytes.
- Admission rejects Coding Orchestrator, Factory and other global-write roles,
  same-provider routing, repository escapes, overlapping writer ownership, and
  unavailable or conflicting routes.
- Claude receives a CLI-scoped canonical `--agents` override with project
  settings excluded. Claude ignores subagent frontmatter hooks under `--agents`,
  so the `anvil-guard` gate reaches a foreign Claude run through the installed
  `~/.claude/settings.json` registration and `--setting-sources user`.
- A terminal success is accepted only when the child returns the small
  `anvil.agent-handoff/v1` record. Exit zero or narrative success alone is not
  completion.
- The parent orchestrator keeps monitor, resume, message, cancel, evidence,
  integration, and completion authority for every foreign run.
