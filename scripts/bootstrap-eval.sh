#!/usr/bin/env bash
# bootstrap-eval.sh — put ONE task repository into Workcell eval mode: an unattended benchmark
# run (DeepSWE-style container, hidden verifiers, the agent must produce a patch) with no human
# in the loop and nothing outward-facing.
#
#   scripts/bootstrap-eval.sh <task-dir>               write the marker + the eval preamble
#   scripts/bootstrap-eval.sh --with-hooks <task-dir>  ...and wire the advisory gates into it
#   scripts/bootstrap-eval.sh --force <task-dir>       ...restoring a preamble that was edited
#   scripts/bootstrap-eval.sh --remove <task-dir>      undo everything this script wrote
#
# Design notes:
#  * The switch is mechanical: <task-dir>/.workcell/eval-mode.json. build-guard reads that file
#    and nothing else does, so eval mode cannot be argued into existence by prose.
#  * It is scoped to the task repository. This script refuses to mark the Workcell source tree,
#    and the guard resolves the marker from the repository each command targets, so a workcell
#    checkout on the same machine is never itself in eval mode.
#  * The instruction surface travels with the task repo — one delimited block in its AGENTS.md
#    and CLAUDE.md — so no skill or agent definition needs an eval-only branch.
#  * Advisory gates are wired by bootstrap-project.sh, not re-implemented here. The TDD gates are
#    deliberately untouched: an eval measures the harness WITH its gates (docs/eval-runs.md).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$ROOT/scripts/lib.sh"
BEGIN='<!-- BEGIN workcell eval-mode -->'
END='<!-- END workcell eval-mode -->'
MARKER=".workcell/eval-mode.json"
FILES=(AGENTS.md CLAUDE.md)
usage(){ sed -n '2,20p' "$0"; }

force=0; withhooks=0; remove=0; DIR=""
for a in "$@"; do case "$a" in
  --force) force=1;; --with-hooks) withhooks=1;; --remove) remove=1;;
  -h|--help) usage; exit 0;;
  -*) usage >&2; die "unknown option: $a";;
  *) DIR="$a";; esac; done
[[ -n $DIR ]] || { usage >&2; die "a task directory is required"; }
[[ -d $DIR ]] || die "no such dir: $DIR"
DIR="$(cd "$DIR" && pwd)"; cd "$DIR"

# --- refusals ----------------------------------------------------------------------------------
if [[ $DIR == "$ROOT" ]] || [[ -d cmd/tdd-guard && -d agents/bodies ]]; then
  die "$DIR is the Workcell source tree — the harness runs the eval, it is never the thing evaluated"
fi
git rev-parse --git-dir >/dev/null 2>&1 \
  || die "$DIR is not a git repository — an eval run has to commit its work somewhere"

# --- the eval preamble the task repository carries ----------------------------------------------
# Terse on purpose: it is read by every agent on every turn, and it says only what eval mode
# changes. Everything it does not mention is unchanged, the TDD gates included.
preamble(){
  printf '%s\n' "$BEGIN"
  cat <<'EOF'
## Eval mode

This repository is running under Workcell eval mode: an unattended benchmark run, no human in
the loop. `.workcell/eval-mode.json` is the marker and `build-guard` enforces it.

- **No approval pause.** The planner's folio and JSON sidecar are the plan of record the moment
  they are written; execution proceeds without waiting for anyone to approve them.
- **No interview.** The task statement is the brief. Decide rather than ask, and record the
  assumption in the commit message.
- **GitHub is out of scope.** No `gh`, no issues, no pull requests, no reconcile `--apply`. The
  guard denies every `gh` invocation here, whoever asks.
- **Work lands as ordinary local commits** on this repository's default branch. No branch per
  issue, no PR ceremony; there is usually no remote at all.
- **The deploy skill must refuse.** Nothing outward-facing runs in eval mode.
- **Never read or modify verifier or reference material** — hidden tests, task metadata,
  container definitions, reference solutions. Solving the task is in scope; gaming the verifier
  is not, and neither is looking up its answer.
- **The deliverable is the committed working tree.** The harness collects the diff; do not write
  a patch file or a summary report unless the task asks for one.

The gates are unchanged: `tdd-guard` and the RED -> seal -> GREEN ceremony stay fully active. Eval
mode removes the human pauses and the outward surface, not the mechanical gates.
EOF
  printf '%s\n' "$END"
}
# current_block FILE -> the block this script owns, as it stands in FILE (empty when absent).
current_block(){ awk -v b="$BEGIN" -v e="$END" '$0 == b { k = 1 } k { print } $0 == e { k = 0 }' "$1"; }
# strip_block FILE -> FILE without that block, and without the blank line written after it.
strip_block(){
  awk -v b="$BEGIN" -v e="$END" '
    $0 == b { drop = 1; next }
    $0 == e { drop = 0; blank = 1; next }
    drop    { next }
    blank && $0 == "" { blank = 0; next }
    { blank = 0; print }' "$1"
}
# rewrite FILE < new-content -> replace FILE's content through the symlink, if it is one, so a
# CLAUDE.md symlinked at AGENTS.md keeps pointing where the repository pointed it.
rewrite(){ local tmp; tmp=$(mktemp); cat > "$tmp"; cat "$tmp" > "$1"; rm -f "$tmp"; }

echo "bootstrap-eval: $DIR"

# --- --remove: undo exactly what this script writes ----------------------------------------------
if ((remove)); then
  undo=(.workcell/)
  for f in "${FILES[@]}"; do
    grep -qF "$BEGIN" "$f" 2>/dev/null || continue
    strip_block "$f" | rewrite "$f"
    if [[ -s $f ]]; then echo "  removed the eval preamble from $DIR/$f"
    else rm -f "$f"; echo "  removed $DIR/$f (nothing but the eval preamble was in it)"; fi
    undo+=("$f")
  done
  if [[ -f $MARKER ]]; then rm -f "$MARKER"; echo "  removed $DIR/$MARKER"; fi
  if rmdir .workcell 2>/dev/null; then echo "  removed $DIR/.workcell"; fi
  git_exclude_remove "${undo[@]}" || echo "  not a git repository: nothing to un-exclude"
  echo "done."
  exit 0
fi

# --- the marker the guard reads ------------------------------------------------------------------
if [[ -f $MARKER ]] && ((!force)); then
  echo "  already present  $DIR/$MARKER"
else
  mkdir -p .workcell
  printf '{"mode":"eval","startedAt":"%s","source":"bootstrap-eval"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$MARKER"
  echo "  wrote $DIR/$MARKER"
fi
git_exclude_add .workcell/ || echo "  not a git repository: .workcell/ is not local-ignored"

# --- the preamble, prepended to the instruction files --------------------------------------------
# An instruction file we create is local-ignored like the marker, so it can never reach the scored
# patch. One the task repository already tracks cannot be: say so, because --remove is then the
# only thing that takes the preamble back out of the diff.
for f in "${FILES[@]}"; do
  tracked=0; if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then tracked=1; fi
  if [[ -f $f ]] && grep -qF "$BEGIN" "$f"; then
    if [[ $(current_block "$f") == "$(preamble)" ]]; then echo "  already present  $DIR/$f"; continue; fi
    ((force)) || die "$DIR/$f carries an eval preamble that differs from this one — re-run with --force to restore it"
    { preamble; printf '\n'; strip_block "$f"; } | rewrite "$f"
    echo "  restored the eval preamble in $DIR/$f (--force)"
  else
    { preamble; printf '\n'; if [[ -f $f ]]; then cat "$f"; fi; } | rewrite "$f"
    echo "  wrote the eval preamble into $DIR/$f"
  fi
  if ((tracked)); then echo "  note: $f is tracked here — run --remove before collecting the diff"
  else git_exclude_add "$f" || true; fi
done

# --- optional: the advisory gates, through the script that already knows how -----------------------
if ((withhooks)); then
  echo "== advisory gates =="
  "$ROOT/scripts/bootstrap-project.sh" --install --with-hooks "$DIR" | sed 's/^/  /'
fi

# --- how an eval driver launches the harness against this directory --------------------------------
cat <<EOF
== headless launch (\$TASK is the task statement) ==
  (cd $DIR && claude -p "\$TASK" --dangerously-skip-permissions --output-format stream-json --verbose)
  codex exec --cd $DIR --approve-for-me -o $DIR/.workcell/trace.txt "\$TASK"
  (cd $DIR && agy -p "\$TASK" --dangerously-skip-permissions)
Collect the result with 'git -C $DIR diff <base>..HEAD' — see docs/eval-runs.md.
EOF
echo "done."
