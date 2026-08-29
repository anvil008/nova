#!/usr/bin/env bash
# bootstrap-plugins.sh — install the Swarm Coder plugin into every coding harness on
# this machine. Idempotent and reversible. Run scripts/bootstrap-tools.sh first: the
# plugin's hooks call ~/.local/bin/tdd-guard and build-*, which that script provides.
#
#   scripts/bootstrap-plugins.sh                    # install into every harness present
#   scripts/bootstrap-plugins.sh --harness claude   # just one (claude|codex|agy)
#   scripts/bootstrap-plugins.sh --force            # also replace foreign *symlinks* (never files/dirs)
#   scripts/bootstrap-plugins.sh --uninstall        # remove everything this script installs
#
# This repository is the single source: agents/ and skills/ hold the real content and
# each plugins/<harness>/ directory is a thin wrapper that links back to them.
#
#   Claude   plugins/claude  installed as swarm-coder@swarm-coder-local via the claude CLI,
#                            from the marketplace declared in .claude-plugin/marketplace.json
#   Codex    plugins/codex   installed the same way via the codex CLI, from
#                            .agents/plugins/marketplace.json
#   Agy      plugins/agy     symlinked into ~/.gemini/config/plugins/swarm-coder and
#                            ~/.gemini/antigravity-cli/plugins/swarm-coder
#
# Both marketplaces are rooted at this repository so the wrappers' agents/ and skills/
# symlinks resolve inside the marketplace: an install drops any symlink escaping the root.
# Claude and Codex install a copy, so edits here reach them on the next run of this
# script; the Antigravity links are live and need no re-install.
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
  --harness) HARNESS=${2:?"--harness needs claude|codex|agy"}; shift 2;;
  --install) MODE=install; shift;;
  --uninstall) MODE=uninstall; shift;;
  --force) FORCE=--force; shift;;
  -h|--help) sed -n '2,30p' "$0"; exit 0;;
  *) echo "unknown arg: $1" >&2; exit 2;;
esac; done
case "$HARNESS" in all|claude|codex|agy) ;; *) die "unknown harness: $HARNESS (claude|codex|agy)";; esac

want(){ [[ $HARNESS == all || $HARNESS == "$1" ]]; }
BIN="$HOME/.local/bin"

# ---- validate the sources before touching any harness ----
# Every directory under skills/ is a skill and every agent file is discovered rather than
# listed, so the only structural checks are that both sets are non-empty and that each
# agent carries usable frontmatter.
compgen -G "$ROOT/skills/*/" >/dev/null || die "no skills found under $ROOT/skills"
agent_files(){ ls "$ROOT"/agents/claude/*.md "$ROOT"/agents/codex/*.md "$ROOT"/agents/agy/*/agent.md 2>/dev/null; }
[[ -n $(agent_files) ]] || die "no agent definitions found under $ROOT/agents"
while read -r f; do
  check_frontmatter "$f" || die "invalid agent frontmatter in $f"
done < <(agent_files)

# ---- keep the Antigravity wrapper's skill links in step with skills/ ----
# Claude and Codex link skills/ whole. Antigravity cannot: a skill owned by one of its
# agents lives under agents/agy/<agent>/skills/ and must not also be offered globally
# (ADR 0003). So the wrapper carries one link per *shared* skill, derived here rather
# than hand-listed, so adding a skill never means editing this script.
sync_agy_skills(){
  local dir="$ROOT/plugins/agy/skills" s name owned
  mkdir -p "$dir"
  for s in "$dir"/*; do owned_link "$s" && rm -f "$s"; done
  for s in "$ROOT"/skills/*/; do
    name=$(basename "$s")
    owned=$(find "$ROOT/agents/agy" -mindepth 3 -maxdepth 3 -name "$name" -print -quit 2>/dev/null || true)
    [[ -n $owned ]] && continue
    ln -sfn "../../../skills/$name" "$dir/$name"
  done
}

# ---- plan the symlink targets (Antigravity only) ----
# Fields: harness | directory that must exist first ("-" = install anyway) | destination.
# Antigravity is unguarded: it creates ~/.gemini on first run.
PLUGIN_TARGETS=(
  "agy|-|$HOME/.gemini/config/plugins/swarm-coder"
  "agy|-|$HOME/.gemini/antigravity-cli/plugins/swarm-coder"
)
PLAN_DST=()
for spec in "${PLUGIN_TARGETS[@]}"; do
  h=${spec%%|*}; rest=${spec#*|}; guard=${rest%%|*}; dst=${rest#*|}
  want "$h" || continue
  [[ $guard == - || -d $guard ]] || continue
  [[ -d "$ROOT/plugins/$h" ]] || continue
  PLAN_DST+=("$dst")
done

# ---- marketplace-installed harnesses ----
# Fields: harness | CLI | directory that must exist first | install verb | remove verb.
# The two CLIs agree on everything but the word for "install" and "uninstall".
MARKET_HARNESSES=(
  "claude|claude|$HOME/.claude|install|uninstall"
  "codex|codex|$HOME/.codex|add|remove"
)

if [[ $MODE == install ]]; then
  sync_agy_skills
  bad=0
  for dst in ${PLAN_DST[@]+"${PLAN_DST[@]}"}; do
    link_owned "$ROOT/plugins/agy" "$dst" $FORCE || bad=$((bad+1))
  done
  ((${#PLAN_DST[@]})) && echo "agy: swarm-coder plugin linked"
else
  for dst in ${PLAN_DST[@]+"${PLAN_DST[@]}"}; do unlink_owned "$dst"; done
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
  for h in build-hooks build-format build-lint build-guard tdd-guard; do unlink_owned "$BIN/$h"; done
  echo "links into $ROOT removed (agy plugin, legacy agents/skills, ~/.local/bin/build-* and tdd-guard)"
fi

# ---- Codex config.toml: strip the pre-ADR-0005 [agents.*] block if it is still there ----
CODEX_CFG="$HOME/.codex/config.toml"
if want codex && [[ -f $CODEX_CFG ]] && grep -q '# BEGIN SWARM CODER' "$CODEX_CFG"; then
  command -v python3 >/dev/null || die "python3 is required to strip the legacy agents block from $CODEX_CFG"
  python3 - "$CODEX_CFG" <<'PY'
import re, sys
from pathlib import Path
cfg = Path(sys.argv[1])
cfg.write_text(re.sub(
    r"\n*# BEGIN SWARM CODER(?: V3)? AGENTS.*?# END SWARM CODER(?: V3)? AGENTS\n",
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
    # Pre-marketplace layout: a bare symlink in the harness's plugin directory, which
    # neither CLI ever discovers. Remove it so it cannot shadow the real install.
    unlink_owned "$HOME/.$h/plugins/swarm-coder"
    "$cli" plugin marketplace add "$ROOT" >/dev/null
    "$cli" plugin "$add" swarm-coder@swarm-coder-local >/dev/null
    echo "$h: swarm-coder plugin installed from the local marketplace"
  else
    unlink_owned "$HOME/.$h/plugins/swarm-coder"
    if command -v "$cli" >/dev/null; then
      "$cli" plugin "$del" swarm-coder@swarm-coder-local >/dev/null 2>&1 || true
      "$cli" plugin marketplace remove swarm-coder-local >/dev/null 2>&1 || true
    fi
  fi
done

if [[ $MODE == install ]]; then
  ((bad == 0)) || die "$bad target(s) refused (see above); the rest were installed"
  command -v tdd-guard >/dev/null || echo "note: tdd-guard/build-hooks not found — run scripts/bootstrap-tools.sh --install"
  echo "done."
else
  # Say what was deliberately left behind, using the same ownership test as unlink_owned.
  report_unowned "$HOME/.claude/plugins" "$HOME/.codex/plugins" \
                 "$HOME/.gemini/config/plugins" "$HOME/.gemini/antigravity-cli/plugins"
  echo "uninstalled."
fi
