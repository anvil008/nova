#!/usr/bin/env bash
# Tests for the builder aux hooks (build-format / build-lint / build-guard / build-hooks).
# Hermetic: everything that touches $HOME runs under a throwaway HOME whose .local/bin is
# populated with symlinks, and the real ~/.local/bin is snapshotted before/after to prove it
# was never written. Tool-dependent assertions skip gracefully when the formatter/linter is
# absent, so this stays green in a minimal CI image; the guard corpus always runs.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$(dirname "$HERE")"
FMT="$DIR/build-format"; LINT="$DIR/build-lint"; GUARD="$DIR/build-guard"; HOOKS="$DIR/build-hooks"
CORPUS="$HERE/guard-corpus.txt"
REAL_HOME="$HOME"; REAL_BIN="$REAL_HOME/.local/bin"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ printf 'ok   %s\n' "$1"; pass=$((pass+1)); }
no(){ printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
check(){ if "$@"; then ok "$name"; else no "$name"; fi; }

# --- snapshot the real ~/.local/bin so we can prove nothing below wrote to it ------------------
snapshot_bin(){
  [[ -d $REAL_BIN ]] || { echo absent; return; }
  find "$REAL_BIN" -mindepth 1 -maxdepth 1 -print0 | sort -z \
    | xargs -0 stat -c '%n %Y %F %N' 2>/dev/null \
    || find "$REAL_BIN" -mindepth 1 -maxdepth 1 -exec stat -f '%N %m %HT %Y' {} +
}
before_bin="$(snapshot_bin)"

# --- hermetic HOME + BIN: symlinks only, so a stray write lands here and not in the real one ---
export HOME="$TMP/home"; BIN="$HOME/.local/bin"; mkdir -p "$BIN"
for t in bash sh awk sed grep cat jq env printf tr sort find xargs stat mktemp python3 install; do
  p=$(PATH="$PATH" command -v "$t" 2>/dev/null) && ln -sfn "$p" "$BIN/$t"
done
export PATH="$BIN:$PATH"
export GIT_CONFIG_NOSYSTEM=1

j(){ jq -nc --arg f "$1" '{tool_input:{file_path:$f}}'; }        # Edit/Write payload
jb(){ jq -nc --arg c "$1" '{tool_input:{command:$c}}'; }         # Claude/Codex Bash payload
jbi(){ jq -nc --arg c "$1" --arg a "$2" '{agent_id:$a,tool_input:{command:$c}}'; }    # ... from a subagent
jbt(){ jq -nc --arg c "$1" --arg a "$2" '{agent_type:$a,tool_input:{command:$c}}'; }  # ... naming only its type
ja(){ jq -nc --arg c "$1" '{toolCall:{name:"run_command",args:{CommandLine:$c}}}'; }  # agy payload
denied_claude(){ jq -e '.hookSpecificOutput.permissionDecision=="deny" and (.hookSpecificOutput.permissionDecisionReason|length>0)' >/dev/null 2>&1; }
denied_agy(){ jq -e '.decision=="deny" and (.reason|length>0)' >/dev/null 2>&1; }
mkrepo(){
  local d=$1 br=${2:-issue-1}
  git -c init.defaultBranch="$br" init -q "$d"
  git -C "$d" config user.email t@example.invalid
  git -C "$d" config user.name t
  printf 'x\n' > "$d/f"; git -C "$d" add f
  git -C "$d" -c commit.gpgsign=false commit -qm init
}

# --- build-guard corpus: every probe, every payload shape ----------------------------------------
CORPUS_CWD="$TMP/corpus-repo"
git -c init.defaultBranch=issue-1 init -q "$CORPUS_CWD"
mkdir -p "$CORPUS_CWD/.agents/plugins/workcell"
# The eval-mode corpus runs in its own repository — checked out on main, carrying the marker
# bootstrap-eval.sh writes — so a `@…-eval` probe can never leak eval mode into the ordinary ones.
EVAL_CWD="$TMP/corpus-eval-repo"
mkrepo "$EVAL_CWD" main
mkdir -p "$EVAL_CWD/.agents/plugins/workcell" "$EVAL_CWD/.workcell"
printf '{"mode":"eval","startedAt":"1970-01-01T00:00:00Z","source":"bootstrap-eval"}\n' \
  > "$EVAL_CWD/.workcell/eval-mode.json"

# verdict <shape> <command> -> prints allow|deny|error. A shape is the payload one caller sends:
# a harness's own session names nobody, a subagent's names it with agent_id or agent_type.
verdict(){
  local shape=$1 cmd=$2 out rc
  case $shape in
    agy)          out=$(ja "$cmd" | (cd "$CORPUS_CWD" && "$GUARD" agy) 2>"$TMP/err"); rc=$? ;;
    claude-agent) out=$(jbi "$cmd" agent_01 | (cd "$CORPUS_CWD" && "$GUARD") 2>"$TMP/err"); rc=$? ;;
    codex-agent)  out=$(jbt "$cmd" workcell:builder | (cd "$CORPUS_CWD" && "$GUARD" codex) 2>"$TMP/err"); rc=$? ;;
    codex)        out=$(jb "$cmd" | (cd "$CORPUS_CWD" && "$GUARD" codex) 2>"$TMP/err"); rc=$? ;;
    claude-eval)  out=$(jb "$cmd" | (cd "$EVAL_CWD" && "$GUARD") 2>"$TMP/err"); rc=$? ;;
    claude-agent-eval) out=$(jbi "$cmd" agent_01 | (cd "$EVAL_CWD" && "$GUARD") 2>"$TMP/err"); rc=$? ;;
    agy-eval)     out=$(ja "$cmd" | (cd "$EVAL_CWD" && "$GUARD" agy) 2>"$TMP/err"); rc=$? ;;
    *)            out=$(jb "$cmd" | (cd "$CORPUS_CWD" && "$GUARD") 2>"$TMP/err"); rc=$? ;;
  esac
  [[ $rc -eq 0 ]] || { echo "error(rc=$rc)"; return; }
  if [[ -z ${out//[[:space:]]/} ]]; then echo allow; return; fi
  case $shape in
    agy*) printf '%s' "$out" | denied_agy && { echo deny; return; } ;;
    *)   printf '%s' "$out" | denied_claude && { echo deny; return; } ;;
  esac
  echo "malformed($out)"
}
# Shapes an unscoped probe must satisfy: a top-level session, a subagent, and Antigravity. A probe
# scoped with `@shape` runs in that shape alone, which is how the merge-authority split is pinned.
shapes=(claude claude-agent agy)
probes=0
while IFS= read -r line || [[ -n $line ]]; do
  [[ -z $line || $line == \#* ]] && continue
  expected=${line%%|*}; cmd=${line#*|}
  run=("${shapes[@]}"); [[ $expected == *@* ]] && { run=("${expected#*@}"); expected=${expected%%@*}; }
  probes=$((probes+1))
  for h in "${run[@]}"; do
    got=$(verdict "$h" "$cmd")
    if [[ $got == "$expected" ]]; then ok "guard($h) $expected: $cmd"
    else no "guard($h) expected $expected got $got: $cmd"; fi
  done
done < "$CORPUS"
name="corpus has >= 40 probes (has $probes)"; check [ "$probes" -ge 40 ]
name="corpus has deny probes";  check grep -q '^deny|'  "$CORPUS"
name="corpus has allow probes"; check grep -q '^allow|' "$CORPUS"

guard_out=""; guard_rc=0
guard_in(){
  local dir=$1 harness=$2 cmd=$3
  case $harness in
    agy) guard_out=$(ja "$cmd" | (cd "$dir" && "$GUARD" agy) 2>"$TMP/err"); guard_rc=$? ;;
    *)   guard_out=$(jb "$cmd" | (cd "$dir" && "$GUARD")     2>"$TMP/err"); guard_rc=$? ;;
  esac
}
is_deny_claude(){ printf '%s' "$1" | denied_claude; }
is_deny_agy(){ printf '%s' "$1" | denied_agy; }
is_allow(){ [[ $guard_rc -eq 0 && -z ${1//[[:space:]]/} ]]; }
reason_of(){ printf '%s' "$1" | jq -r '.hookSpecificOutput.permissionDecisionReason // .reason // empty' 2>/dev/null; }

aliased="$TMP/repo-aliased"; mkrepo "$aliased"; git -C "$aliased" config alias.p push
plain="$TMP/repo-plain"; mkrepo "$plain"
benign="$TMP/repo-benign"; mkrepo "$benign"; git -C "$benign" config alias.s status
mkdir -p "$aliased/.agents/plugins/workcell"
guard_in "$aliased" claude 'git p origin main'; name="guard denies a configured alias that expands to push (claude)"; check is_deny_claude "$guard_out"
guard_in "$aliased" agy 'git p origin main'; name="guard denies a configured alias that expands to push (agy)"; check is_deny_agy "$guard_out"
guard_in "$plain" claude 'git p origin main'; name="guard allows the same payload where no such alias is configured"; check is_allow "$guard_out"
guard_in "$plain" agy 'git p origin main'; name="guard allows the same payload where no such alias is configured (agy)"; check is_allow "$guard_out"
guard_in "$benign" claude 'git s'; name="guard allows an alias that expands to an unpoliced subcommand"; check is_allow "$guard_out"
guard_in "$aliased" claude 'git p origin issue-12'; name="guard allows a resolved alias pushing an issue branch"; check is_allow "$guard_out"

onmain="$TMP/repo-on-main"; mkrepo "$onmain" main
onmaster="$TMP/repo-on-master"; mkrepo "$onmaster" master
onissue="$TMP/repo-on-issue"; mkrepo "$onissue" issue-1
detached="$TMP/repo-detached"; mkrepo "$detached" main; git -C "$detached" checkout -q --detach
norepo="$TMP/not-a-repo"; mkdir -p "$norepo"
mkdir -p "$onmain/.agents/plugins/workcell"
guard_in "$onmain" claude 'git commit -m x'; name="guard denies commit while HEAD is main (claude)"; check is_deny_claude "$guard_out"
name="guard reason names main"; check sh -c 'printf %s "$1" | grep -q main' _ "$(reason_of "$guard_out")"
guard_in "$onmain" agy 'git commit -m x'; name="guard denies commit while HEAD is main (agy)"; check is_deny_agy "$guard_out"
guard_in "$onmain" claude 'git merge feat'; name="guard denies merge while HEAD is main"; check is_deny_claude "$guard_out"
guard_in "$onmain" claude 'git rebase feat'; name="guard denies rebase while HEAD is main"; check is_deny_claude "$guard_out"
guard_in "$onmain" claude 'git cherry-pick abc123'; name="guard denies cherry-pick while HEAD is main"; check is_deny_claude "$guard_out"
guard_in "$onmaster" claude 'git commit -m x'; name="guard denies commit while HEAD is master"; check is_deny_claude "$guard_out"
guard_in "$onissue" claude 'git commit -m x'; name="guard allows commit on an issue branch"; check is_allow "$guard_out"
guard_in "$onissue" agy 'git commit -m x'; name="guard allows commit on an issue branch (agy)"; check is_allow "$guard_out"
guard_in "$detached" claude 'git commit -m x'; name="guard allows commit with a detached HEAD"; check is_allow "$guard_out"
guard_in "$norepo" claude 'git commit -m x'; name="guard allows commit outside a repository"; check is_allow "$guard_out"
guard_in "$onmain" claude 'git status'; name="guard allows a read-only command on main"; check is_allow "$guard_out"

# Antigravity's plugin hook is session-global. Without a payload identity, only projects carrying
# bootstrap-project's Workcell marker are in scope; Claude and Codex remain plugin-scoped.
agy_scope="$TMP/repo-agy-scope"; mkrepo "$agy_scope" issue-1
guard_in "$agy_scope" agy 'git push origin main'
name="agy guard is silent outside an opted-in project"; check is_allow "$guard_out"
mkdir -p "$agy_scope/.agents/plugins/workcell" "$agy_scope/nested/deep"
guard_in "$agy_scope" agy 'git push origin main'
name="agy guard denies inside an opted-in project"; check is_deny_agy "$guard_out"
guard_in "$agy_scope/nested/deep" agy 'git push origin main'
name="agy guard finds the Workcell marker in an ancestor"; check is_deny_agy "$guard_out"
guard_in "$agy_scope" claude 'git push origin main'
name="Claude remains enforced independent of the Agy scope marker"; check is_deny_claude "$guard_out"
codex_payload='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git push origin main"}}'
guard_out=$(printf '%s' "$codex_payload" | (cd "$TMP/not-a-repo" && "$GUARD" codex) 2>"$TMP/err"); guard_rc=$?
name="Codex remains enforced independent of the Agy scope marker"; check is_deny_claude "$guard_out"
set +e
guard_out=$(printf '%s' '{"toolCall":{"name":"run_command","args":{}}}' | (cd "$agy_scope" && "$GUARD" agy) 2>"$TMP/err"); guard_rc=$?
set -u
name="malformed Agy payload still fails closed before scoping"; check [ "$guard_rc" -eq 2 ]
name="malformed Agy payload explains the failure"; check grep -q 'no command' "$TMP/err"

# --- merge authority: the payload's caller identity decides, and nothing else --------------------
# Same repository, same environment, same command: only the payload differs between a harness's
# own session and one of its subagents, so these assertions pin the wording of both verdicts.
for h in claude codex; do
  guard_out=$(jb 'gh pr merge 12 --merge' | (cd "$plain" && "$GUARD" "$h") 2>"$TMP/err"); guard_rc=$?
  name="$h session may merge a pull request"; check is_allow "$guard_out"
  guard_out=$(jbi 'gh pr merge 12 --merge' agent_01 | (cd "$plain" && "$GUARD" "$h") 2>"$TMP/err"); guard_rc=$?
  name="$h subagent may not merge (agent_id)"; check is_deny_claude "$guard_out"
  name="$h subagent merge reason hands the PR back"
  check sh -c 'printf %s "$1" | grep -qF "must not merge pull requests — hand the PR back for review"' _ "$(reason_of "$guard_out")"
  guard_out=$(jbt 'gh pr merge 12 --merge' workcell:builder | (cd "$plain" && "$GUARD" "$h") 2>"$TMP/err"); guard_rc=$?
  name="$h subagent may not merge (agent_type alone)"; check is_deny_claude "$guard_out"
  guard_out=$(jb 'gh pr merge 12 --merge --admin' | (cd "$plain" && "$GUARD" "$h") 2>"$TMP/err"); guard_rc=$?
  name="$h session may not merge with --admin"; check is_deny_claude "$guard_out"
  name="$h --admin reason names the checks it would bypass"
  check sh -c 'printf %s "$1" | grep -qF "bypasses the checks the pull request exists for"' _ "$(reason_of "$guard_out")"
  guard_out=$(jb 'gh pr merge 12 --auto' | (cd "$plain" && "$GUARD" "$h") 2>"$TMP/err"); guard_rc=$?
  name="$h session may not arm --auto"; check is_deny_claude "$guard_out"
  guard_out=$(jb 'gh api -X PUT repos/o/r/pulls/12/merge' | (cd "$plain" && "$GUARD" "$h") 2>"$TMP/err"); guard_rc=$?
  name="$h session may merge through the API"; check is_allow "$guard_out"
  guard_out=$(jbi 'gh api -X PUT repos/o/r/pulls/12/merge' agent_01 | (cd "$plain" && "$GUARD" "$h") 2>"$TMP/err"); guard_rc=$?
  name="$h subagent may not merge through the API"; check is_deny_claude "$guard_out"
  name="$h API merge reason names the API"
  check sh -c 'printf %s "$1" | grep -qF "merge pull requests via the API"' _ "$(reason_of "$guard_out")"
done
# Antigravity hooks are session-wide, so no merge there is attributable: deny with or without a name.
guard_in "$agy_scope" agy 'gh pr merge 12 --merge'
name="agy denies a merge from an unnamed caller"; check is_deny_agy "$guard_out"
guard_out=$(jq -nc '{agent_type:"workcell:builder",toolCall:{args:{CommandLine:"gh pr merge 12 --merge"}}}' \
  | (cd "$plain" && "$GUARD" agy) 2>"$TMP/err"); guard_rc=$?
name="agy denies a merge from a named builder"; check is_deny_agy "$guard_out"

# --- eval mode: one file flips the verdicts, and only for the repository that carries it ---------
# The same repository is probed before and after the marker appears, so the marker is the only
# variable; a sibling repository and a -C into one pin that eval mode does not travel.
evalrepo="$TMP/repo-eval"; mkrepo "$evalrepo" main
sibling="$TMP/repo-eval-sibling"; mkrepo "$sibling" main
guard_in "$evalrepo" claude 'git push origin main'
name="push to main is denied before the eval marker exists"; check is_deny_claude "$guard_out"
guard_in "$evalrepo" claude 'gh pr merge 12 --merge'
name="the session may merge before the eval marker exists"; check is_allow "$guard_out"
mkdir -p "$evalrepo/.workcell"
printf '{"mode":"eval","startedAt":"1970-01-01T00:00:00Z","source":"bootstrap-eval"}\n' > "$evalrepo/.workcell/eval-mode.json"
guard_in "$evalrepo" claude 'git push origin main'
name="eval marker allows a push to main"; check is_allow "$guard_out"
guard_in "$evalrepo" claude 'git commit -m x'
name="eval marker allows a commit on main"; check is_allow "$guard_out"
guard_in "$evalrepo/.." claude "git -C $evalrepo commit -m x"
name="eval mode is read from the repository -C names, not the cwd"; check is_allow "$guard_out"
guard_in "$evalrepo" claude 'gh pr merge 12 --merge'
name="eval marker denies the merge the session could otherwise make"; check is_deny_claude "$guard_out"
name="eval deny names eval mode and GitHub"
check sh -c 'printf %s "$1" | grep -qF "eval mode: GitHub is out of scope"' _ "$(reason_of "$guard_out")"
guard_in "$evalrepo" claude 'CARGO_TARGET_DIR=/tmp cargo build'
name="eval marker leaves the RAM-tmpfs rule alone"; check is_deny_claude "$guard_out"
guard_in "$sibling" claude 'git push origin main'
name="the eval marker does not leak to a sibling repository"; check is_deny_claude "$guard_out"
guard_in "$evalrepo" claude "git -C $sibling push origin main"
name="a -C out of the eval repo is judged by the repository it names"; check is_deny_claude "$guard_out"

# --- build-guard fails closed: exit 2 + reason on stderr ----------------------------------------
nojq="$TMP/nojq"; mkdir -p "$nojq"
for t in bash sh awk sed grep cat env printf tr; do
  p=$(command -v "$t" 2>/dev/null) && ln -sfn "$p" "$nojq/$t"
done
out=$(jb 'git status' | PATH="$nojq" "$GUARD" 2>"$TMP/err"); rc=$?
name="guard exits 2 without jq";              check [ "$rc" -eq 2 ]
name="guard prints a reason without jq";      check grep -qi 'jq' "$TMP/err"
out=$(printf 'not json' | "$GUARD" 2>"$TMP/err"); rc=$?
name="guard exits 2 on unparseable payload";  check [ "$rc" -eq 2 ]
name="guard reason on unparseable payload";   check [ -s "$TMP/err" ]
out=$(printf 'not json' | "$GUARD" agy 2>"$TMP/err"); rc=$?
name="guard(agy) exits 2 on unparseable payload"; check [ "$rc" -eq 2 ]
out=$(printf '{"tool_input":{}}' | "$GUARD" 2>"$TMP/err"); rc=$?
name="guard exits 2 when payload has no command"; check [ "$rc" -eq 2 ]
name="guard reason when payload has no command"; check [ -s "$TMP/err" ]
out=$(printf '{"toolCall":{"args":{}}}' | "$GUARD" agy 2>"$TMP/err"); rc=$?
name="guard(agy) exits 2 when payload has no command"; check [ "$rc" -eq 2 ]

# --- build-hooks fails closed when tdd-guard is absent -------------------------------------------
out=$(HOME="$TMP/nohome" "$HOOKS" claude PreToolUse </dev/null 2>"$TMP/err"); rc=$?
name="build-hooks exits 2 without tdd-guard";   check [ "$rc" -eq 2 ]
name="build-hooks names tdd-guard in reason";   check grep -q 'tdd-guard' "$TMP/err"
out=$("$HOOKS" 2>"$TMP/err"); rc=$?
name="build-hooks exits 2 on missing args";     check [ "$rc" -eq 2 ]

# --- build-format: reformats in place; missing file is a silent no-op ---------------------------
if command -v gofmt >/dev/null 2>&1 && printf 'package x\n' | gofmt >/dev/null 2>&1; then
  gf="$TMP/x.go"; printf 'package x\nfunc F(){\nreturn\n}\n' > "$gf"     # under-indented
  j "$gf" | "$FMT" >/dev/null
  name="format tabs-indents go"; check grep -q $'\treturn' "$gf"
else printf 'skip build-format go (gofmt absent)\n'; fi
if command -v ruff >/dev/null 2>&1; then
  pf="$TMP/x.py"; printf 'x=1\n' > "$pf"; j "$pf" | "$FMT" >/dev/null
  name="format spaces python"; check grep -q 'x = 1' "$pf"
else printf 'skip build-format python (ruff absent)\n'; fi
name="format no-ops on missing file"; check sh -c 'echo "$1" | "$2" >/dev/null' _ "$(j "$TMP/nope.py")" "$FMT"

# --- build-lint: emits additionalContext on a violation --------------------------------------------
if command -v shellcheck >/dev/null 2>&1; then
  sl="$TMP/x.sh"; printf '#!/bin/sh\nrm $f\n' > "$sl"                    # SC2086 unquoted
  out=$(j "$sl" | "$LINT")
  name="lint reports shell issue"; check sh -c 'printf "%s" "$1" | jq -e ".hookSpecificOutput.additionalContext" >/dev/null 2>&1' _ "$out"
elif command -v ruff >/dev/null 2>&1; then
  pl="$TMP/y.py"; printf 'import os\n' > "$pl"
  out=$(j "$pl" | "$LINT")
  name="lint reports unused import"; check sh -c 'printf "%s" "$1" | jq -e ".hookSpecificOutput.additionalContext" >/dev/null 2>&1' _ "$out"
else printf 'skip build-lint (no ruff/shellcheck)\n'; fi

# --- portability: POSIX ERE only ------------------------------------------------------------------
name="bootstrap-tools has jq check";           check grep -q "need jq" "$DIR/../bootstrap-tools.sh"
name="build-guard has no \\b word boundaries"; check sh -c '! grep -q "\\\\b" "$1"' _ "$GUARD"
name="build-guard has no grep -P";             check sh -c '! grep -Eq "grep[[:space:]]+(-[[:alnum:]]*P|--perl-regexp)" "$1"' _ "$GUARD"

# --- Antigravity tool-call payload handling in format/lint hooks ---------------------------------
filter='.toolCall.args.TargetFile // .toolCall.args.AbsolutePath // .args.TargetFile // .tool_input.file_path // .tool_input.notebook_path // .tool_response.filePath // empty'
for pair in \
  '{"toolCall":{"args":{"TargetFile":"/path/to/t1"}}}|/path/to/t1' \
  '{"toolCall":{"args":{"AbsolutePath":"/path/to/t2"}}}|/path/to/t2' \
  '{"args":{"TargetFile":"/path/to/t3"}}|/path/to/t3' \
  '{"tool_input":{"file_path":"/path/to/t4"}}|/path/to/t4' \
  '{"tool_input":{"notebook_path":"/path/to/t5"}}|/path/to/t5' \
  '{"tool_response":{"filePath":"/path/to/t6"}}|/path/to/t6'; do
  payload=${pair%%|*}; expected=${pair#*|}
  name="extract $expected"; check [ "$(printf '%s' "$payload" | jq -r "$filter")" = "$expected" ]
done
name="build-format extracts Antigravity payloads"; check grep -Fq 'toolCall.args.TargetFile' "$FMT"
name="build-lint extracts Antigravity payloads";   check grep -Fq 'toolCall.args.TargetFile' "$LINT"

# --- bootstrap-project under the hermetic HOME: writes only to $TMP ------------------------------
pb_tmp="$TMP/pb_test"; git -c init.defaultBranch=main init -q "$pb_tmp"
bash "$DIR/../bootstrap-project.sh" --with-hooks "$pb_tmp" >/dev/null 2>&1
name="bootstrap-project writes the repository-resolved info/exclude"
check sh -c 'cd "$1" && ex=$(git rev-parse --git-path info/exclude) && grep -qxF ".claude/settings.local.json" "$ex"' _ "$pb_tmp"
name="bootstrap-project installs into the hermetic BIN"; check [ -x "$BIN/build-guard" ]

# --- hermeticity: the real ~/.local/bin is untouched --------------------------------------------
after_bin="$(HOME="$REAL_HOME" snapshot_bin)"
name="real ~/.local/bin mtimes and link targets unchanged"; check [ "$before_bin" = "$after_bin" ]


printf '\n%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
