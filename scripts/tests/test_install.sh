#!/usr/bin/env bash
# Tests for the bootstrap scripts (bootstrap-plugins.sh / bootstrap-project.sh / bootstrap-tools.sh).
# Every case runs against a throwaway HOME under mktemp; the real ~/.claude, ~/.codex,
# ~/.gemini and ~/.local/bin are never read or written.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
INSTALL="$ROOT/scripts/bootstrap-plugins.sh"
BOOTSTRAP="$ROOT/scripts/bootstrap-project.sh"
REAL_HOME=$HOME
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ printf 'ok   %s\n' "$1"; pass=$((pass+1)); }
no(){ printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
# fresh_home NAME -> creates $TMP/NAME with the harness dirs the installers look for, exports HOME
fresh_home(){ HOME="$TMP/$1"; export HOME
  mkdir -p "$HOME/.claude" "$HOME/.codex" "$HOME/.gemini/config" "$HOME/.local/bin"
  [[ $HOME != "$REAL_HOME" ]] || { echo "refusing to test against the real HOME" >&2; exit 99; }; }
# is_link_to DST SRC LABEL -> asserts DST is a symlink pointing exactly at SRC
is_link_to(){ [[ -L $1 && $(readlink "$1") == "$2" ]] && ok "$3" || no "$3"; }
# links_into_root DIR -> prints every symlink under DIR whose literal target is inside $ROOT
links_into_root(){ local l; find "$1" -type l | while read -r l; do
  case "$(readlink "$l")" in "$ROOT"/*) echo "$l";; esac; done; }
# git_repo DIR -> initialised repo with one commit, so worktrees can be added
git_repo(){ mkdir -p "$1" && ( cd "$1" && git init -q && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init ); }
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
# registered CLI LABEL -> asserts CLI lists the plugin, or reports a skip when the CLI is
# absent. A CI runner has neither claude nor codex, and their absence is not a defect.
registered(){ local cli=$1 label=$2
  if ! command -v "$cli" >/dev/null; then printf 'skip %s (no %s CLI)\n' "$label" "$cli"; return 0; fi
  "$cli" plugin list 2>/dev/null | grep -q 'swarm-coder@swarm-coder-local' && ok "$label" || no "$label"; }
not_registered(){ local cli=$1
  command -v "$cli" >/dev/null || return 0
  ! "$cli" plugin list 2>/dev/null | grep -q 'swarm-coder@swarm-coder-local'; }

# --- install-refuses-foreign-target --------------------------------------------------------------
fresh_home foreign
mkdir -p "$HOME/.gemini/config/plugins/swarm-coder"
echo "user's own plugin" > "$HOME/.gemini/config/plugins/swarm-coder/plugin.json"
cp -R "$HOME/.gemini" "$TMP/foreign-before"
out=$("$INSTALL" --install --harness agy 2>&1); rc=$?
[[ $rc -ne 0 ]] && ok "install exits non-zero on foreign targets" || no "install exits non-zero on foreign targets (rc=$rc)"
grep -q "plugins/swarm-coder" <<<"$out" && ok "refusal names foreign target" || no "refusal names foreign target: $out"
grep -q "done\." <<<"$out" && no "refused install must not print done." || ok "refused install does not print done."
[[ ! -L $HOME/.gemini/config/plugins/swarm-coder ]] \
  && cmp -s "$TMP/foreign-before/config/plugins/swarm-coder/plugin.json" "$HOME/.gemini/config/plugins/swarm-coder/plugin.json" \
  && ok "foreign targets left byte-identical" || no "foreign targets left byte-identical"

# --- uninstall-removes-only-owned-links ----------------------------------------------------------
fresh_home owned
mkdir -p "$TMP/elsewhere" "$HOME/.claude/plugins"; echo foreign > "$TMP/elsewhere/foreign-plugin"
out=$("$INSTALL" --install 2>&1); rc=$?
[[ $rc -eq 0 ]] && grep -q "done\." <<<"$out" && ok "install into fresh HOME succeeds" || no "install into fresh HOME succeeds (rc=$rc): $out"
[[ -L $HOME/.gemini/config/plugins/swarm-coder && -L $HOME/.gemini/antigravity-cli/plugins/swarm-coder ]] \
  && ok "install links the Antigravity plugin" || no "install links the Antigravity plugin"
registered codex "install registers the Codex plugin"
registered claude "install registers the Claude plugin"
git_repo "$TMP/owned-proj"
"$BOOTSTRAP" --install "$TMP/owned-proj" >/dev/null 2>&1
ln -sfn "$ROOT/bin/tdd-guard" "$HOME/.local/bin/tdd-guard"; ln -sfn "$ROOT/scripts/hooks/build-hooks" "$HOME/.local/bin/build-hooks"
ln -sfn "$TMP/elsewhere/foreign-plugin" "$HOME/.claude/plugins/foreign-plugin"      # foreign link
out=$("$INSTALL" --uninstall 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "uninstall exits zero" || no "uninstall exits zero (rc=$rc): $out"
left=$(links_into_root "$HOME")
[[ -z $left ]] && ok "uninstall removes every link into ROOT (incl. ~/.local/bin/build-* and tdd-guard)" || no "links into ROOT left behind: $left"
[[ -L $HOME/.claude/plugins/foreign-plugin && $(readlink "$HOME/.claude/plugins/foreign-plugin") == "$TMP/elsewhere/foreign-plugin" ]] \
  && ok "uninstall leaves the foreign plugin link" || no "uninstall leaves the foreign plugin link"
grep -q "foreign-plugin" <<<"$out" && ok "uninstall reports what it left behind" || no "uninstall reports what it left behind: $out"

# --- hooks-are-symlinks-after-bootstrap-project --------------------------------------------------
fresh_home hooks
git_repo "$TMP/hooks-proj"
out=$("$BOOTSTRAP" --with-hooks "$TMP/hooks-proj" 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "bootstrap-project --with-hooks exits zero" || no "bootstrap-project --with-hooks exits zero (rc=$rc): $out"
allsym=1
for h in build-format build-lint build-guard; do
  [[ -L $HOME/.local/bin/$h && $(readlink "$HOME/.local/bin/$h") == "$ROOT/scripts/hooks/$h" ]] || allsym=0
done
[[ $allsym -eq 1 ]] && ok "build-format/lint/guard are symlinks into scripts/hooks" || no "build-format/lint/guard are symlinks into scripts/hooks"
[[ -f $TMP/hooks-proj/.claude/settings.local.json ]] && ok "settings.local.json written" || no "settings.local.json written"
grep -qxF '.claude/settings.local.json' "$TMP/hooks-proj/.git/info/exclude" && ok "exclude written in plain repo" || no "exclude written in plain repo"

# --- no-gnu-only-constructs ----------------------------------------------------------------------
bad=$(grep -nE 'mapfile|find .*-printf|readlink -f|sed -i' "$ROOT"/scripts/*.sh || true)
[[ -z $bad ]] && ok "no GNU-only constructs in scripts/*.sh" || no "GNU-only constructs: $bad"

# --- bash -n syntax check on all scripts ---------------------------------------------------------
bad_syntax=0
for s in "$ROOT"/scripts/*.sh "$ROOT"/scripts/tests/*.sh "$ROOT"/scripts/hooks/build-*; do
  bash -n "$s" || bad_syntax=1
done
[[ $bad_syntax -eq 0 ]] && ok "bash -n passes for every script" || no "bash -n failed on one or more scripts"

# --- installers use set -euo pipefail -----------------------------------------------------------
bad_flags=0
for s in "$INSTALL" "$BOOTSTRAP" "$ROOT/scripts/bootstrap-tools.sh"; do
  grep -q 'set -euo pipefail' "$s" || bad_flags=1
done
[[ $bad_flags -eq 0 ]] && ok "installers use set -euo pipefail" || no "set -euo pipefail missing in one or more scripts"

# --- bootstrap-project has no install -m copy ---------------------------------------------------
grep -q 'install -m' "$BOOTSTRAP" && no "bootstrap-project still contains install -m" || ok "bootstrap-project has no install -m copy"

# --- exclude-written-in-worktree -----------------------------------------------------------------
fresh_home wt
git_repo "$TMP/wt-main"
( cd "$TMP/wt-main" && git worktree add -q "$TMP/wt-tree" -b side )
[[ -f $TMP/wt-tree/.git ]] && ok "worktree has a .git file" || no "worktree has a .git file"
"$BOOTSTRAP" --with-hooks "$TMP/wt-tree" >/dev/null 2>&1
ex=$(cd "$TMP/wt-tree" && git rev-parse --git-path info/exclude)
grep -qxF '.claude/settings.local.json' "$ex" && ok "exclude written to common-dir info/exclude in worktree" || no "exclude written to common-dir info/exclude in worktree ($ex)"
( cd "$TMP/wt-tree" && git status --porcelain | grep -q settings.local ) && no "settings.local.json visible to git in worktree" || ok "settings.local.json invisible to git in worktree"

# --- --force replaces only symlinks, never real files/dirs ---------------------------------------
fresh_home force
mkdir -p "$TMP/elsewhere" "$HOME/.gemini/antigravity-cli/plugins" "$HOME/.gemini/config/plugins/swarm-coder"
echo foreign > "$TMP/elsewhere/foreign-plugin"
ln -sfn "$TMP/elsewhere/foreign-plugin" "$HOME/.gemini/antigravity-cli/plugins/swarm-coder"
echo real > "$HOME/.gemini/config/plugins/swarm-coder/plugin.json"
out=$("$INSTALL" --install --force 2>&1); rc=$?
is_link_to "$HOME/.gemini/antigravity-cli/plugins/swarm-coder" "$ROOT/plugins/agy" "--force replaces a foreign symlink"
[[ $rc -ne 0 && ! -L $HOME/.gemini/config/plugins/swarm-coder && -f $HOME/.gemini/config/plugins/swarm-coder/plugin.json ]] \
  && ok "--force still refuses a real directory" || no "--force still refuses a real directory (rc=$rc): $out"

# --- frontmatter validated before any harness is touched -----------------------------------------
fresh_home fm
BROKEN="$TMP/broken-root"; mkdir -p "$BROKEN/scripts" "$BROKEN/skills"
cp -R "$ROOT/agents" "$BROKEN/agents"; cp -R "$ROOT/skills/jj" "$BROKEN/skills/jj"; cp "$ROOT"/scripts/*.sh "$BROKEN/scripts/"
printf 'no frontmatter here\n' > "$BROKEN/agents/codex/docs.md"
out=$("$BROKEN/scripts/bootstrap-plugins.sh" --install 2>&1); rc=$?
[[ $rc -ne 0 ]] && grep -q "agents/codex/docs.md" <<<"$out" && ok "invalid frontmatter fails and is named" || no "invalid frontmatter fails and is named (rc=$rc): $out"
[[ -z $(find "$HOME/.claude" "$HOME/.codex" "$HOME/.gemini" -type l) ]] && ok "invalid frontmatter: no harness touched" || no "invalid frontmatter: no harness touched"

# --- manifest-schema-validity --------------------------------------------------------------------
bad_json=0
for manifest in "$ROOT"/plugins/agy/plugin.json "$ROOT"/plugins/claude/.claude-plugin/plugin.json \
                "$ROOT"/plugins/codex/.codex-plugin/plugin.json "$ROOT"/.claude-plugin/marketplace.json \
                "$ROOT"/.agents/plugins/marketplace.json; do
  if ! jq . "$manifest" >/dev/null 2>&1; then
    bad_json=1
    echo "Invalid JSON or missing: $manifest"
  fi
done
[[ $bad_json -eq 0 ]] && ok "manifests are valid JSON" || no "manifests are valid JSON"

bad_schema=0
jq -e '.name == "swarm-coder" and .version and .description and .capabilities' "$ROOT/plugins/agy/plugin.json" >/dev/null 2>&1 || bad_schema=1
jq -e '.name == "swarm-coder" and .version and .description' "$ROOT/plugins/claude/.claude-plugin/plugin.json" >/dev/null 2>&1 || bad_schema=1
jq -e '.name == "swarm-coder" and .version and .description' "$ROOT/plugins/codex/.codex-plugin/plugin.json" >/dev/null 2>&1 || bad_schema=1
# Claude's marketplace is rooted at the repository and follows the wrapper's links.
jq -e '.name == "swarm-coder-local" and (.plugins[0].source == "./plugins/claude")' "$ROOT/.claude-plugin/marketplace.json" >/dev/null 2>&1 || bad_schema=1
# Codex's is generated into dist/, because Codex copies a plugin and drops escaping symlinks.
python3 "$ROOT/scripts/build-codex-plugin.py" >/dev/null 2>&1 || bad_schema=1
jq -e '.name == "swarm-coder-local" and (.plugins[0].source.path == "./plugins/swarm-coder")' "$ROOT/dist/codex/.agents/plugins/marketplace.json" >/dev/null 2>&1 || bad_schema=1
# The staged manifest must carry what Codex validation actually requires.
jq -e '.author.name and .interface.displayName and .interface.defaultPrompt and .skills == "./skills/" and (has("hooks") | not)' \
  "$ROOT/dist/codex/plugins/swarm-coder/.codex-plugin/plugin.json" >/dev/null 2>&1 || bad_schema=1
[[ $bad_schema -eq 0 ]] && ok "manifests satisfy schema requirements" || no "manifests satisfy schema requirements"

# --- plugin-structure-integrity ------------------------------------------------------------------
bad_links=0
for plugin_dir in "$ROOT/plugins/agy" "$ROOT/plugins/claude"; do
  if [[ ! -d "$plugin_dir/skills" ]]; then
    bad_links=1
    echo "Missing skills in $plugin_dir"
  fi
done
if [[ ! -d "$ROOT/plugins/agy/agents" || ! -d "$ROOT/plugins/claude/agents" ]]; then
  bad_links=1
  echo "Missing agents in plugin directories"
fi
if [[ ! -f "$ROOT/plugins/agy/hooks.json" || ! -d "$ROOT/plugins/agy/rules" ]]; then
  bad_links=1
  echo "Missing hooks.json or rules in agy plugin"
fi
if [[ ! -f "$ROOT/plugins/claude/hooks/hooks.json" || ! -f "$ROOT/plugins/codex/hooks/hooks.json" ]]; then
  bad_links=1
  echo "Missing hooks.json in the Claude or Codex plugin"
fi
if find "$ROOT/plugins" -type l ! -exec test -e {} \; -print | grep -q .; then
  bad_links=1
  echo "Broken symlinks found in plugins/"
fi
[[ $bad_links -eq 0 ]] && ok "plugin structure integrity" || no "plugin structure integrity"

# --- agy-skill-links-are-derived-not-listed -------------------------------------------------------
# The Antigravity wrapper carries one link per *shared* skill: every skills/ directory
# except those owned by one of its agents (ADR 0003). Asserted as the rule, so adding a
# skill can never silently leave the wrapper behind.
expected=$(for d in "$ROOT"/skills/*/; do
  n=$(basename "$d")
  find "$ROOT/agents/agy" -mindepth 3 -maxdepth 3 -name "$n" | grep -q . || echo "$n"
done | sort)
actual=$(ls "$ROOT/plugins/agy/skills" | sort)
[[ $expected == "$actual" ]] && ok "agy skill links are exactly the non-agent-owned skills" \
  || no "agy skill links drifted from skills/ (expected: $(echo "$expected" | tr '\n' ' ')| got: $(echo "$actual" | tr '\n' ' '))"

# --- install-all-plugins (integration) -----------------------------------------------------------
fresh_home plugins
mkdir -p "$HOME/.gemini/antigravity-cli"
out=$("$INSTALL" --install 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "install exits zero" || no "install exits zero (rc=$rc): $out"
is_link_to "$HOME/.gemini/antigravity-cli/plugins/swarm-coder" "$ROOT/plugins/agy" "agy plugin linked"
registered codex "codex plugin installed from local marketplace"
registered claude "claude plugin installed from local marketplace"

# --- uninstall-cleans-plugins (integration) ------------------------------------------------------
out=$("$INSTALL" --uninstall 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "uninstall exits zero" || no "uninstall exits zero (rc=$rc): $out"
[[ ! -L "$HOME/.gemini/antigravity-cli/plugins/swarm-coder" ]] \
  && not_registered codex && not_registered claude \
  && ok "uninstall removes all plugins" || no "uninstall removes all plugins"

# --- refuses-foreign-plugin (unit) ---------------------------------------------------------------
fresh_home foreign_plugin
mkdir -p "$HOME/.gemini/config/plugins/swarm-coder"
echo "foreign" > "$HOME/.gemini/config/plugins/swarm-coder/foreign.txt"
out=$("$INSTALL" --install 2>&1); rc=$?
[[ $rc -ne 0 ]] && ok "install refuses foreign plugin directory" || no "install refuses foreign plugin directory (rc=$rc): $out"
[[ -f "$HOME/.gemini/config/plugins/swarm-coder/foreign.txt" ]] && ok "foreign plugin untouched" || no "foreign plugin untouched"


# --- project-bootstrap-installs-local-plugins (integration) --------------------------------------
fresh_home pb_plugins
git_repo "$TMP/pb-plugins-proj"
out=$("$BOOTSTRAP" --install "$TMP/pb-plugins-proj" 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "bootstrap-project --install exits zero" || no "bootstrap-project --install exits zero (rc=$rc): $out"

ex=$(cd "$TMP/pb-plugins-proj" && git rev-parse --git-path info/exclude)
is_link_to "$TMP/pb-plugins-proj/.agents/plugins/swarm-coder" "$ROOT/plugins/agy" \
  "bootstrap-project agy workspace plugin linked"
grep -qxF ".agents/plugins" "$TMP/pb-plugins-proj/$ex" && ok "exclude .agents/plugins written" || no "exclude .agents/plugins written"
registered codex "bootstrap-project registers the Codex plugin"
# --- codex-model-profiles ------------------------------------------------------------------------
# Codex reads no per-agent model surface, so agents/models.json only takes effect there
# through a profile. These are machine state, so ownership rules apply exactly as they do
# to links: we write ours, refuse to touch anyone else's, and remove only our own.
fresh_home codex_profiles
"$INSTALL" --install >/dev/null 2>&1 || true

[[ -f "$HOME/.codex/swarm-builder.config.toml" ]] \
  && ok "install writes a codex profile per agent" \
  || no "install writes a codex profile per agent"
grep -q 'model_reasoning_effort = "high"' "$HOME/.codex/swarm-builder.config.toml" 2>/dev/null \
  && ok "codex profile carries the manifest effort" \
  || no "codex profile carries the manifest effort"
grep -q 'model_reasoning_effort = "low"' "$HOME/.codex/swarm-research.config.toml" 2>/dev/null \
  && ok "codex profile is per-agent, not one blanket value" \
  || no "codex profile is per-agent, not one blanket value"

# A profile we did not write is never overwritten, even under our own name prefix.
printf 'model = "mine"\n' > "$HOME/.codex/swarm-builder.config.toml"
out=$(python3 "$ROOT/scripts/sync-agent-models.py" --codex-profiles 2>&1); rc=$?
[[ $rc -ne 0 ]] && grep -q "refusing to overwrite" <<<"$out" \
  && ok "foreign codex profile refused by name" \
  || no "foreign codex profile refused by name (rc=$rc): $out"
grep -q 'model = "mine"' "$HOME/.codex/swarm-builder.config.toml" \
  && ok "foreign codex profile untouched" || no "foreign codex profile untouched"

# Uninstall sweeps ours and leaves theirs, including the foreign one just written.
"$INSTALL" --uninstall >/dev/null 2>&1 || true
[[ -f "$HOME/.codex/swarm-builder.config.toml" ]] \
  && ok "uninstall leaves a foreign codex profile" || no "uninstall leaves a foreign codex profile"
[[ ! -f "$HOME/.codex/swarm-research.config.toml" ]] \
  && ok "uninstall removes our codex profiles" || no "uninstall removes our codex profiles"

# --- codex-staged-tree ---------------------------------------------------------------------------
# Codex materializes a copy of a plugin and silently drops any symlink pointing
# outside the plugin root, so the wrapper's links delivered nothing. The staged
# tree is what makes skills and agents actually reach the model.
python3 "$ROOT/scripts/build-codex-plugin.py" >/dev/null 2>&1
staged="$ROOT/dist/codex/plugins/swarm-coder"

[[ -f "$staged/hooks/hooks.json" ]] \
  && ok "codex hooks at the auto-discovered path" || no "codex hooks at the auto-discovered path"

skill_count=$(find "$staged/skills" -maxdepth 2 -name SKILL.md | wc -l)
repo_skills=$(find "$ROOT/skills" -maxdepth 2 -name SKILL.md | wc -l)
codex_agents=$(find "$ROOT/agents/codex" -maxdepth 1 -name '*.md' | wc -l)
[[ $skill_count -eq $((repo_skills + codex_agents)) ]] \
  && ok "every skill and agent is staged ($skill_count)" \
  || no "every skill and agent is staged (got $skill_count, want $((repo_skills + codex_agents)))"

[[ -f "$staged/skills/agent-builder/agents/openai.yaml" ]] \
  && ok "agents ship as skills with openai.yaml" || no "agents ship as skills with openai.yaml"

if find "$staged" -type l | grep -q .; then
  no "staged tree is symlink-free"
else
  ok "staged tree is symlink-free"
fi

# --- plugin-cache-refresh (T-PLUGIN-REFRESH / #76) ------------------------------------------------
# A marketplace harness refreshes a cached plugin only when plugin.json's version changes,
# so a plain re-install can leave yesterday's agents/ tree installed against today's hooks.
# The install must therefore remove the plugin before adding it, every run. The harness CLIs
# are stubbed first on PATH so the exact call sequence is observable without a real CLI and
# without ever touching the real ~/.claude or ~/.codex.
#
# stub_cli NAME DIR LOG -> writes an executable NAME into DIR that appends its argv to LOG
# (one call per line) and exits 0. Put DIR first on PATH for the run under test.
stub_cli(){ local name=$1 dir=$2 log=$3
  mkdir -p "$dir"; : > "$log"
  { printf '#!/usr/bin/env bash\n'
    printf 'printf "%%s\\n" "$*" >> %q\n' "$log"
    printf 'exit 0\n'; } > "$dir/$name"
  chmod +x "$dir/$name"; }
# call_line LOG TEXT -> 1-based line number of the first logged call containing TEXT ("" if none)
call_line(){ grep -n -F -- "$2" "$1" 2>/dev/null | head -1 | cut -d: -f1; }

# --- install-removes-the-cached-plugin-before-adding-it -------------------------------------------
fresh_home refresh_claude
CLAUDE_STUBS="$TMP/stubs-claude"; CLAUDE_LOG="$TMP/claude-calls.log"
stub_cli claude "$CLAUDE_STUBS" "$CLAUDE_LOG"
out=$(PATH="$CLAUDE_STUBS:$PATH" "$INSTALL" --install --harness claude 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "claude install with a stubbed CLI exits zero" \
  || no "claude install with a stubbed CLI exits zero (rc=$rc): $out"
add_at=$(call_line "$CLAUDE_LOG" "plugin install swarm-coder@swarm-coder-local")
rm_at=$(call_line "$CLAUDE_LOG" "plugin uninstall swarm-coder@swarm-coder-local")
[[ -n $rm_at ]] || rm_at=$(call_line "$CLAUDE_LOG" "plugin marketplace remove swarm-coder-local")
[[ -n $add_at && -n $rm_at && $rm_at -lt $add_at ]] \
  && ok "claude install removes the cached plugin before adding it" \
  || no "claude install removes the cached plugin before adding it (remove=${rm_at:-none} install=${add_at:-none}) calls: $(tr '\n' ';' < "$CLAUDE_LOG")"

# --- codex-install-refreshes-too ------------------------------------------------------------------
fresh_home refresh_codex
CODEX_STUBS="$TMP/stubs-codex"; CODEX_LOG="$TMP/codex-calls.log"
stub_cli codex "$CODEX_STUBS" "$CODEX_LOG"
out=$(PATH="$CODEX_STUBS:$PATH" "$INSTALL" --install --harness codex 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "codex install with a stubbed CLI exits zero" \
  || no "codex install with a stubbed CLI exits zero (rc=$rc): $out"
cx_add_at=$(call_line "$CODEX_LOG" "plugin add swarm-coder@swarm-coder-local")
cx_rm_at=$(call_line "$CODEX_LOG" "plugin remove swarm-coder@swarm-coder-local")
[[ -n $cx_add_at && -n $cx_rm_at && $cx_rm_at -lt $cx_add_at ]] \
  && ok "codex install removes the cached plugin before adding it" \
  || no "codex install removes the cached plugin before adding it (remove=${cx_rm_at:-none} add=${cx_add_at:-none}) calls: $(tr '\n' ';' < "$CODEX_LOG")"

# --- reinstall-stays-idempotent -------------------------------------------------------------------
# Forcing a refresh must not cost idempotence or the exit-status semantics: two runs in a row
# both succeed and both announce "done.", and a foreign target is still refused non-zero and
# still never announces "done.".
fresh_home reinstall
BOTH_STUBS="$TMP/stubs-both"; BOTH_LOG="$TMP/both-calls.log"
stub_cli claude "$BOTH_STUBS" "$BOTH_LOG"; stub_cli codex "$BOTH_STUBS" "$BOTH_LOG"
out1=$(PATH="$BOTH_STUBS:$PATH" "$INSTALL" --install 2>&1); rc1=$?
out2=$(PATH="$BOTH_STUBS:$PATH" "$INSTALL" --install 2>&1); rc2=$?
[[ $rc1 -eq 0 ]] && grep -q "done\." <<<"$out1" && [[ $rc2 -eq 0 ]] && grep -q "done\." <<<"$out2" \
  && ok "two consecutive installs both exit zero and print done." \
  || no "two consecutive installs both exit zero and print done. (rc1=$rc1 rc2=$rc2): $out1 || $out2"
# A HOME of its own: the run above already linked ~/.gemini/.../swarm-coder into ROOT, and
# writing a "foreign" file through that link would land in the repository.
fresh_home reinstall_foreign
mkdir -p "$HOME/.gemini/config/plugins/swarm-coder"
echo "user's own plugin" > "$HOME/.gemini/config/plugins/swarm-coder/plugin.json"
out3=$(PATH="$BOTH_STUBS:$PATH" "$INSTALL" --install --harness agy 2>&1); rc3=$?
[[ $rc3 -ne 0 ]] && ! grep -q "done\." <<<"$out3" \
  && ok "refresh keeps the foreign-target refusal non-zero and silent about done." \
  || no "refresh keeps the foreign-target refusal non-zero and silent about done. (rc=$rc3): $out3"

# --- claude-plugin-version-is-past-the-stale-cache ------------------------------------------------
# 0.1.0 is the version pinned by the stale cache in the wild; leaving it there means existing
# installs never refresh on a version bump.
claude_ver=$(jq -r .version "$ROOT/plugins/claude/.claude-plugin/plugin.json" 2>/dev/null)
[[ $claude_ver =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] && [[ $claude_ver != "0.1.0" ]] \
  && ok "claude plugin.json version is semver and past the stale 0.1.0 cache" \
  || no "claude plugin.json version is semver and past the stale 0.1.0 cache (got '$claude_ver')"

printf "\n%d passed, %d failed\n" "$pass" "$fail"
[[ $fail -eq 0 ]]
