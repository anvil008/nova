# Swarm Coder

A multi-agent coding system for **Claude Code**, **Codex**, and **Antigravity**.

It turns a goal into a reviewable plan, hands each implementation task to an isolated
builder, and uses mechanical gates — not promises — to keep the combined result
verifiable. The point is to run coding agents in parallel without losing human approval,
test evidence, ownership boundaries, or a resumable GitHub record.

One repository, three harnesses, the same agents and skills in each.

---

## Install

Two commands. The first installs the external tools, the second installs the plugin.

```sh
git clone https://github.com/anvil008/swarm-coder
cd swarm-coder

scripts/bootstrap-tools.sh --install     # 1. external dependencies + the tdd-guard gate
scripts/bootstrap-plugins.sh             # 2. the swarm-coder plugin, into every harness found
```

That is the whole setup. Run either script with no flags to see what it *would* do
before it does anything (`bootstrap-tools.sh` reports; `bootstrap-plugins.sh --help`
explains).

| | What it does |
|---|---|
| `scripts/bootstrap-tools.sh --install` | Installs Go, jq, `jj`, `gh`, formatters and linters where a package manager is available, builds `tdd-guard`, and links the `build-*` hook commands into `~/.local/bin`. |
| `scripts/bootstrap-plugins.sh` | Installs the `swarm-coder` plugin into Claude Code, Codex, and Antigravity — whichever are present. |

Useful flags for the second command:

```sh
scripts/bootstrap-plugins.sh --harness claude   # one harness only (claude | codex | agy)
scripts/bootstrap-plugins.sh --uninstall        # remove everything it installed
```

It never overwrites something it does not own. A real file or directory where a link
should go is refused by name, and the run exits non-zero rather than clobbering it.

### Per-project install

To set up one repository instead of your whole machine:

```sh
scripts/bootstrap-project.sh --install --with-hooks /path/to/project
```

This detects the project's stack, installs the formatters and linters that stack needs,
installs the plugin at project scope, and wires the advisory format/lint/guard hooks
into the project. Everything it writes is added to the repository's `info/exclude`, so
none of it shows up in `git diff` or a commit.

---

## How work moves

```mermaid
flowchart TB
    Goal["Goal"]

    subgraph primary["Primary agent — plans, integrates, never writes issue code"]
        direction TB
        Plan["<b>planner</b> skill<br/><i>HTML folio + plan.sidecar.json</i>"]
        Issues["GitHub milestone<br/>and issues, in waves"]
        Integrate["serial merge + retest<br/><i>combined GREEN</i>"]
    end

    Gate{"Human approval"}

    subgraph wave["One wave — disjoint ownership, parallel"]
        direction LR
        B1["<b>builder</b> agent<br/><i>jj workspace · issue A</i>"]
        B2["<b>builder</b> agent<br/><i>jj workspace · issue B</i>"]
    end

    R1["<b>code-reviewer</b> agents<br/><i>read-only · 2 passes</i>"]
    PRs["Pull requests<br/><i>--base main</i>"]
    Ship["<b>deploy</b> skill<br/><i>human-gated</i>"]

    Goal --> Plan
    Plan --> Gate
    Gate -->|changes requested| Plan
    Gate -->|approved| Issues
    Issues --> B1 & B2
    B1 & B2 --> R1
    R1 -->|"critical/high clear"| PRs
    R1 -.->|"still critical/high"| Blocked["returns <b>blocked</b><br/>no PR"]
    PRs --> Integrate
    Blocked -.-> Issues
    Integrate --> Ship
```

In words: the **primary agent** runs the `planner` skill to turn a goal into an HTML folio plus
a machine-readable sidecar, and a human approves that plan before any GitHub resource is written.
Approved issues run in dependency waves. Each **builder** agent owns exactly one issue in its own
Jujutsu workspace, branched from the same integration base — `trunk()` unless the primary agent is
deliberately stacking — and it opens its PR with an explicit `--base main`. Before any PR exists a
builder hands its change-set to read-only **code-reviewer** agents for at most two passes; if a
`critical` or `high` finding still stands it returns `blocked` with no PR, and the primary agent
decides whether to re-dispatch, re-scope, or escalate. The primary agent then integrates the wave by
serial merge plus retest and must see a combined GREEN before marking issues done. It never writes
issue code, never merges before combined green, and never force-pushes `main`. Deployment is a
separate human decision.

### Who does what

| Agent | Writes code | Owns | Never |
|---|---|---|---|
| primary (you, in the harness) | no | planning, wave scheduling, integration, final verification | writes issue code, merges before combined GREEN |
| `builder` | yes | one issue, one workspace, one PR | touches another issue's files, pushes `main`, merges its own PR |
| `code-reviewer` | no | assurance lenses over one change-set | edits anything it reviews |
| `research` | no | investigation that feeds a plan | changes behaviour |
| `docs` | yes | READMEs, ADRs, the documentation gate | product code |

---

## How the repository is laid out

```mermaid
flowchart TB
    subgraph source["Single source"]
        direction TB
        A["<b>agents/</b><br/>claude · codex · agy"]
        S["<b>skills/</b><br/>planner · build · code-review · docs · deploy · …"]
        H["<b>scripts/hooks/</b> + <b>cmd/tdd-guard/</b><br/>the mechanical gates"]
    end

    subgraph wrappers["plugins/ — one thin wrapper per harness"]
        direction TB
        PC["<b>plugins/claude/</b><br/>.claude-plugin/plugin.json<br/>hooks/hooks.json"]
        PX["<b>plugins/codex/</b><br/>.codex-plugin/plugin.json<br/>hooks.json"]
        PA["<b>plugins/agy/</b><br/>plugin.json · rules/<br/>hooks.json"]
    end

    subgraph harness["Installed"]
        direction TB
        IC["Claude Code<br/><i>swarm-coder@swarm-coder-local</i>"]
        IX["Codex<br/><i>swarm-coder@swarm-coder-local</i>"]
        IA["Antigravity<br/><i>~/.gemini/antigravity-cli/plugins/</i>"]
    end

    source -->|"symlinked into"| wrappers
    PC -->|"marketplace · claude CLI"| IC
    PX -->|"marketplace · codex CLI"| IX
    PA -->|"symlink"| IA
```

In words: `agents/` and `skills/` hold the real content once. Each `plugins/<harness>/`
directory is a thin wrapper — a manifest, a `hooks.json`, and symlinks back to the
agents and skills it exposes. Claude Code and Codex install that wrapper through a local
marketplace declared at the repository root, using their own CLIs. Antigravity has no
plugin CLI, so its wrapper is symlinked into place and stays live.

| Directory | What lives there |
|---|---|
| [`agents/`](agents/) | Agent definitions per harness: research, builder, code-reviewer, docs. |
| [`skills/`](skills/) | The shared workflows: planner, build, code-review, docs, deploy, and support skills. |
| [`plugins/`](plugins/) | One thin wrapper per harness. No content of its own. |
| [`scripts/`](scripts/) | The three bootstrap commands, plus the hook scripts they install. |
| [`cmd/tdd-guard/`](cmd/tdd-guard/) | The gate binary that binds failing tests, passing tests, and review evidence to an exact change. |
| [`docs/adr/`](docs/adr/) | Architecture decisions and their consequences. |

Adding a skill means adding a directory under `skills/` — no manifest edit. Claude and
Codex link `skills/` whole; the Antigravity wrapper's per-skill links are regenerated on
every install from `skills/` minus the skills owned by one of its agents.

---

## What you get

Once installed, these workflows are available in each harness:

- **`planner`** — investigates a substantial change and produces an offline HTML plan
  plus `plan.sidecar.json`. GitHub reconciliation waits for explicit approval.
- **`build`** — executes an approved milestone as resumable dependency waves in isolated
  Jujutsu workspaces.
- **`code-review`** — runs independent assurance lenses, verifies candidates, renders an
  offline report, and reconciles approved findings.
- **`docs`** — keeps READMEs newcomer-friendly, updates documentation in place, records
  ADRs, and runs the documentation gate.
- **`deploy`** — preflight checks, an approved release, post-deploy verification, and
  rollback preparation.

Supporting skills cover research, frontend implementation and review, bounded review/fix
loops, Jujutsu, and explicitly requested alternate harnesses.

## Core guarantees

- **Human gates.** Planning approval and deployment approval are explicit. Silence is
  never treated as consent.
- **Isolated parallel work.** The build skill schedules non-overlapping issues into
  dependency waves and gives each builder its own `jj` workspace.
- **Evidence-bound integration.** Builders prove RED then GREEN, review their own diff,
  and return command-linked evidence. The primary agent retests the combined wave.
- **Resumable tracking.** Stable markers connect planner sidecars, GitHub milestones,
  issues, reports, and review findings — without GitHub Projects.
- **Accessible communication.** Every meaningful visual is paired with text that conveys
  the same relationships ([ADR 0004](docs/adr/0004-visuals-require-text-equivalents.md)).
- **Cross-harness parity.** The same skills reach all three harnesses; role-specific
  capabilities stay explicit in the agent definitions.

## Mechanical gates

Every builder is bound by `tdd-guard`, which turns TDD from a promise into a state machine. The
guard is a real binary (`cmd/tdd-guard/`, `guard/`), installed by `bootstrap-tools.sh`; the
`scripts/hooks/build-*` commands are what wire it into a harness's tool events.

```mermaid
flowchart TB
    Red["Write the acceptance<br/>tests · run RED"]
    Seal["<b>seal</b><br/><i>--tests · --red-command</i>"]
    Impl["Implement"]
    Verify["<b>verify</b><br/><i>--green-command</i>"]
    Review["<b>diff-review record</b><br/><i>--findings</i>"]
    Stop{"Stop hook<br/><i>evidence fresh?</i>"}
    PR["PR allowed"]

    Red --> Seal --> Impl --> Verify --> Review --> Stop
    Stop -->|yes| PR
    Stop -->|no| Impl
    Impl -.->|"edit a sealed test"| Denied["denied<br/><i>reseal --reason</i>"]
    Denied -.-> Impl
```

In words, and in the order a builder hits them:

1. **`tdd-guard seal --tests <globs> --red-command <argv...>`** records the exact failing command and
   a digest of every sealed test file. RED has to be real and non-zero before the seal is taken.
2. **While implementing, sealed tests are read-only.** A `PreToolUse` edit of a sealed path is
   *denied*, not warned about; changing one out-of-band is flagged the moment the guard sees it. The
   only legitimate amendment is `tdd-guard reseal --reason <text>`, after proving the amended test
   fails for the intended reason.
3. **`tdd-guard verify --green-command <argv...>`** accepts the run only if the tests are byte-identical
   to the seal and the GREEN run *postdates* it. Optional `--coverage-command` and `--min-coverage`
   add a coverage floor; `tdd-guard arch-check --assertions <file>` asserts structural invariants.
4. **`tdd-guard diff-review record --findings <file>`** binds review findings to the current diff. Change
   the diff afterwards and the record goes stale.
5. **The Stop hook refuses to let a builder finish** while any of that is missing: sealed tests changed
   without a recorded amendment, no green evidence, green evidence older than the current seal, or a
   missing/stale diff review. `tdd-guard status --json` reports the same state for a human or the
   primary agent.

Alongside the TDD state machine, `build-guard` inspects each shell command *before* it runs and fails
closed on malformed tool payloads, protected-branch mutations, unsafe Git/jj/GitHub operations, and
RAM-tmpfs build targets. `build-format` and `build-lint` auto-format written files and feed
single-file lint findings back to the agent.

Claude Code and Antigravity wire these to native tool events; Codex has no equivalent hook surface, so
its builder calls `build-guard codex` and the `tdd-guard` commands explicitly — the codex builder
definition says so in its own procedure.

---

## Verify the repository

The same substantive checks CI runs:

```sh
go mod tidy && git diff --exit-code -- go.mod go.sum
go build ./... && go vet ./... && go test -count=1 -race ./...
bash scripts/hooks/tests/test_hooks.sh
bash scripts/tests/test_install.sh
ruff check skills/
shellcheck -S warning scripts/*.sh scripts/hooks/build-*
for d in skills/*/tests; do python3 -m unittest discover -s "$d" -p 'test_*.py'; done
python3 skills/docs/scripts/docs_check.py .
```

Architecture decisions live in [`docs/adr/`](docs/adr/); notable changes are summarized
in [`CHANGELOG.md`](CHANGELOG.md).

## Upgrading from an earlier install

Earlier versions linked agents and skills straight into `~/.claude/agents`,
`~/.codex/skills`, and friends, and later linked plugin wrappers into
`~/.claude/plugins/`. Neither Claude Code nor Codex ever discovered those links.

```sh
scripts/bootstrap-plugins.sh --uninstall   # sweeps the legacy links
scripts/bootstrap-plugins.sh               # installs through the marketplaces
```

See [ADR 0006](docs/adr/0006-plugins-install-through-local-marketplaces.md) for why the
mechanism changed.
