#!/usr/bin/env bash
# bootstrap-plugins.sh — install the Workcell plugin into every coding harness on
# this machine. Idempotent and reversible (legacy MCP retirement excepted; see
# register_mcp). Run scripts/bootstrap-tools.sh first: the
# plugin's hooks call ~/.local/bin/tdd-guard and build-*, which that script provides.
#
#   scripts/bootstrap-plugins.sh                    # install into every harness present
#   scripts/bootstrap-plugins.sh --harness claude   # just one (claude|codex|agy|grok)
#   scripts/bootstrap-plugins.sh --force            # also replace foreign *symlinks* (never files/dirs)
#   scripts/bootstrap-plugins.sh --uninstall        # remove everything this script installs
#
# This repository is the single source: agents/ and skills/ hold the real content and
# each plugins/<harness>/ directory is a thin wrapper that links back to them.
#
#   Claude   plugins/claude  installed as workcell@workcell via the claude CLI,
#                            from the marketplace declared in .claude-plugin/marketplace.json
#   Codex    plugins/codex   staged into dist/codex/ first, then installed via the codex
#                            CLI from dist/codex/.agents/plugins/marketplace.json. Codex
#                            copies a plugin on install and DROPS symlinks that leave the
#                            plugin root, so it gets a real tree instead of a link farm.
#                            After install, trust its non-managed hooks with `/hooks`, or
#                            bypass hook trust for one invocation with --dangerously-bypass-hook-trust.
#   Agy      plugins/agy     staged into dist/agy/ first, then installed as an
#                            owned copy into ~/.gemini/config/plugins/workcell
#   Grok     plugins/grok    staged into dist/grok/ first (Grok, like Codex, copies a
#                            plugin on install and DROPS symlinks that leave the plugin
#                            root), then installed as an owned copy at ~/.grok/plugins/workcell
#                            via install_owned. Auto-discovered and auto-trusted in user scope;
#                            no CLI required. No hooks ship: grok's hook payload is its own
#                            dialect and the gates would misparse it; the tdd-guard ceremony
#                            in the agent bodies is harness-neutral and still applies.
#
# The Claude marketplace is rooted at this repository so the wrapper's agents/ and
# skills/ symlinks resolve inside the marketplace: an install drops any symlink escaping
# the root. Codex, Grok, and Antigravity install from their staged trees under dist/. All
# four install a copy, so edits here reach them on the next run of this script.
#
# A target that already exists and is not one of our links (a real file or directory, or
# a symlink elsewhere) is never replaced: it is refused by name and the run exits
# non-zero. Agent frontmatter is validated before any harness is touched.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$ROOT/scripts/lib.sh"
HARNESS=all; MODE=install; FORCE=""
while (($#)); do case "$1" in
  --harness) HARNESS=${2:?"--harness needs claude|codex|agy|grok"}; shift 2;;
  --install) MODE=install; shift;;
  --uninstall) MODE=uninstall; shift;;
  --force) FORCE=--force; shift;;
  -h|--help) sed -n '2,30p' "$0"; exit 0;;
  *) echo "unknown arg: $1" >&2; exit 2;;
esac; done
case "$HARNESS" in all|claude|codex|agy|grok) ;; *) die "unknown harness: $HARNESS (claude|codex|agy|grok)";; esac

want(){ [[ $HARNESS == all || $HARNESS == "$1" ]]; }
BIN="$HOME/.local/bin"

# ---- validate the sources before touching any harness ----
# Every directory under skills/ is a skill and every agent file is discovered rather than
# listed, so the only structural checks are that both sets are non-empty and that each
# agent carries usable frontmatter.
compgen -G "$ROOT/skills/*/" >/dev/null || die "no skills found under $ROOT/skills"
agent_files(){ ls "$ROOT"/agents/claude/*.md "$ROOT"/agents/codex/*.md "$ROOT"/agents/grok/*.md "$ROOT"/agents/agy/*/agent.md 2>/dev/null; }
[[ -n $(agent_files) ]] || die "no agent definitions found under $ROOT/agents"
while read -r f; do
  check_frontmatter "$f" || die "invalid agent frontmatter in $f"
done < <(agent_files)

# ---- one source for per-agent model and thinking level ----
# agents/models.json decides both, per harness. Applying it here means editing that
# file and re-running this script is the whole workflow; an uninstall leaves the
# definitions alone, since they are repository content rather than something we
# installed. Missing python3 is not fatal: the frontmatter already in the tree is
# what ships, and CI checks it separately.
if command -v python3 >/dev/null; then
  if [[ $MODE == install ]]; then
    # agents/bodies/ + agents/agents.json are the source for every agent definition;
    # this regenerates every harness variant before anything is installed.
    python3 "$ROOT/scripts/sync-agents.py" || die "agent definitions could not be generated"
    # --codex-profiles also writes $CODEX_HOME/workcell-<agent>.config.toml. Codex has no
    # per-agent model surface in a plugin, so a profile (`codex --profile workcell-builder`)
    # is the only place its model and reasoning effort actually take effect. The script
    # refuses to touch a profile it did not write.
    python3 "$ROOT/scripts/sync-agent-models.py" --codex-profiles \
      || die "agents/models.json could not be applied"
  else
    python3 "$ROOT/scripts/sync-agent-models.py" --remove-codex-profiles || true
  fi
else
  echo "note: python3 not found — skipping agents/models.json sync"
fi

# ---- keep the Antigravity wrapper's skill links in step with skills/ ----
# Claude and Codex link skills/ whole. Antigravity cannot: a skill owned by one of its
# agents lives under agents/agy/<agent>/skills/ and must not also be offered globally
# (ADR 0003). So the wrapper carries one link per *shared* skill, derived here rather
# than hand-listed, so adding a skill never means editing this script.
sync_agy_skills(){
  local dir="$ROOT/plugins/agy/skills" s name owned
  mkdir -p "$dir"
  # Our links are relative by construction; owned_link covers absolute legacies.
  # Sweeping both means a renamed skill cannot leave a dangling stray behind.
  for s in "$dir"/*; do
    if owned_link "$s" || { [[ -L $s ]] && [[ $(readlink "$s") == ../../../skills/* ]]; }; then rm -f "$s"; fi
  done
  for s in "$ROOT"/skills/*/; do
    name=$(basename "$s")
    owned=$(find "$ROOT/agents/agy" -mindepth 3 -maxdepth 3 -name "$name" -print -quit 2>/dev/null || true)
    [[ -n $owned ]] && continue
    ln -sfn "../../../skills/$name" "$dir/$name"
  done
}

# ---- marketplace-installed harnesses ----
# Fields: harness | CLI | directory that must exist first | install verb | remove verb.
# The two CLIs agree on everything but the word for "install" and "uninstall".
MARKET_HARNESSES=(
  "claude|claude|$HOME/.claude|install|uninstall"
  "codex|codex|$HOME/.codex|add|remove"
)

bad=0
if [[ $MODE == install ]]; then
  if want agy; then
    sync_agy_skills
    # Retire owned Antigravity links created under the former product name.
    unlink_owned "$HOME/.gemini/config/plugins/swarm-coder"
    unlink_owned "$HOME/.gemini/antigravity-cli/plugins/swarm-coder"
    # Migration: remove our own legacy symlinks at both paths before installing the copy.
    # Do not recreate ~/.gemini/antigravity-cli/plugins/workcell.
    unlink_owned "$HOME/.gemini/config/plugins/workcell"
    unlink_owned "$HOME/.gemini/antigravity-cli/plugins/workcell"

    command -v python3 >/dev/null || die "agy: python3 is required to stage the plugin"
    python3 "$ROOT/scripts/build-agy-plugin.py" >/dev/null || die "agy: staging failed"

    version=$(_json_field "$ROOT/plugins/agy/plugin.json" version)
    if install_owned "$ROOT/dist/agy/workcell" "$HOME/.gemini/config/plugins/workcell" "$version" $FORCE; then
      echo "agy: workcell plugin copied to ~/.gemini/config/plugins/workcell"
      echo "agy: note: a new agy session is required to load changes"
      if command -v agy >/dev/null; then
        agy plugin validate "$ROOT/dist/agy/workcell" >/dev/null 2>&1 || true
      fi
    else
      bad=$((bad+1))
    fi
  fi
else
  if want agy; then
    unlink_owned "$HOME/.gemini/config/plugins/workcell"
    unlink_owned "$HOME/.gemini/antigravity-cli/plugins/workcell"
    uninstall_owned "$HOME/.gemini/config/plugins/workcell"
    # Remove live links created before the Workcell rename when they still point
    # into this repository. Foreign paths remain protected by unlink_owned.
    unlink_owned "$HOME/.gemini/config/plugins/swarm-coder"
    unlink_owned "$HOME/.gemini/antigravity-cli/plugins/swarm-coder"
  fi
  # Pre-ADR-0005 layout: one link per agent and per skill, straight into the harness
  # root. Swept by directory rather than by today's names, so links left by agents and
  # skills that have since been renamed go too. Anything not ours is passed over in
  # silence — these are the user's own directories.
  # Retire once no install predating ADR 0005 is left in the wild.
  for d in "$HOME/.claude/agents" "$HOME/.claude/skills" "$HOME/.codex" "$HOME/.codex/skills" \
           "$HOME/.gemini/config/agents" "$HOME/.gemini/config/skills" "$HOME/.agents/skills"; do
    for f in "$d"/*; do
      if owned_link "$f"; then rm -f "$f"; fi
    done
  done
  rm -f "$ROOT/dist/codex"/*.config.toml
  # Two install shapes have to come out cleanly: the symlink into $ROOT a pre-#130 install left,
  # and the receipt-owned copy that replaced it. The link is retired first so that uninstall_owned
  # then sees an absent destination and sweeps the orphaned receipt with it; running them in the
  # other order would report as "left" the very file the next call removes. Either way exactly
  # one of the two speaks, so a tool the human put there themselves is named once and kept.
  for h in build-hooks build-format build-lint build-guard tdd-guard workcell-ws; do
    if owned_link "$BIN/$h"; then unlink_owned "$BIN/$h"; fi
    uninstall_owned "$BIN/$h"
  done
  echo "removed: our links into $ROOT (legacy agents/skills) and the installed copies of build-{hooks,format,lint,guard}, workcell-ws and tdd-guard in $BIN"
fi

# ---- Codex config.toml: strip the pre-ADR-0005 [agents.*] block if it is still there ----
CODEX_CFG="$HOME/.codex/config.toml"
if want codex && [[ -f $CODEX_CFG ]] && grep -Eq '# BEGIN (WORKCELL|WORKCELL)' "$CODEX_CFG"; then
  command -v python3 >/dev/null || die "python3 is required to strip the legacy agents block from $CODEX_CFG"
  python3 - "$CODEX_CFG" <<'PY'
import re, sys
from pathlib import Path
cfg = Path(sys.argv[1])
cfg.write_text(re.sub(
    r"\n*# BEGIN (?:WORKCELL|WORKCELL)(?: V3)? AGENTS.*?# END (?:WORKCELL|WORKCELL)(?: V3)? AGENTS\n",
    "\n", cfg.read_text(), flags=re.DOTALL,
))
print(f"codex: removed legacy agents block from {cfg}")
PY
fi

for spec in "${MARKET_HARNESSES[@]}"; do
  h=${spec%%|*}; rest=${spec#*|}; cli=${rest%%|*}; rest=${rest#*|}
  guard=${rest%%|*}; rest=${rest#*|}; add=${rest%%|*}; del=${rest#*|}
  want "$h" || continue
  if [[ $MODE == install ]]; then
    [[ -d $guard ]] || continue
    # The harness directory exists but its CLI does not: nothing can register the plugin,
    # and that is the user's situation to fix, not a reason to fail the whole run.
    command -v "$cli" >/dev/null || { echo "$h: skipped — $guard exists but the $cli CLI is not on PATH"; continue; }
    # Retire the pre-rename registration before adding Workcell. These commands
    # are harmless when no legacy installation exists.
    "$cli" plugin "$del" swarm-coder@swarm-coder-local >/dev/null 2>&1 || true
    "$cli" plugin marketplace remove swarm-coder-local >/dev/null 2>&1 || true
    # Pre-marketplace layout: a bare symlink in the harness's plugin directory, which
    # neither CLI ever discovers. Remove it so it cannot shadow the real install.
    unlink_owned "$HOME/.$h/plugins/swarm-coder"
    unlink_owned "$HOME/.$h/plugins/workcell"
    root="$ROOT"
    if [[ $h == codex ]]; then
      # Codex materializes a copy and discards symlinks escaping the plugin root,
      # so the wrapper's links to skills/ and agents/ never survive. Stage a real
      # tree and register that instead.
      command -v python3 >/dev/null || die "codex: python3 is required to stage the plugin"
      python3 "$ROOT/scripts/build-codex-plugin.py" >/dev/null || die "codex: staging failed"
      root="$ROOT/dist/codex"
    fi
    # Retire the pre-rename marketplace registration: the marketplace was called
    # workcell-local before the plain name won. Harmless when nothing is there.
    "$cli" plugin "$del" workcell@workcell-local >/dev/null 2>&1 || true
    "$cli" plugin marketplace remove workcell-local >/dev/null 2>&1 || true
    # Register/validate the marketplace before touching the current install. Then force
    # a refresh: Claude otherwise keeps its cached plugin when content changes without
    # a version bump, while Codex safely tolerates the same remove/add sequence.
    "$cli" plugin marketplace add "$root" >/dev/null
    "$cli" plugin "$del" workcell@workcell >/dev/null 2>&1 || true
    "$cli" plugin "$add" workcell@workcell >/dev/null
    echo "$h: workcell plugin installed from the local marketplace"
    if [[ $h == codex ]]; then
      echo "codex: trust the Workcell plugin hooks with /hooks, or use --dangerously-bypass-hook-trust for one invocation"
    fi
  else
    unlink_owned "$HOME/.$h/plugins/swarm-coder"
    unlink_owned "$HOME/.$h/plugins/workcell"
    if command -v "$cli" >/dev/null; then
      "$cli" plugin "$del" swarm-coder@swarm-coder-local >/dev/null 2>&1 || true
      "$cli" plugin marketplace remove swarm-coder-local >/dev/null 2>&1 || true
      # Clean up installations made before the Workcell rename and the
      # workcell-local marketplace name that preceded the plain one.
      "$cli" plugin "$del" workcell@workcell-local >/dev/null 2>&1 || true
      "$cli" plugin marketplace remove workcell-local >/dev/null 2>&1 || true
      "$cli" plugin "$del" workcell@workcell >/dev/null 2>&1 || true
      "$cli" plugin marketplace remove workcell >/dev/null 2>&1 || true
    fi
  fi
done

# ---- Grok Build ----
# Grok consumes the Claude plugin layout (manifest, agents/*.md, skills/) but, like
# Codex, copies a plugin on install and drops symlinks that leave the plugin root, so
# it too stages a real tree first. Grok auto-discovers and auto-trusts plugins at
# ~/.grok/plugins/<name>, so it needs no grok CLI at all to install. When the CLI is
# present, retire legacy marketplace registrations from earlier versions.
grok_plugin(){
  want grok || return 0
  [[ -d $HOME/.grok ]] || return 0
  if [[ $MODE == install ]]; then
    command -v python3 >/dev/null || die "grok: python3 is required to stage the plugin"
    python3 "$ROOT/scripts/build-grok-plugin.py" >/dev/null || die "grok: staging failed"
    # Retire legacy marketplace registrations when the grok CLI is available.
    if command -v grok >/dev/null; then
      grok plugin uninstall workcell >/dev/null 2>&1 || true
      grok plugin marketplace remove "$ROOT/dist/grok" >/dev/null 2>&1 || true
      grok plugin marketplace remove "$ROOT" >/dev/null 2>&1 || true
    fi
    local version
    version=$(repo_semver)
    if install_owned "$ROOT/dist/grok/plugins/workcell" "$HOME/.grok/plugins/workcell" "$version" $FORCE; then
      echo "grok: workcell plugin installed at $HOME/.grok/plugins/workcell (start a new session or press 'r' in Grok's Plugins tab to load changes)"
    else
      bad=$((bad+1))
    fi
  else
    if command -v grok >/dev/null; then
      grok plugin uninstall workcell >/dev/null 2>&1 || true
      grok plugin marketplace remove "$ROOT/dist/grok" >/dev/null 2>&1 || true
      grok plugin marketplace remove "$ROOT" >/dev/null 2>&1 || true
    fi
    uninstall_owned "$HOME/.grok/plugins/workcell"
  fi
}
grok_plugin

# ---- retire the MCP servers this script used to register ----
# Every browser surface, the debugger's diagnostics included, now runs through the
# agent-browser CLI (ADR 0012): no agent carries MCP browser tool definitions, so no
# MCP server is registered at all. This block only *retires* the servers earlier
# versions of this script wrote (playwright, then chrome-devtools) — and only while
# an entry still runs exactly the command we wrote, so a customized entry stays.
# Drop it once no install from those eras is left.
register_mcp(){
  local name cmd
  for spec in "playwright|@playwright/mcp@latest" "chrome-devtools|chrome-devtools-mcp@latest"; do
    name=${spec%%|*}; cmd=${spec#*|}
    if want claude && command -v claude >/dev/null \
       && claude mcp get "$name" 2>/dev/null | grep -qF -- "$cmd"; then
      claude mcp remove "$name" -s user >/dev/null 2>&1 && echo "claude: $name MCP server retired"
    fi
    if want codex && command -v codex >/dev/null \
       && codex mcp get "$name" 2>/dev/null | grep -qF -- "$cmd"; then
      codex mcp remove "$name" >/dev/null 2>&1 && echo "codex: $name MCP server retired"
    fi
    if want agy && command -v agy >/dev/null \
       && agy mcp list 2>/dev/null | grep "^${name}[[:space:]]" | grep -qF -- "$cmd"; then
      agy mcp remove "$name" >/dev/null 2>&1 && echo "agy: $name MCP server retired"
    fi
    if want grok && command -v grok >/dev/null \
       && grok mcp list 2>/dev/null | grep "$name" | grep -qF -- "$cmd"; then
      grok mcp remove "$name" >/dev/null 2>&1 && echo "grok: $name MCP server retired"
    fi
  done
}

if [[ $MODE == install ]]; then
  register_mcp
  ((bad == 0)) || die "$bad target(s) refused (see above); the rest were installed"
  command -v tdd-guard >/dev/null || echo "note: tdd-guard/build-hooks not found — run scripts/bootstrap-tools.sh --install"
  echo "done."
else
  # Say what was deliberately left behind, using the same ownership test as unlink_owned.
  report_unowned "$HOME/.claude/plugins" "$HOME/.codex/plugins" \
                 "$HOME/.gemini/config/plugins" "$HOME/.gemini/antigravity-cli/plugins" \
                 "$HOME/.grok/plugins"
  echo "uninstalled."
fi
