#!/usr/bin/env bash
# Plugin hook manifests and their shipped command paths.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
CLAUDE="$ROOT/plugins/claude"
CODEX="$ROOT/plugins/codex"
AGY="$ROOT/plugins/agy"
HOOK_TEST_HOME=$(mktemp -d)
trap 'rm -rf -- "$HOOK_TEST_HOME"' EXIT
mkdir -p "$HOOK_TEST_HOME/.local/bin"
# Codex commands use the installed path literally. Mirror that layout in a throwaway
# home so this test exercises the manifest command without requiring bootstrap-tools.
for hook in "$ROOT"/scripts/hooks/build-*; do
  ln -s "$hook" "$HOOK_TEST_HOME/.local/bin/${hook##*/}"
done
pass=0; fail=0
ok(){ printf 'ok   %s\n' "$1"; pass=$((pass+1)); }
no(){ printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
check(){ if "$@"; then ok "$name"; else no "$name"; fi; }

for manifest in "$CLAUDE/hooks/hooks.json" "$ROOT/plugins/codex/hooks/hooks.json" "$ROOT/plugins/agy/hooks.json"; do
  name="valid JSON: ${manifest#"$ROOT/"}"; check jq -e 'type == "object"' "$manifest" >/dev/null
  name="commands are non-empty strings: ${manifest#"$ROOT/"}"
  check jq -e '[.. | .command? | select(. != null)] | length > 0 and all(type == "string" and length > 0)' "$manifest" >/dev/null
done

name="Claude declares builder-scoped SubagentStop"
check jq -e '.hooks.SubagentStop[0].matcher == "^workcell:builder$" and (.hooks.SubagentStop[0].hooks[0].command | contains("build-hooks claude SubagentStop"))' "$CLAUDE/hooks/hooks.json" >/dev/null
name="Claude retains the main-agent Stop gate"
check jq -e '.hooks.Stop | length > 0 and ([.[].hooks[].command] | any(contains("build-hooks claude Stop")))' "$CLAUDE/hooks/hooks.json" >/dev/null
name="every Claude command is plugin-relative"
check jq -e '[.. | .command? | select(. != null)] | all(startswith("${CLAUDE_PLUGIN_ROOT}/"))' "$CLAUDE/hooks/hooks.json" >/dev/null
name="no Claude command uses the user-local bin directory"
check sh -c '! grep -q "~/.local/bin" "$1"' _ "$CLAUDE/hooks/hooks.json"

while IFS= read -r command; do
  relative=${command#'${CLAUDE_PLUGIN_ROOT}/'}
  executable=${relative%% *}
  name="Claude command resolves: $executable"; check test -x "$CLAUDE/$executable"
done < <(jq -r '.. | .command? | select(. != null)' "$CLAUDE/hooks/hooks.json")

name="dead Claude frontmatter hook snippet is absent"; check test ! -e "$ROOT/agents/hooks/claude-build.yaml"
name="manifest no longer names the ignored hook snippet"; check sh -c '! grep -q "claude-build" "$1"' _ "$ROOT/agents/agents.json"
name="generated Claude agents have no top-level hooks key"
check sh -c '! grep -l "^hooks:" "$1"/*.md >/dev/null' _ "$ROOT/agents/claude"
name="agent definitions match the generator"; check python3 "$ROOT/scripts/sync-agents.py" --check
name="skill definitions match the generator"; check python3 "$ROOT/scripts/sync-skills.py" --check
name="every harness carries the same contracts"; check python3 "$ROOT/scripts/check-contract-parity.py"

name="Codex uses the documented top-level hook shape"
check jq -e 'has("hooks") and (.hooks | type == "object") and ((keys - ["description", "hooks"]) | length == 0)' "$CODEX/hooks/hooks.json" >/dev/null
name="Codex contains no legacy namespace wrapper"
check sh -c '! grep -q "workcell-guard" "$1"' _ "$CODEX/hooks/hooks.json"
name="Codex matchers use only Codex tool names"
check jq -e '[.hooks.PreToolUse[], .hooks.PostToolUse[] | .matcher | split("|")[]] | all(. == "Bash" or . == "apply_patch" or . == "Edit" or . == "Write")' "$CODEX/hooks/hooks.json" >/dev/null
name="Codex manifest contains no Antigravity tool names"
check sh -c '! grep -Eq "run_command|write_to_file|replace_file_content|multi_replace_file_content" "$1"' _ "$CODEX/hooks/hooks.json"

payload='{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git push origin main"}}'
codex_matcher=$(jq -r '.hooks.PreToolUse[] | select(.matcher | split("|") | index("Bash")) | .matcher' "$CODEX/hooks/hooks.json" | head -n1)
codex_command=$(jq -r '.hooks.PreToolUse[] | select(.matcher | split("|") | index("Bash")) | .hooks[0].command' "$CODEX/hooks/hooks.json" | head -n1)
name="Codex Bash matcher matches a recorded payload"; check sh -c 'printf "%s\n" "$1" | grep -Eq "$2"' _ Bash "$codex_matcher"
name="Codex matched guard command denies a main push"
check sh -c 'printf "%s" "$1" | HOME="$2" bash -c "$3" | jq -e '\''.hookSpecificOutput.permissionDecision == "deny"'\'' >/dev/null' _ "$payload" "$HOOK_TEST_HOME" "$codex_command"

name="Antigravity plugin hook manifest is plugin-owned, not a symlink"
check sh -c 'test -f "$1" && test ! -L "$1"' _ "$AGY/hooks.json"
name="Antigravity manifest documents its session-global scope"
check jq -e '."workcell-guard".description | test("session-global")' "$AGY/hooks.json" >/dev/null
name="Antigravity grouped tool hooks and flat Stop match its schema"
check jq -e '."workcell-guard" as $h | ($h.PreToolUse | all(has("matcher") and (.hooks | type == "array"))) and ($h.PostToolUse | all(has("matcher") and (.hooks | type == "array"))) and ($h.Stop | all(has("type") and has("command") and (has("hooks") | not)))' "$AGY/hooks.json" >/dev/null
while IFS= read -r command; do
  executable=${command%% *}; executable=${executable/#\~/$HOME}
  name="Antigravity command names an installed hook executable: ${command%% *}"
  check sh -c 'case "$1" in "$HOME"/.local/bin/build-*) test -x "$2/${1##*/}" ;; *) false ;; esac' _ "$executable" "$ROOT/scripts/hooks"
done < <(jq -r '.. | .command? | select(. != null)' "$AGY/hooks.json")

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
