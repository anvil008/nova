#!/usr/bin/env bash
# Tests for the builder aux hooks (build-format / build-lint / build-guard).
# Tool-dependent assertions skip gracefully when the formatter/linter is absent,
# so this stays green in a minimal CI image; the tool-free guard checks always run.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$(dirname "$HERE")"
FMT="$DIR/build-format"; LINT="$DIR/build-lint"; GUARD="$DIR/build-guard"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ printf 'ok   %s\n' "$1"; pass=$((pass+1)); }
no(){ printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
j(){ jq -nc --arg f "$1" '{tool_input:{file_path:$f}}'; }        # Edit/Write payload
jb(){ jq -nc --arg c "$1" '{tool_input:{command:$c}}'; }         # Bash payload
denied(){ jq -e '.hookSpecificOutput.permissionDecision=="deny"' >/dev/null 2>&1; }

# --- build-guard: deny policy violations, allow benign commands (no external tools) ---
jb 'git push origin main'              | "$GUARD" | denied && ok "guard denies git push main"        || no "guard denies git push main"
jb 'git commit -m x main'              | "$GUARD" | denied && ok "guard denies commit into main"      || no "guard denies commit into main"
jb 'CARGO_TARGET_DIR=/tmp/x cargo b'   | "$GUARD" | denied && ok "guard denies cargo target in /tmp"  || no "guard denies cargo target in /tmp"
out=$(jb 'git status'                  | "$GUARD"); [[ -z ${out//[[:space:]]/} ]] && ok "guard allows git status"          || no "guard allows git status"
out=$(jb 'git push origin feat-branch' | "$GUARD"); [[ -z ${out//[[:space:]]/} ]] && ok "guard allows push feature branch" || no "guard allows push feature branch"

# --- build-guard: Antigravity payload/output shape (.toolCall.args.CommandLine -> {decision:deny}) ---
ja(){ jq -nc --arg c "$1" '{toolCall:{name:"run_command",args:{CommandLine:$c}}}'; }
ja 'git push origin main' | "$GUARD" agy | jq -e '.decision=="deny"' >/dev/null 2>&1 && ok "guard(agy) denies push main"     || no "guard(agy) denies push main"
out=$(ja 'cargo test'     | "$GUARD" agy); [[ -z ${out//[[:space:]]/} ]]                 && ok "guard(agy) allows cargo test" || no "guard(agy) allows cargo test"

# --- build-format: reformats in place; missing file is a silent no-op ---
if command -v gofmt >/dev/null 2>&1; then
  gf="$TMP/x.go"; printf 'package x\nfunc F(){\nreturn\n}\n' > "$gf"     # under-indented
  j "$gf" | "$FMT" >/dev/null
  grep -q $'\treturn' "$gf" && ok "format tabs-indents go" || no "format tabs-indents go"
else printf 'skip build-format go (gofmt absent)\n'; fi
if command -v ruff >/dev/null 2>&1; then
  pf="$TMP/x.py"; printf 'x=1\n' > "$pf"; j "$pf" | "$FMT" >/dev/null
  grep -q 'x = 1' "$pf" && ok "format spaces python" || no "format spaces python"
else printf 'skip build-format python (ruff absent)\n'; fi
j "$TMP/nope.py" | "$FMT" >/dev/null && ok "format no-ops on missing file" || no "format no-ops on missing file"

# --- build-lint: emits additionalContext on a violation, silent when clean ---
if command -v shellcheck >/dev/null 2>&1; then
  sl="$TMP/x.sh"; printf '#!/bin/sh\nrm $f\n' > "$sl"                    # SC2086 unquoted
  out=$(j "$sl" | "$LINT"); echo "$out" | jq -e '.hookSpecificOutput.additionalContext' >/dev/null 2>&1 \
    && ok "lint reports shell issue" || no "lint reports shell issue"
elif command -v ruff >/dev/null 2>&1; then
  pl="$TMP/y.py"; printf 'import os\n' > "$pl"
  out=$(j "$pl" | "$LINT"); echo "$out" | jq -e '.hookSpecificOutput.additionalContext' >/dev/null 2>&1 \
    && ok "lint reports unused import" || no "lint reports unused import"
else printf 'skip build-lint (no ruff/shellcheck)\n'; fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
