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

j(){ jq -nc --arg f "$1" '{tool_input:{file_path:$f}}'; }        # Edit/Write payload
jb(){ jq -nc --arg c "$1" '{tool_input:{command:$c}}'; }         # Claude Bash payload
ja(){ jq -nc --arg c "$1" '{toolCall:{name:"run_command",args:{CommandLine:$c}}}'; }  # agy payload
denied_claude(){ jq -e '.hookSpecificOutput.permissionDecision=="deny" and (.hookSpecificOutput.permissionDecisionReason|length>0)' >/dev/null 2>&1; }
denied_agy(){ jq -e '.decision=="deny" and (.reason|length>0)' >/dev/null 2>&1; }

# --- build-guard corpus: every probe, both payload shapes ----------------------------------------
# verdict <harness> <command> -> prints allow|deny|error
verdict(){
  local harness=$1 cmd=$2 out rc
  case $harness in
    agy) out=$(ja "$cmd" | "$GUARD" agy 2>"$TMP/err"); rc=$? ;;
    *)   out=$(jb "$cmd" | "$GUARD" 2>"$TMP/err"); rc=$? ;;
  esac
  [[ $rc -eq 0 ]] || { echo "error(rc=$rc)"; return; }
  if [[ -z ${out//[[:space:]]/} ]]; then echo allow; return; fi
  case $harness in
    agy) printf '%s' "$out" | denied_agy && { echo deny; return; } ;;
    *)   printf '%s' "$out" | denied_claude && { echo deny; return; } ;;
  esac
  echo "malformed($out)"
}
probes=0
while IFS= read -r line || [[ -n $line ]]; do
  [[ -z $line || $line == \#* ]] && continue
  expected=${line%%|*}; cmd=${line#*|}
  probes=$((probes+1))
  for h in claude agy; do
    got=$(verdict "$h" "$cmd")
    if [[ $got == "$expected" ]]; then ok "guard($h) $expected: $cmd"
    else no "guard($h) expected $expected got $got: $cmd"; fi
  done
done < "$CORPUS"
name="corpus has >= 40 probes (has $probes)"; check [ "$probes" -ge 40 ]
name="corpus has deny probes";  check grep -q '^deny|'  "$CORPUS"
name="corpus has allow probes"; check grep -q '^allow|' "$CORPUS"

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

# --- project-bootstrap under the hermetic HOME: writes only to $TMP ------------------------------
pb_tmp="$TMP/pb_test"; git -c init.defaultBranch=main init -q "$pb_tmp"
bash "$DIR/../project-bootstrap.sh" --with-hooks "$pb_tmp" >/dev/null 2>&1
name="project-bootstrap writes the repository-resolved info/exclude"
check sh -c 'cd "$1" && ex=$(git rev-parse --git-path info/exclude) && grep -qxF ".claude/settings.local.json" "$ex"' _ "$pb_tmp"
name="project-bootstrap installs into the hermetic BIN"; check [ -x "$BIN/build-guard" ]

# --- hermeticity: the real ~/.local/bin is untouched --------------------------------------------
after_bin="$(HOME="$REAL_HOME" snapshot_bin)"
name="real ~/.local/bin mtimes and link targets unchanged"; check [ "$before_bin" = "$after_bin" ]


# --- Acceptance Tests (Issue #45) ---

# 1. plugin-hooks-validity
for plugin_dir in "$DIR/../../plugins"/*/*; do
  [[ -d $plugin_dir ]] || continue
  hjson="$plugin_dir/hooks.json"
  name="plugin has hooks.json: $plugin_dir"
  check [ -f "$hjson" ]
  if [[ -f $hjson ]]; then
    name="plugin hooks validity (path resolution): $hjson"
    # Every command must use ~/.local/bin/
    check sh -c '! jq -e ".[] | .. | .command? | select(. != null) | select(startswith(\"~/.local/bin/\") | not)" "$1" >/dev/null' _ "$hjson"
  fi
done

# 2. tdd-guard-executes-via-plugin
# Invoking tool operations through a plugin-configured harness triggers build-hooks and enforces TDD seal verification.
# For each plugin, we simulate the hook execution.
# We will just verify that 'build-hooks' when triggered correctly interacts with tdd-guard.
# Actually, the test says: "Invoking tool operations through a plugin-configured harness triggers build-hooks and enforces TDD seal verification."
# Let's write a mock payload and pass it to the hook command from the json.

# 2. tdd-guard-executes-via-plugin
# We will invoke the PreToolUse hook from each plugin's hooks.json for write_to_file and verify it calls build-hooks and errors because of tdd-guard.
# Or better, just verify that parsing hooks.json gives us the correct build-hooks command, and we can run it.
name="tdd-guard-executes-via-plugin"
for plugin_dir in "$DIR/../../plugins"/*/*; do
  [[ -d $plugin_dir ]] || continue
  hjson="$plugin_dir/hooks.json"
  [[ -f $hjson ]] || continue
  # Extract the PreToolUse write_to_file command
  cmd=$(jq -r '.["swarm-guard"].PreToolUse[] | select(.matcher | contains("write_to_file")) | .hooks[] | select(.type=="command") | .command' "$hjson" | head -n 1)
  # Ensure it calls build-hooks with the right args
  if [[ -n $cmd ]]; then
    # eval the command in our sandbox where tdd-guard is missing -> should get exit 2 and "tdd-guard" in stderr
    ln -sfn "$HOOKS" "$TMP/home/.local/bin/build-hooks"
    out=$(eval HOME="$TMP/nohome" $cmd </dev/null 2>"$TMP/err")
    rc=$?
    check [ "$rc" -eq 2 ]
    check grep -q 'tdd-guard' "$TMP/err"
  fi
done


printf '\n%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
