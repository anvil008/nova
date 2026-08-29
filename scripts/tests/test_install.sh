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
codex plugin list 2>/dev/null | grep -q '^swarm-coder@swarm-coder-local' \
  && ok "install registers the Codex plugin" || no "install registers the Codex plugin"
claude plugin list 2>/dev/null | grep -q 'swarm-coder@swarm-coder-local' \
  && ok "install registers the Claude plugin" || no "install registers the Claude plugin"
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
# Both marketplaces are rooted at the repository and point at the flattened wrappers.
jq -e '.name == "swarm-coder-local" and (.plugins[0].source == "./plugins/claude")' "$ROOT/.claude-plugin/marketplace.json" >/dev/null 2>&1 || bad_schema=1
jq -e '.name == "swarm-coder-local" and (.plugins[0].source.path == "./plugins/codex")' "$ROOT/.agents/plugins/marketplace.json" >/dev/null 2>&1 || bad_schema=1
[[ $bad_schema -eq 0 ]] && ok "manifests satisfy schema requirements" || no "manifests satisfy schema requirements"

# --- plugin-structure-integrity ------------------------------------------------------------------
bad_links=0
for plugin_dir in "$ROOT/plugins/agy" "$ROOT/plugins/claude" "$ROOT/plugins/codex"; do
  if [[ ! -d "$plugin_dir/skills" ]]; then
    bad_links=1
    echo "Missing skills in $plugin_dir"
  fi
done
if [[ ! -d "$ROOT/plugins/agy/agents" || ! -d "$ROOT/plugins/claude/agents" || ! -d "$ROOT/plugins/codex/agents" ]]; then
  bad_links=1
  echo "Missing agents in plugin directories"
fi
if [[ ! -f "$ROOT/plugins/agy/hooks.json" || ! -d "$ROOT/plugins/agy/rules" ]]; then
  bad_links=1
  echo "Missing hooks.json or rules in agy plugin"
fi
if [[ ! -f "$ROOT/plugins/claude/hooks/hooks.json" || ! -f "$ROOT/plugins/codex/hooks.json" ]]; then
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
codex plugin list 2>/dev/null | grep -q '^swarm-coder@swarm-coder-local' \
  && ok "codex plugin installed from local marketplace" || no "codex plugin installed from local marketplace"
claude plugin list 2>/dev/null | grep -q 'swarm-coder@swarm-coder-local' \
  && ok "claude plugin installed from local marketplace" || no "claude plugin installed from local marketplace"

# --- uninstall-cleans-plugins (integration) ------------------------------------------------------
out=$("$INSTALL" --uninstall 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "uninstall exits zero" || no "uninstall exits zero (rc=$rc): $out"
[[ ! -L "$HOME/.gemini/antigravity-cli/plugins/swarm-coder" ]] \
  && ! codex plugin list 2>/dev/null | grep -q '^swarm-coder@swarm-coder-local' \
  && ! claude plugin list 2>/dev/null | grep -q 'swarm-coder@swarm-coder-local' \
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
codex plugin list 2>/dev/null | grep -q '^swarm-coder@swarm-coder-local' \
  && ok "bootstrap-project registers the Codex plugin" || no "bootstrap-project registers the Codex plugin"
printf "\n%d passed, %d failed\n" "$pass" "$fail"
[[ $fail -eq 0 ]]
