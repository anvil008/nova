---
model: grok-4.6
official_source_urls:
  - https://docs.x.ai/build/overview
  - https://docs.x.ai/build/features/skills-plugins-marketplaces
  - https://docs.x.ai/build/modes-and-commands
  - https://docs.x.ai/build/cli/headless-scripting
  - https://docs.x.ai/build/settings
  - https://docs.x.ai/developers/grok-4-6
fetched_date: 2026-09-02
extractor_version: 1.1.0
normalized_source_digests:
  https://docs.x.ai/build/overview: 6528ca7fccab57dd0ad4f3c0ca5cbcd1eaae799231aedd6ae7eb97d972d9431f
  https://docs.x.ai/build/features/skills-plugins-marketplaces: 09153d9abc2ec9d3d41a68176d16860a2594480cfbfdb0c7490cc0ba3a861e7e
  https://docs.x.ai/build/modes-and-commands: b701adb576cdddc780dbec84e0d32c4790f285bf20cfe3bed76ad58532923b0f
  https://docs.x.ai/build/cli/headless-scripting: 72a90f0af02f262b6cefd304e7d48e5bd85b6322aaef1a32725a25a289cf3c15
  https://docs.x.ai/build/settings: 1399d893e91b91502dc5b1f95142c46d093f46c78e56b1038ec99317f1b6218c
  https://docs.x.ai/developers/grok-4-6: 7b1b32fa102b086006751b5bb5c2f72a09e605ed3f74942eeb2470f32e762fdc
---
# Grok Build with Grok 4.6

This is a concise implementation extract for generating Workcell's Grok Build
instructions. It was checked against the official xAI sources above and the
installed Grok Build 1.0.13 user guide. That vendored upstream guide comes from
`xai-org/grok-build` and is installed at `~/.grok/docs/user-guide/`.

Grok Build is an extensible coding agent with interactive, headless, and ACP
surfaces. The same `grok-4.6` model is available through the xAI API. Keep
harness instructions about Grok Build's native tools separate from API-only
model properties such as request caching and function-calling parameters.

## Roster pin

On the extraction machine, `grok models` reported `grok-4.6` as both available
and the default model. Workcell's Grok routes in `agents/models.json` must
therefore pin `grok-4.6` rather than inherit an unspecified parent model. The
later generator-owned roster change should consume this recorded decision; this
guide does not own that file.

## Instruction rules

Put durable repository instructions in `AGENTS.md`. Grok walks instruction
files from the repository root toward the working directory and gives deeper
instructions later precedence. It also loads Markdown rules from
`.grok/rules/` at each directory level. Use `--rules` for a one-run addition to
the system prompt, or `--system-prompt-override` only when the entire default
system prompt should be replaced. Keep rules short, specific, scoped, and
version controlled.

## Agents and personas

Agents configure a whole session: model, tools, prompt mode, system prompt, and
skills. Store project agent definitions in `.grok/agents/`. Personas are
behavioral overlays for subagents—tone, output shape, task focus, and
contracts—and project personas live in `.grok/personas/`.

Every child resolves to an agent type. The built-ins are `general-purpose` for
full-capability work, `explore` for investigation, and `plan` for read-only
planning. A persona layers behavior onto that type; it is not passed as a
separate `spawn_subagent` parameter. Prefer explicit agent definitions when a
role needs a fixed toolset or model and personas when only the delegated
behavior or contract differs.

## Input and output contracts

A persona may declare `inputs` and `outputs` so the parent knows what context
to provide and what artifacts to expect. Every contract item has a `name`, an
`io_type` (default `file`), a `required` boolean, and a `description`. This is
the native seam for chaining roles—for example, one persona's output file can
be the next persona's required input—without hiding the artifact contract in
free-form prose.

## Background subagents

The parent invokes `spawn_subagent` with a complete prompt, short description,
and a `subagent_type`; `background: true` starts the child asynchronously and
returns its ID immediately. Retrieve completion or partial output with
`get_command_or_subagent_output`. Background children have independent context
windows and report summaries to the parent. Grok limits nesting to one level,
so a subagent cannot create another subagent.

## Forks

In the TUI, `/fork` branches the current session into a peer agent. In headless
automation, combine `--fork-session` with `--resume` or `--continue` to copy an
existing conversation into a new session rather than append to the original;
an optional `--session-id` names the new UUID. Use a fork when shared history is
the important input, not as a substitute for an independently scoped subagent.

## Workflows

Workflows orchestrate a bounded set of background subagents and are enabled by
default. `/create-workflow` asks for fan-out, verification, and scope, then
saves the result under `.grok/workflows/` as a Rhai file. Launch it with
`/workflow <name> [args]`; use the same command with `pause`, `resume`, or
`stop` to control a run. A workflow should own bounded orchestration and return
a verified result, while ordinary one-off delegation should use a subagent.

## Capability modes

Capability mode comes from the selected agent type or role definition, not a
`spawn_subagent` argument:

| Mode | Read | Write | Execute | Intended use |
| --- | --- | --- | --- | --- |
| `read-only` | yes | no | no | Search and inspect without edits or shell |
| `read-write` | yes | yes | no | Modify files without executing commands |
| `execute` | yes | no | yes | Run commands and background tasks without edits |
| `all` | yes | yes | yes | Unrestricted work; default for `general-purpose` |

Choose the narrowest native mode that can satisfy the role, and do not describe
`explore` or `plan` as write-capable.

## Headless flags

Use `grok -p "<prompt>"` for a non-interactive run. Pin automation explicitly:
`--model grok-4.6`, `--effort high`, and an `--output-format` of `plain`, `json`,
or `streaming-json`. `--always-approve` skips ordinary tool prompts, but deny
rules, hooks, and matching shell-command ask rules still apply; pair it with
reviewed boundaries rather than treating it as a sandbox.
`--max-turns` bounds the agent loop; `--no-plan` disables plan mode;
`--no-subagents` prevents child spawning; and `--no-auto-update` avoids update
checks during scripts and CI. Use `--cwd` to name the target workspace. For
machine consumers, prefer JSON output and inspect its exit status and terminal
event rather than scraping TUI text.

## Unsupported fields

The current official skills page says Grok accepts the skill frontmatter field
`allowed-tools`, but it does not grant or restrict tools. It likewise says
`model`, `effort`, `license`, and `compatibility` are accepted but not applied.
Treat those five fields as unsupported for enforcement and routing under the
official contract: do not infer capabilities from them. The installed 1.0.13
vendored guide disagrees for `model` and `effort`, describing them as active
overrides; that conflict needs runtime re-verification before a generator may
depend on the installed-guide behavior. Native CLI tool filtering (`--tools`
and `--disallowed-tools`) and agent capability modes are separate surfaces and
remain applicable.
