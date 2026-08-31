# Harness eval runs

Eval mode is how Workcell runs unattended against a benchmark task — a DeepSWE-style container
holding a task repository and hidden verifiers, where the agent's only deliverable is a patch.
It removes the two things such a run cannot supply, a human to approve and a GitHub to publish
to, and nothing else. The gates stay on.

The switch is one file, `<task-dir>/.workcell/eval-mode.json`, written by
[`scripts/bootstrap-eval.sh`](../scripts/bootstrap-eval.sh) and read by `build-guard`. It counts
only at the root of the repository it sits in — there is no upward walk, so a marker beside a
repository, or in a directory that is not a repository at all, switches nothing on. The bootstrap
refuses to mark the Workcell source tree, refuses any directory that is not its repository's root,
and the guard resolves the marker from the repository each command targets, so a workcell checkout
on the same machine is never itself in eval mode.

A repository in eval mode neither records to nor consolidates a wiki: every `wiki.py --repo`
subcommand refuses a repository carrying the marker, reads included, so a benchmark run cannot
contaminate — or be contaminated by — a project's persistent knowledge. The marker is read from
the repository the command targets, so a workcell checkout on the same machine keeps its own
namespace. See [ADR 0019](adr/0019-the-wiki-lives-outside-every-repository.md).

Entering eval mode is the operator's act. An agent that tries to write the marker is denied:
`build-guard` refuses the shell vectors (redirection, `tee`, `cp`, `mv`, `install`, `ln`) and
`build-hooks` refuses an `Edit`/`Write` of that path, in or out of eval mode.

## Recipe

```sh
scripts/bootstrap-eval.sh --with-hooks /task            # marker + preamble + advisory gates
export WORKCELL_EVAL_TASK_DIR=/task                     # the belt: export it before launching
(cd /task && claude -p "$TASK" --dangerously-skip-permissions --output-format stream-json --verbose)
codex exec --cd /task --approve-for-me -o /task/.workcell/trace.txt "$TASK"
(cd /task && agy -p "$TASK" --dangerously-skip-permissions)
scripts/bootstrap-eval.sh --remove /task               # before collecting the diff
git -C /task diff <base>..HEAD                          # the scored patch
```

Export `WORKCELL_EVAL_TASK_DIR` in the environment the harness runs in — the bootstrap prints the
line. The marker is read from the repository a command targets, so it says nothing about a command
run from somewhere else; the variable travels with the process. With it set, `gh` is denied from
any working directory, and the default-branch relaxation applies to that one repository alone.

The bootstrap writes a delimited eval preamble into the task repo's `AGENTS.md` and `CLAUDE.md`,
so the instruction surface travels with the task and no skill needs an eval-only branch. An
instruction file it creates is local-ignored through `info/exclude`; one the repository already
tracks cannot be, which is why `--remove` runs before the diff is collected. `--remove` undoes
everything the bootstrap wrote and leaves the repository byte-identical.

## Auto-resolved, still enforced

| Auto-resolved                                                                 | Still enforced                                                                                        |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| The planner's approval pause — the folio and sidecar are the plan of record   | `tdd-guard`: RED -> seal -> GREEN, sealed tests read-only, the Stop gate                              |
| The `new-feature` interview — the task statement is the brief                 | `build-guard`'s branch-rewrite, `update-ref`, xargs, obfuscation and RAM-tmpfs rules                  |
| Commit, merge, rebase, cherry-pick and push on the task repo's default branch | The deploy skill, which must refuse: nothing outward-facing runs                                      |
| —                                                                             | Every `gh` invocation, denied outright — including the merge the main conversation may otherwise make |
| —                                                                             | Writing `.workcell/eval-mode.json` — an agent may not put itself into eval mode                       |

An eval measures the harness _with_ its gates. Relaxing the TDD ceremony would score a different
harness than the one that ships, so the marker does not touch it. See
[ADR 0013](adr/0013-eval-mode-removes-the-human-pauses-not-the-gates.md).

## Legitimacy

A benchmark result only means something if the run solved the task rather than the scoring:

- Never read or modify verifier material — hidden tests, task metadata, container definitions,
  scoring scripts. Solving the task is in scope; gaming the verifier is not.
- Never read a reference solution, in the container or anywhere else.
- Never edit the task repository outside the working tree the diff is collected from.
- The deliverable is the committed working tree. If a run cannot solve the task, it says so.

The preamble states all four in the task repository itself, so every agent in the run reads them.
