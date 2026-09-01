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
  CODEX_HOME="$HOME/.codex"; export CODEX_HOME
  CLAUDE_CONFIG_DIR="$HOME/.claude"; export CLAUDE_CONFIG_DIR
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
  "$cli" plugin list 2>/dev/null | grep -q 'workcell@workcell' && ok "$label" || no "$label"; }
not_registered(){ local cli=$1
  command -v "$cli" >/dev/null || return 0
  ! "$cli" plugin list 2>/dev/null | grep -q 'workcell@workcell'; }

# --- install-refuses-foreign-target --------------------------------------------------------------
fresh_home foreign
mkdir -p "$HOME/.gemini/config/plugins/workcell"
echo "user's own plugin" > "$HOME/.gemini/config/plugins/workcell/plugin.json"
cp -R "$HOME/.gemini" "$TMP/foreign-before"
out=$("$INSTALL" --install --harness agy 2>&1); rc=$?
[[ $rc -ne 0 ]] && ok "install exits non-zero on foreign targets" || no "install exits non-zero on foreign targets (rc=$rc)"
grep -q "plugins/workcell" <<<"$out" && ok "refusal names foreign target" || no "refusal names foreign target: $out"
grep -q "done\." <<<"$out" && no "refused install must not print done." || ok "refused install does not print done."
[[ ! -L $HOME/.gemini/config/plugins/workcell ]] \
  && cmp -s "$TMP/foreign-before/config/plugins/workcell/plugin.json" "$HOME/.gemini/config/plugins/workcell/plugin.json" \
  && ok "foreign targets left byte-identical" || no "foreign targets left byte-identical"

# --- uninstall-removes-only-owned-links ----------------------------------------------------------
fresh_home owned
mkdir -p "$TMP/elsewhere" "$HOME/.claude/plugins"; echo foreign > "$TMP/elsewhere/foreign-plugin"
out=$("$INSTALL" --install 2>&1); rc=$?
[[ $rc -eq 0 ]] && grep -q "done\." <<<"$out" && ok "install into fresh HOME succeeds" || no "install into fresh HOME succeeds (rc=$rc): $out"
[[ -L $HOME/.gemini/config/plugins/workcell && -L $HOME/.gemini/antigravity-cli/plugins/workcell ]] \
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

# --- hooks-are-real-copies-after-bootstrap-project (#130) ----------------------------------------
# These three used to be symlinks into scripts/hooks/, so every gate call resolved through this
# working tree. They are now owned copies: real, executable files, byte-identical to their
# sources, and nothing under ~/.local/bin points back into $ROOT.
fresh_home hooks
git_repo "$TMP/hooks-proj"
out=$("$BOOTSTRAP" --with-hooks "$TMP/hooks-proj" 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "bootstrap-project --with-hooks exits zero" || no "bootstrap-project --with-hooks exits zero (rc=$rc): $out"
allcopies=1; copybad=
for h in build-format build-lint build-guard; do
  d="$HOME/.local/bin/$h"
  { [[ -f $d && -x $d && ! -L $d ]] && cmp -s "$ROOT/scripts/hooks/$h" "$d"; } || copybad="$copybad $h"
done
[[ -z $copybad ]] || allcopies=0
[[ $allcopies -eq 1 ]] && ok "build-format/lint/guard are real copies of scripts/hooks/, not symlinks" \
  || no "build-format/lint/guard are real copies of scripts/hooks/, not symlinks (wrong:$copybad)"
gate_links=$(links_into_root "$HOME/.local/bin")
[[ -z $gate_links ]] && ok "bootstrap-project leaves no gate link into ROOT" \
  || no "bootstrap-project leaves gate links into ROOT: $gate_links"
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
mkdir -p "$TMP/elsewhere" "$HOME/.gemini/antigravity-cli/plugins" "$HOME/.gemini/config/plugins/workcell"
echo foreign > "$TMP/elsewhere/foreign-plugin"
ln -sfn "$TMP/elsewhere/foreign-plugin" "$HOME/.gemini/antigravity-cli/plugins/workcell"
echo real > "$HOME/.gemini/config/plugins/workcell/plugin.json"
out=$("$INSTALL" --install --force 2>&1); rc=$?
is_link_to "$HOME/.gemini/antigravity-cli/plugins/workcell" "$ROOT/plugins/agy" "--force replaces a foreign symlink"
[[ $rc -ne 0 && ! -L $HOME/.gemini/config/plugins/workcell && -f $HOME/.gemini/config/plugins/workcell/plugin.json ]] \
  && ok "--force still refuses a real directory" || no "--force still refuses a real directory (rc=$rc): $out"

# --- frontmatter validated before any harness is touched -----------------------------------------
fresh_home fm
BROKEN="$TMP/broken-root"; mkdir -p "$BROKEN/scripts" "$BROKEN/skills"
cp -R "$ROOT/agents" "$BROKEN/agents"; cp -R "$ROOT/skills/jj" "$BROKEN/skills/jj"; cp "$ROOT"/scripts/*.sh "$BROKEN/scripts/"
printf 'no frontmatter here\n' > "$BROKEN/agents/codex/documenter.md"
out=$("$BROKEN/scripts/bootstrap-plugins.sh" --install 2>&1); rc=$?
[[ $rc -ne 0 ]] && grep -q "agents/codex/documenter.md" <<<"$out" && ok "invalid frontmatter fails and is named" || no "invalid frontmatter fails and is named (rc=$rc): $out"
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
jq -e '.name == "workcell" and .version and .description and .capabilities' "$ROOT/plugins/agy/plugin.json" >/dev/null 2>&1 || bad_schema=1
jq -e '.name == "workcell" and .version and .description' "$ROOT/plugins/claude/.claude-plugin/plugin.json" >/dev/null 2>&1 || bad_schema=1
jq -e '.name == "workcell" and .version and .description' "$ROOT/plugins/codex/.codex-plugin/plugin.json" >/dev/null 2>&1 || bad_schema=1
# Claude's marketplace is rooted at the repository and follows the wrapper's links.
jq -e '.name == "workcell" and (.plugins[0].source == "./plugins/claude")' "$ROOT/.claude-plugin/marketplace.json" >/dev/null 2>&1 || bad_schema=1
# Codex's is generated into dist/, because Codex copies a plugin and drops escaping symlinks.
python3 "$ROOT/scripts/build-codex-plugin.py" >/dev/null 2>&1 || bad_schema=1
jq -e '.name == "workcell" and (.plugins[0].source.path == "./plugins/workcell")' "$ROOT/dist/codex/.agents/plugins/marketplace.json" >/dev/null 2>&1 || bad_schema=1
# The staged manifest must carry what Codex validation actually requires.
jq -e '.author.name and .interface.displayName and .interface.defaultPrompt and .skills == "./skills/" and (has("hooks") | not)' \
  "$ROOT/dist/codex/plugins/workcell/.codex-plugin/plugin.json" >/dev/null 2>&1 || bad_schema=1
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
is_link_to "$HOME/.gemini/antigravity-cli/plugins/workcell" "$ROOT/plugins/agy" "agy plugin linked"
registered codex "codex plugin installed from local marketplace"
registered claude "claude plugin installed from local marketplace"

# --- uninstall-cleans-plugins (integration) ------------------------------------------------------
out=$("$INSTALL" --uninstall 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "uninstall exits zero" || no "uninstall exits zero (rc=$rc): $out"
[[ ! -L "$HOME/.gemini/antigravity-cli/plugins/workcell" ]] \
  && not_registered codex && not_registered claude \
  && ok "uninstall removes all plugins" || no "uninstall removes all plugins"

# --- refuses-foreign-plugin (unit) ---------------------------------------------------------------
fresh_home foreign_plugin
mkdir -p "$HOME/.gemini/config/plugins/workcell"
echo "foreign" > "$HOME/.gemini/config/plugins/workcell/foreign.txt"
out=$("$INSTALL" --install 2>&1); rc=$?
[[ $rc -ne 0 ]] && ok "install refuses foreign plugin directory" || no "install refuses foreign plugin directory (rc=$rc): $out"
[[ -f "$HOME/.gemini/config/plugins/workcell/foreign.txt" ]] && ok "foreign plugin untouched" || no "foreign plugin untouched"


# --- project-bootstrap-installs-local-plugins (integration) --------------------------------------
fresh_home pb_plugins
git_repo "$TMP/pb-plugins-proj"
out=$("$BOOTSTRAP" --install "$TMP/pb-plugins-proj" 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "bootstrap-project --install exits zero" || no "bootstrap-project --install exits zero (rc=$rc): $out"

ex=$(cd "$TMP/pb-plugins-proj" && git rev-parse --git-path info/exclude)
is_link_to "$TMP/pb-plugins-proj/.agents/plugins/workcell" "$ROOT/plugins/agy" \
  "bootstrap-project agy workspace plugin linked"
grep -qxF ".agents/plugins" "$TMP/pb-plugins-proj/$ex" && ok "exclude .agents/plugins written" || no "exclude .agents/plugins written"
registered codex "bootstrap-project registers the Codex plugin"
# --- codex-model-profiles ------------------------------------------------------------------------
# Codex reads no per-agent model surface, so agents/models.json only takes effect there
# through a profile. These are machine state, so ownership rules apply exactly as they do
# to links: we write ours, refuse to touch anyone else's, and remove only our own.
fresh_home codex_profiles
"$INSTALL" --install >/dev/null 2>&1 || true

[[ -f "$HOME/.codex/workcell-builder.config.toml" ]] \
  && ok "install writes a codex profile per agent" \
  || no "install writes a codex profile per agent"
grep -q 'model_reasoning_effort = "high"' "$HOME/.codex/workcell-builder.config.toml" 2>/dev/null \
  && ok "codex profile carries the manifest effort" \
  || no "codex profile carries the manifest effort"
grep -q 'model_reasoning_effort = "low"' "$HOME/.codex/workcell-researcher.config.toml" 2>/dev/null \
  && ok "codex profile is per-agent, not one blanket value" \
  || no "codex profile is per-agent, not one blanket value"

# A profile we did not write is never overwritten, even under our own name prefix.
printf 'model = "mine"\n' > "$HOME/.codex/workcell-builder.config.toml"
out=$(python3 "$ROOT/scripts/sync-agent-models.py" --codex-profiles 2>&1); rc=$?
[[ $rc -ne 0 ]] && grep -q "refusing to overwrite" <<<"$out" \
  && ok "foreign codex profile refused by name" \
  || no "foreign codex profile refused by name (rc=$rc): $out"
grep -q 'model = "mine"' "$HOME/.codex/workcell-builder.config.toml" \
  && ok "foreign codex profile untouched" || no "foreign codex profile untouched"

# Uninstall sweeps ours and leaves theirs, including the foreign one just written.
"$INSTALL" --uninstall >/dev/null 2>&1 || true
[[ -f "$HOME/.codex/workcell-builder.config.toml" ]] \
  && ok "uninstall leaves a foreign codex profile" || no "uninstall leaves a foreign codex profile"
[[ ! -f "$HOME/.codex/workcell-researcher.config.toml" ]] \
  && ok "uninstall removes our codex profiles" || no "uninstall removes our codex profiles"

# --- codex-staged-tree ---------------------------------------------------------------------------
# Codex materializes a copy of a plugin and silently drops any symlink pointing
# outside the plugin root, so the wrapper's links delivered nothing. The staged
# tree is what makes skills and agents actually reach the model.
python3 "$ROOT/scripts/build-codex-plugin.py" >/dev/null 2>&1
staged="$ROOT/dist/codex/plugins/workcell"

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

# --- plugin-cache-refresh (T-PLUGIN-REFRESH / #76) ----------------------------------------------
stub_cli(){ local name=$1 dir=$2 log=$3
  mkdir -p "$dir"; : > "$log"
  { printf '#!/usr/bin/env bash\n'; printf 'printf "%%s\\n" "$*" >> %q\n' "$log"; } > "$dir/$name"
  chmod +x "$dir/$name"
}

# --- codex-hook-trust-instructions ---------------------------------------------------------------
fresh_home codex_hook_trust
mkdir -p "$TMP/stub-bin"
printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/stub-bin/codex"
chmod +x "$TMP/stub-bin/codex"
out=$(PATH="$TMP/stub-bin:$PATH" "$INSTALL" --install --harness codex 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "Codex-only install succeeds with a stub CLI" || no "Codex-only install failed (rc=$rc): $out"
grep -q '/hooks' <<<"$out" && grep -q -- '--dangerously-bypass-hook-trust' <<<"$out" \
  && ok "Codex install prints both hook trust choices" || no "Codex hook trust instructions missing: $out"
sed -n '1,30p' "$INSTALL" | grep -q '/hooks' && sed -n '1,30p' "$INSTALL" | grep -q -- '--dangerously-bypass-hook-trust' \
  && ok "installer header documents both hook trust choices" || no "installer header lacks hook trust instructions"
call_line(){ grep -n -F -- "$2" "$1" 2>/dev/null | head -1 | cut -d: -f1; }

for harness in claude codex; do
  fresh_home "refresh_$harness"
  stubs="$TMP/stubs-$harness"; log="$TMP/$harness-calls.log"
  stub_cli "$harness" "$stubs" "$log"
  out=$(PATH="$stubs:$PATH" "$INSTALL" --install --harness "$harness" 2>&1); rc=$?
  [[ $rc -eq 0 ]] || no "$harness refresh install exits zero (rc=$rc): $out"
  if [[ $harness == claude ]]; then add=install; del=uninstall; else add=add; del=remove; fi
  add_at=$(call_line "$log" "plugin $add workcell@workcell")
  del_at=$(call_line "$log" "plugin $del workcell@workcell")
  [[ -n $add_at && -n $del_at && $del_at -lt $add_at ]] \
    && ok "$harness removes its cached plugin before adding it" \
    || no "$harness cache refresh order (remove=${del_at:-none} add=${add_at:-none})"
done

# --- grok-staged-install -------------------------------------------------------------------------
fresh_home grok_install
mkdir -p "$HOME/.grok"
stubs="$TMP/stubs-grok"; log="$TMP/grok-calls.log"
stub_cli grok "$stubs" "$log"
out=$(PATH="$stubs:$PATH" "$INSTALL" --install --harness grok 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "grok-only install exits zero" || no "grok-only install failed (rc=$rc): $out"
[[ -f $ROOT/dist/grok/.grok-plugin/marketplace.json ]] && ok "grok marketplace staged" || no "grok staged marketplace missing"
[[ -f $ROOT/dist/grok/plugins/workcell/agents/builder.md && -f $ROOT/dist/grok/plugins/workcell/skills/plan/SKILL.md ]] \
  && ok "grok staged agents and skills are real files" || no "grok staged content missing"
find "$ROOT/dist/grok" -type l | grep -q . && no "grok staged tree contains symlinks" || ok "grok staged tree is symlink-free"
del_at=$(call_line "$log" "plugin uninstall workcell")
add_at=$(call_line "$log" "plugin install workcell --trust")
[[ -n $add_at && -n $del_at && $del_at -lt $add_at ]] \
  && ok "grok removes its cached plugin before adding it" \
  || no "grok cache refresh order (remove=${del_at:-none} add=${add_at:-none})"

# A project-local reinstall also retires marketplace registrations from before
# the Workcell rename, so the old and new plugin identities cannot coexist.
fresh_home project_rename
git_repo "$TMP/project-rename-repo"
for harness in claude codex; do
  stubs="$TMP/project-stubs-$harness"; log="$TMP/project-$harness-calls.log"
  stub_cli "$harness" "$stubs" "$log"
  out=$(PATH="$stubs:$PATH" "$BOOTSTRAP" --install "$TMP/project-rename-repo" 2>&1); rc=$?
  [[ $rc -eq 0 ]] || no "project-local $harness migration exits zero (rc=$rc): $out"
  if [[ $harness == claude ]]; then del=uninstall; else del=remove; fi
  call_line "$log" "plugin $del swarm-coder@swarm-coder-local" >/dev/null \
    && call_line "$log" "plugin marketplace remove swarm-coder-local" >/dev/null \
    && ok "project-local $harness install retires the legacy registration" \
    || no "project-local $harness install retires the legacy registration"
done

claude_ver=$(jq -r .version "$ROOT/plugins/claude/.claude-plugin/plugin.json" 2>/dev/null)
[[ $claude_ver =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && $claude_ver != 0.1.0 ]] \
  && ok "claude plugin version is past the stale 0.1.0 cache" \
  || no "claude plugin version is past the stale 0.1.0 cache (got '$claude_ver')"

# --- copy ownership: install_owned / uninstall_owned / receipts (#129) ---------------------------
# The copy-side equivalent of the link helpers, with the same three guarantees: install only
# over absent-or-ours, refuse a foreign destination by name with a non-zero return, and remove
# on uninstall only what we installed while reporting what was left behind. Every case runs
# against a throwaway HOME, so the receipts under $HOME/.local/state are hermetic too.
# shellcheck source=../lib.sh
. "$ROOT/scripts/lib.sh"
unset WORKCELL_STATE WORKCELL_SHARE
# receipts_for DST -> every receipt file under the current state dir that names DST
receipts_for(){ local r; r="$(workcell_state_dir)/receipts"; [[ -n $r && -d $r ]] || return 0
  grep -rlF -- "$1" "$r" 2>/dev/null || true; }
# tree_list DIR -> the sorted relative path of every file under DIR, minus our own stamp
tree_list(){ [[ -d $1 ]] || return 0
  ( cd "$1" && find . -type f ! -name .workcell-stamp.json | sort ); }
CSRC="$TMP/copy-src"; mkdir -p "$CSRC"
printf '#!/usr/bin/env bash\necho workcell\n' > "$CSRC/tool.sh"; chmod 0644 "$CSRC/tool.sh"
CTREE="$TMP/copy-tree"; mkdir -p "$CTREE/nested"
printf 'alpha\n' > "$CTREE/a.txt"; printf 'beta\n' > "$CTREE/nested/b.txt"

# install-owned-creates-a-real-copy-not-a-link
fresh_home copy_real
DST="$HOME/.local/bin/wc-tool"
rc=0; err=$({ install_owned "$CSRC/tool.sh" "$DST" 1.2.3 >/dev/null; } 2>&1) || rc=$?
[[ $rc -eq 0 ]] && ok "install_owned into an absent destination exits zero" \
  || no "install_owned into an absent destination exits zero (rc=$rc): $err"
[[ -f $DST && -x $DST && ! -L $DST ]] && ok "install_owned creates a real executable file, not a symlink" \
  || no "install_owned creates a real executable file, not a symlink"
cmp -s "$CSRC/tool.sh" "$DST" && ok "the installed copy is byte-identical to its source" \
  || no "the installed copy is byte-identical to its source"
find "$HOME" -type l | grep -qxF -- "$DST" \
  && no "install_owned left a symlink at the destination" \
  || ok "no symlink under HOME at the installed path"

# install-owned-refuses-a-foreign-destination-by-name
fresh_home copy_foreign
DST="$HOME/.local/bin/wc-tool"
printf 'the user own script\n' > "$DST"; cp "$DST" "$TMP/foreign-file-before"
rc=0; err=$({ install_owned "$CSRC/tool.sh" "$DST" 1.2.3 >/dev/null; } 2>&1) || rc=$?
[[ $rc -ne 0 ]] && ok "install_owned refuses a foreign file with a non-zero return" \
  || no "install_owned refuses a foreign file with a non-zero return (rc=$rc)"
grep -qF -- "$DST" <<<"$err" && ok "the refusal names the foreign file on stderr" \
  || no "the refusal names the foreign file on stderr: $err"
cmp -s "$TMP/foreign-file-before" "$DST" && ok "the foreign file is left byte-identical" \
  || no "the foreign file is left byte-identical"
FDIR="$HOME/.local/share/foreign-tree"; mkdir -p "$FDIR"; printf 'mine\n' > "$FDIR/keep.txt"
rc=0; err=$({ install_owned "$CTREE" "$FDIR" 1.2.3 >/dev/null; } 2>&1) || rc=$?
[[ $rc -ne 0 ]] && ok "install_owned refuses a foreign directory with a non-zero return" \
  || no "install_owned refuses a foreign directory with a non-zero return (rc=$rc)"
grep -qF -- "$FDIR" <<<"$err" && ok "the refusal names the foreign directory on stderr" \
  || no "the refusal names the foreign directory on stderr: $err"
[[ -f $FDIR/keep.txt && $(cat "$FDIR/keep.txt") == mine && ! -e $FDIR/a.txt ]] \
  && ok "the foreign directory is left untouched" || no "the foreign directory is left untouched"

# install-owned-replaces-our-own-previous-symlink
fresh_home copy_relink
DST="$HOME/.local/bin/wc-tool"
ln -sfn "$ROOT/scripts/lib.sh" "$DST"
owned_link "$DST" && ok "the pre-milestone destination is one of our own symlinks" \
  || no "the pre-milestone destination is one of our own symlinks"
rc=0; err=$({ install_owned "$CSRC/tool.sh" "$DST" 1.2.3 >/dev/null; } 2>&1) || rc=$?
[[ $rc -eq 0 ]] && ok "install_owned over our own symlink exits zero" \
  || no "install_owned over our own symlink exits zero (rc=$rc): $err"
[[ -f $DST && ! -L $DST ]] && ok "the upgraded destination is a real file, not a symlink" \
  || no "the upgraded destination is a real file, not a symlink"
cmp -s "$CSRC/tool.sh" "$DST" && ok "the upgraded destination holds the copied source" \
  || no "the upgraded destination holds the copied source"
[[ -z $err ]] && ok "replacing our own symlink prints nothing on stderr" \
  || no "replacing our own symlink prints nothing on stderr: $err"

# uninstall-owned-removes-ours-and-reports-a-foreign-one
fresh_home copy_uninstall
DST="$HOME/.local/bin/wc-tool"
install_owned "$CSRC/tool.sh" "$DST" 1.2.3 >/dev/null 2>&1
RCPT=$(receipts_for "$DST" | head -1)
[[ -n $RCPT ]] && ok "install_owned writes a receipt naming the destination" \
  || no "install_owned writes a receipt naming the destination"
rc=0; out=$(uninstall_owned "$DST" 2>&1) || rc=$?
[[ $rc -eq 0 ]] && ok "uninstall_owned exits zero on an owned copy" \
  || no "uninstall_owned exits zero on an owned copy (rc=$rc): $out"
[[ ! -e $DST ]] && ok "uninstall_owned removes the installed copy" \
  || no "uninstall_owned removes the installed copy"
[[ -n $RCPT && ! -e $RCPT ]] && ok "uninstall_owned removes the receipt file" \
  || no "uninstall_owned removes the receipt file (receipt='$RCPT')"
FOREIGN="$HOME/.local/bin/not-ours"
printf 'user script\n' > "$FOREIGN"
rc=0; out=$(uninstall_owned "$FOREIGN" 2>&1) || rc=$?
[[ $rc -eq 0 ]] && ok "uninstall_owned exits zero on a foreign destination" \
  || no "uninstall_owned exits zero on a foreign destination (rc=$rc): $out"
[[ -f $FOREIGN && $(cat "$FOREIGN") == "user script" ]] \
  && ok "uninstall_owned leaves a foreign destination byte-identical" \
  || no "uninstall_owned leaves a foreign destination byte-identical"
grep -- 'left' <<<"$out" | grep -qF -- "$FOREIGN" \
  && ok "uninstall_owned reports the foreign destination it left" \
  || no "uninstall_owned reports the foreign destination it left: $out"

# uninstall-owned-keeps-a-locally-modified-copy
fresh_home copy_modified
DST="$HOME/.local/bin/wc-tool"
install_owned "$CSRC/tool.sh" "$DST" 1.2.3 >/dev/null 2>&1
printf 'locally edited\n' >> "$DST"
cat "$CSRC/tool.sh" > "$TMP/modified-expected"; printf 'locally edited\n' >> "$TMP/modified-expected"
rc=0; out=$(uninstall_owned "$DST" 2>&1) || rc=$?
[[ $rc -eq 0 ]] && ok "uninstall_owned exits zero on a locally modified copy" \
  || no "uninstall_owned exits zero on a locally modified copy (rc=$rc): $out"
[[ -e $DST ]] && cmp -s "$TMP/modified-expected" "$DST" \
  && ok "uninstall_owned keeps the locally modified copy exactly as the human left it" \
  || no "uninstall_owned keeps the locally modified copy exactly as the human left it"
grep -- 'left' <<<"$out" | grep -qF -- "$DST" \
  && ok "uninstall_owned names the modified copy it kept" \
  || no "uninstall_owned names the modified copy it kept: $out"

# install-owned-records-version-stamp-and-source-for-a-tree
fresh_home copy_tree
DST="$HOME/.local/share/workcell/plugins/demo"
rc=0; err=$({ install_owned "$CTREE" "$DST" 9.9.9 >/dev/null; } 2>&1) || rc=$?
[[ $rc -eq 0 ]] && ok "install_owned copies a directory tree and exits zero" \
  || no "install_owned copies a directory tree and exits zero (rc=$rc): $err"
[[ -n $(tree_list "$CTREE") && $(tree_list "$CTREE") == $(tree_list "$DST") ]] \
  && ok "the copied tree has the same relative file list as its source" \
  || no "the copied tree has the same relative file list as its source"
diff -r -x .workcell-stamp.json "$CTREE" "$DST" >/dev/null 2>&1 \
  && ok "the copied tree is content-identical to its source" \
  || no "the copied tree is content-identical to its source"
[[ -f $DST/.workcell-stamp.json ]] && [[ $(jq -r .version "$DST/.workcell-stamp.json" 2>/dev/null) == 9.9.9 ]] \
  && ok "the copied tree carries .workcell-stamp.json with version 9.9.9" \
  || no "the copied tree carries .workcell-stamp.json with version 9.9.9"
[[ $(installed_version "$DST") == 9.9.9 ]] && ok "installed_version prints the recorded version" \
  || no "installed_version prints the recorded version (got '$(installed_version "$DST")')"
[[ -z $(installed_version "$HOME/.local/share/workcell/plugins/never-installed") ]] \
  && ok "installed_version is empty when there is no receipt" \
  || no "installed_version is empty when there is no receipt"
RCPT=$(receipts_for "$DST" | head -1)
[[ -n $RCPT ]] && grep -qF -- "$CTREE" "$RCPT" \
  && ok "the receipt records the source path of the tree" \
  || no "the receipt records the source path of the tree (receipt='$RCPT')"

# state-and-share-dirs-derive-from-home-and-honour-overrides
fresh_home copy_dirs
unset WORKCELL_STATE WORKCELL_SHARE
sd=$(workcell_state_dir); shd=$(workcell_share_dir)
[[ $sd == "$HOME/.local/state/workcell" ]] && ok "workcell_state_dir defaults under the current HOME" \
  || no "workcell_state_dir defaults under the current HOME (got '$sd', HOME=$HOME)"
[[ $shd == "$HOME/.local/share/workcell" ]] && ok "workcell_share_dir defaults under the current HOME" \
  || no "workcell_share_dir defaults under the current HOME (got '$shd', HOME=$HOME)"
WORKCELL_STATE="$TMP/state-override"; WORKCELL_SHARE="$TMP/share-override"
export WORKCELL_STATE WORKCELL_SHARE
[[ $(workcell_state_dir) == "$WORKCELL_STATE" ]] && ok "workcell_state_dir honours WORKCELL_STATE" \
  || no "workcell_state_dir honours WORKCELL_STATE (got '$(workcell_state_dir)')"
[[ $(workcell_share_dir) == "$WORKCELL_SHARE" ]] && ok "workcell_share_dir honours WORKCELL_SHARE" \
  || no "workcell_share_dir honours WORKCELL_SHARE (got '$(workcell_share_dir)')"
DST="$HOME/.local/bin/wc-tool-override"
install_owned "$CSRC/tool.sh" "$DST" 4.5.6 >/dev/null 2>&1
[[ -n $(grep -rlF -- "$DST" "$TMP/state-override/receipts" 2>/dev/null) ]] \
  && ok "install_owned writes its receipt beneath WORKCELL_STATE" \
  || no "install_owned writes its receipt beneath WORKCELL_STATE"
unset WORKCELL_STATE WORKCELL_SHARE

# --- versioned copy install: scripts/bootstrap-tools.sh --install (#130) -------------------------
# Every harness hook dispatch invokes ~/.local/bin/tdd-guard and ~/.local/bin/build-* on every
# tool call, so what lands there has to be a self-contained, version-stamped copy rather than a
# symlink back into this working tree. One --install run against a throwaway HOME feeds the
# install, version, survival, byte-identity and drift-report cases below.
BT="$ROOT/scripts/bootstrap-tools.sh"
WRAPPERS="build-hooks build-format build-lint build-guard workcell-ws"
# wrapper_src NAME -> the repository file a wrapper destination is copied from
wrapper_src(){ case "$1" in workcell-ws) echo "$ROOT/scripts/workcell-ws";; *) echo "$ROOT/scripts/hooks/$1";; esac; }
# repo_semver -> the release, from its single source of truth
repo_semver(){ sed -n 's/^const Version = "\(.*\)"$/\1/p' "$ROOT/guard/version.go"; }
have_go(){ command -v go >/dev/null 2>&1; }
# The Go build cache is content-addressed and machine-wide, so keeping it out of the throwaway
# HOME costs nothing in hermeticity and saves a cold rebuild of the standard library per install.
GOCACHE=$(HOME="$REAL_HOME" go env GOCACHE 2>/dev/null || echo "$TMP/gocache"); export GOCACHE

fresh_home versioned_install
GUARD="$HOME/.local/bin/tdd-guard"
out=$("$BT" --install 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "bootstrap-tools --install exits zero" || no "bootstrap-tools --install exits zero (rc=$rc): $out"

# bootstrap-tools-installs-real-executables-not-symlinks
notcopy=
for b in tdd-guard $WRAPPERS; do
  if [[ $b == tdd-guard ]] && ! have_go; then continue; fi
  d="$HOME/.local/bin/$b"
  [[ -f $d && -x $d && ! -L $d ]] || notcopy="$notcopy $b"
done
have_go || printf 'skip tdd-guard install assertions (no go toolchain)\n'
[[ -z $notcopy ]] && ok "every installed tool is a real executable file, not a symlink" \
  || no "installed tools that are not real executable files:$notcopy"
into_root=$(links_into_root "$HOME")
[[ -z $into_root ]] && ok "the install leaves no symlink under HOME pointing into ROOT" \
  || no "symlinks into ROOT left by the install: $into_root"

# installed-guard-reports-the-repository-version
if have_go; then
  semver=$(repo_semver)
  [[ -n $semver ]] && ok "guard/version.go carries a semver" || no "guard/version.go carries a semver"
  gout=$("$GUARD" version 2>&1); grc=$?
  [[ $grc -eq 0 && $gout == "tdd-guard $semver"* ]] \
    && ok "the installed guard prints the repository version" \
    || no "the installed guard prints the repository version (rc=$grc): '$gout' want 'tdd-guard $semver...'"
  mkdir -p "$TMP/not-a-repo"
  gout_out=$(cd "$TMP/not-a-repo" && "$GUARD" version 2>&1); grc_out=$?
  [[ $grc_out -eq 0 && $gout_out == "$gout" ]] \
    && ok "the installed guard reports the same version outside any git repository" \
    || no "the installed guard reports the same version outside any git repository (rc=$grc_out): '$gout_out' vs '$gout'"
  # The receipt has to record what the binary itself reports, or report mode below is reading a
  # version nothing installed. (Scope: install_owned ... "$version" is what the built binary prints.)
  recorded=$(installed_version "$GUARD")
  [[ -n $recorded && "tdd-guard $recorded" == "$gout" ]] \
    && ok "the install records the built guard's own version in its receipt" \
    || no "the install records the built guard's own version in its receipt (receipt='$recorded', binary='$gout')"
fi

# installed-copies-survive-the-repo-build-output-disappearing
if have_go; then
  cp "$ROOT/bin/tdd-guard" "$TMP/guard-build-backup" 2>/dev/null
  rm -f "$ROOT/bin/tdd-guard"
  gout_gone=$("$GUARD" version 2>&1); grc_gone=$?
  [[ $grc_gone -eq 0 && $gout_gone == "$gout" ]] \
    && ok "the installed guard still runs, byte-identically, once ROOT/bin/tdd-guard is gone" \
    || no "the installed guard still runs once ROOT/bin/tdd-guard is gone (rc=$grc_gone): '$gout_gone' vs '$gout'"
  hout=$("$HOME/.local/bin/build-hooks" </dev/null 2>&1 >/dev/null); hrc=$?
  [[ $hrc -eq 2 ]] && grep -q 'usage' <<<"$hout" \
    && ok "the installed build-hooks copy still fails closed with its usage line" \
    || no "the installed build-hooks copy still fails closed with its usage line (rc=$hrc): $hout"
  [[ -f $TMP/guard-build-backup ]] && cp "$TMP/guard-build-backup" "$ROOT/bin/tdd-guard"
fi

# wrapper-copies-are-byte-identical-to-their-sources
notsame=
for b in $WRAPPERS; do
  d="$HOME/.local/bin/$b"
  { [[ ! -L $d ]] && cmp -s "$(wrapper_src "$b")" "$d"; } || notsame="$notsame $b"
done
[[ -z $notsame ]] && ok "every wrapper copy is byte-identical to its repository source" \
  || no "wrapper copies that differ from their source (or are links):$notsame"

# report-mode-names-a-version-drift-and-the-remediation
rep=$("$BT" 2>&1); rrc=$?
[[ $rrc -eq 0 ]] && ok "report mode exits zero with everything current" || no "report mode exits zero with everything current (rc=$rrc)"
clean_drift=$(grep -F -- 'scripts/bootstrap-tools.sh --install' <<<"$rep" | grep -cF -- "$(repo_semver)")
[[ $clean_drift -eq 0 ]] && ok "report mode names no drift when the installed version matches" \
  || no "report mode reported drift for a current install ($clean_drift line(s)): $rep"
if have_go; then
  STALE=0.0.1-stale
  rcpt=$(receipts_for "$GUARD" | head -1)
  if [[ -n $rcpt && -f $rcpt ]]; then
    sed 's/"version": "[^"]*"/"version": "'"$STALE"'"/' "$rcpt" > "$rcpt.stale" 2>/dev/null \
      && mv "$rcpt.stale" "$rcpt"
  fi
  [[ $(installed_version "$GUARD") == "$STALE" ]] \
    && ok "the drift fixture leaves a receipt recording a stale version" \
    || no "the drift fixture leaves a receipt recording a stale version (receipt='$rcpt', version='$(installed_version "$GUARD")')"
  rep_stale=$("$BT" 2>&1); rrc_stale=$?
  [[ $rrc_stale -eq 0 ]] && ok "report mode exits zero with a stale copy" \
    || no "report mode exits zero with a stale copy (rc=$rrc_stale): $rep_stale"
  drift=$(grep -F -- "$STALE" <<<"$rep_stale" | grep -F -- "$(repo_semver)" \
          | grep -cF -- 'scripts/bootstrap-tools.sh --install')
  [[ $drift -eq 1 ]] \
    && ok "report mode prints one drift line naming both versions and the remediation" \
    || no "report mode prints one drift line naming both versions and the remediation (got $drift): $rep_stale"
fi

# --- uninstall-removes-owned-copies-and-legacy-links-and-leaves-foreign-tools (#130) --------------
# The sweep now has three cases to get right at once: remove the copies it installed together with
# their receipts, still remove the links a pre-milestone install left into $ROOT, and never take a
# tdd-guard the human put on their own PATH.
fresh_home versioned_uninstall
GUARD="$HOME/.local/bin/tdd-guard"
out=$("$BT" --install 2>&1); rc=$?
[[ $rc -eq 0 ]] || no "bootstrap-tools --install exits zero before the uninstall sweep (rc=$rc): $out"
ln -sfn "$ROOT/scripts/hooks/build-hooks" "$HOME/.local/bin/build-hooks"   # legacy (pre-#130) install
guard_rcpt=$(receipts_for "$GUARD" | head -1)
uout=$("$INSTALL" --uninstall 2>&1); urc=$?
[[ $urc -eq 0 ]] && ok "uninstall over copies and legacy links exits zero" \
  || no "uninstall over copies and legacy links exits zero (rc=$urc): $uout"
if have_go; then
  [[ -n $guard_rcpt ]] && ok "the copy install left a receipt for tdd-guard" \
    || no "the copy install left a receipt for tdd-guard"
  [[ ! -e $GUARD && ! -L $GUARD ]] && ok "uninstall removes the copy-installed tdd-guard" \
    || no "uninstall removes the copy-installed tdd-guard"
  [[ -n $guard_rcpt && ! -e $guard_rcpt ]] && ok "uninstall removes the tdd-guard receipt too" \
    || no "uninstall removes the tdd-guard receipt too (receipt='$guard_rcpt')"
fi
[[ ! -e $HOME/.local/bin/build-hooks && ! -L $HOME/.local/bin/build-hooks ]] \
  && ok "uninstall removes the legacy build-hooks link into ROOT" \
  || no "uninstall removes the legacy build-hooks link into ROOT"
left_after=$(links_into_root "$HOME")
[[ -z $left_after ]] && ok "uninstall leaves no link into ROOT behind" || no "links into ROOT left behind: $left_after"
printf '#!/usr/bin/env bash\necho not the workcell guard\n' > "$GUARD"; chmod 0755 "$GUARD"
fout=$("$INSTALL" --uninstall 2>&1); frc=$?
[[ $frc -eq 0 ]] && ok "uninstall exits zero with a foreign tdd-guard on PATH" \
  || no "uninstall exits zero with a foreign tdd-guard on PATH (rc=$frc): $fout"
[[ -f $GUARD ]] && grep -q 'not the workcell guard' "$GUARD" \
  && ok "uninstall leaves a foreign tdd-guard exactly as the human left it" \
  || no "uninstall leaves a foreign tdd-guard exactly as the human left it"
grep -qF -- "$GUARD" <<<"$fout" && ok "uninstall names the foreign tdd-guard it left" \
  || no "uninstall names the foreign tdd-guard it left: $fout"

printf "\n%d passed, %d failed\n" "$pass" "$fail"
[[ $fail -eq 0 ]]
