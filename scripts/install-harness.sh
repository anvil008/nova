#!/usr/bin/env bash
# Install the Swarm Coder agents + skills into your coding harness(es).
# Idempotent and reversible. Run scripts/bootstrap-tools.sh first (for tdd-guard
# + build-hooks, which the builder agent's Claude/AGY hooks reference).
#
#   scripts/install-harness.sh                      # install into all present harnesses
#   scripts/install-harness.sh --harness claude     # just one (claude|codex|agy)
#   scripts/install-harness.sh --force              # also replace foreign *symlinks* (never files/dirs)
#   scripts/install-harness.sh --uninstall          # remove what this script installs
#
# This repository is the single source. Everything the harnesses see is a symlink
# back into it, so editing a file here takes effect immediately with no re-install:
#   - Claude:      ~/.claude/agents/<agent>.md      -> agents/claude/<agent>.md
#   - Antigravity: ~/.gemini/config/agents/<agent>  -> agents/agy/<agent>/
#   - Codex:       ~/.codex/<agent>.config.toml     -> dist/codex/<agent>.config.toml
#   - Skills:      <harness>/skills/<skill>         -> skills/<skill>
#
# A target that already exists and is not one of our links (a real file/dir, or a
# symlink elsewhere) is never replaced: it is refused by name and the run exits
# non-zero. Agent frontmatter is validated before any harness is touched. Uninstall
# removes only links into this repository, including the ~/.local/bin/build-* and
# tdd-guard links, and reports what it leaves behind.
#
# Codex is the one exception to "edit and go": its harness requires a generated
# TOML with the agent body embedded as an escaped string, so it cannot read the
# markdown directly. The generated file is built into dist/ (gitignored) and
# symlinked from ~/.codex, keeping this repo the source — but a change to
# agents/codex/*.md needs a re-run of this script to reach Codex.
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
  -h|--help) sed -n '2,28p' "$0"; exit 0;;
  *) echo "unknown arg: $1" >&2; exit 2;;
esac; done
case "$HARNESS" in all|claude|codex|agy) ;; *) die "unknown harness: $HARNESS (claude|codex|agy)";; esac

want(){ [[ $HARNESS == all || $HARNESS == "$1" ]]; }
AGENTS=(builder code-reviewer docs research)
BIN="$HOME/.local/bin"

# Every directory under skills/ is a skill. Discovered, not listed, so adding
# one is a matter of creating the directory.
SKILLS=()
for d in "$ROOT"/skills/*/; do [[ -d $d ]] && SKILLS+=("$(basename "$d")"); done
((${#SKILLS[@]})) || die "no skills found under $ROOT/skills"

# ---- validate the sources before touching any harness ----
for a in "${AGENTS[@]}"; do
  for f in "$ROOT/agents/claude/$a.md" "$ROOT/agents/codex/$a.md"; do
    [[ -f $f ]] || die "missing agent source $f"
    check_frontmatter "$f" || die "invalid agent frontmatter in $f"
  done
done
command -v python3 >/dev/null || die "python3 is required (codex agent projection)"

# ---- plan: every SRC DST pair, in install order ----
# Recorded as parallel arrays so the whole plan can be checked before any link is made.
PLAN_SRC=(); PLAN_DST=()
plan(){ PLAN_SRC+=("$1"); PLAN_DST+=("$2"); }
plan_skills(){ local s; for s in "${SKILLS[@]}"; do plan "$ROOT/skills/$s" "$1/$s"; done; }
DIST="$ROOT/dist/codex"

if want claude && [[ -d $HOME/.claude ]]; then
  [[ -d "$ROOT/plugins/claude/swarm-coder" ]] && plan "$ROOT/plugins/claude/swarm-coder" "$HOME/.claude/plugins/swarm-coder"
fi
if want codex && [[ -d $HOME/.codex ]]; then
  [[ -d "$ROOT/plugins/codex/swarm-coder" ]] && plan "$ROOT/plugins/codex/swarm-coder" "$HOME/.codex/plugins/swarm-coder"
fi
if want agy; then
  [[ -d "$ROOT/plugins/agy/swarm-coder" ]] && plan "$ROOT/plugins/agy/swarm-coder" "$HOME/.gemini/config/plugins/swarm-coder"
  [[ -d "$ROOT/plugins/agy/swarm-coder" ]] && plan "$ROOT/plugins/agy/swarm-coder" "$HOME/.gemini/antigravity-cli/plugins/swarm-coder"
fi

if [[ $MODE == install ]]; then
  # Each foreign target is refused on its own; the rest are linked and the run ends non-zero.
  bad=0
  for i in "${!PLAN_DST[@]}"; do link_owned "${PLAN_SRC[$i]}" "${PLAN_DST[$i]}" $FORCE || bad=$((bad+1)); done
  want claude && [[ -d $HOME/.claude ]] && echo "claude: swarm-coder plugin linked"
  want codex && [[ -d $HOME/.codex ]] && echo "codex: swarm-coder plugin linked"
  want agy && echo "agy: swarm-coder plugin linked"
else
  for i in "${!PLAN_DST[@]}"; do unlink_owned "${PLAN_DST[$i]}"; done
  # Legacy flat symlink cleanup
  for a in "${AGENTS[@]}"; do
    unlink_owned "$HOME/.claude/agents/$a.md"
    unlink_owned "$HOME/.codex/$a.config.toml"
    unlink_owned "$HOME/.gemini/config/agents/$a"
  done
  for s in "${SKILLS[@]}"; do
    unlink_owned "$HOME/.claude/skills/$s"
    unlink_owned "$HOME/.codex/skills/$s"
    unlink_owned "$HOME/.gemini/config/skills/$s"
    unlink_owned "$HOME/.agents/skills/$s"
  done
  for h in build-hooks build-format build-lint build-guard tdd-guard; do unlink_owned "$BIN/$h"; done
  [[ -d $DIST ]] && rm -f "$DIST"/*.config.toml
  echo "links into $ROOT removed (harness plugins, legacy agents/skills, ~/.local/bin/build-* and tdd-guard)"
fi

# ---- Codex config.toml: remove legacy [agents.*] block if present ----
if want codex && [[ -d $HOME/.codex && -f $HOME/.codex/config.toml ]]; then
  python3 - "$HOME/.codex/config.toml" <<'PY'
import re, sys
from pathlib import Path
cfg = Path(sys.argv[1])
text = cfg.read_text() if cfg.exists() else ""
new_text = re.sub(
    r"\n*# BEGIN SWARM CODER(?: V3)? AGENTS.*?# END SWARM CODER(?: V3)? AGENTS\n",
    "\n", text, flags=re.DOTALL,
)
if new_text != text:
    cfg.write_text(new_text)
    print(f"codex: removed legacy agents block from {cfg}")
PY
fi

if [[ $MODE == install ]]; then
  ((bad == 0)) || die "$bad target(s) refused (see above); the rest were linked"
  command -v tdd-guard >/dev/null || echo "note: tdd-guard/build-hooks not found — run scripts/bootstrap-tools.sh --install"
  echo "done."
else
  # Report any foreign items left behind in target directories
  for d in "$HOME/.claude/plugins" "$HOME/.codex/plugins" "$HOME/.gemini/config/plugins" "$HOME/.gemini/antigravity-cli/plugins"; do
    if [[ -d "$d" ]]; then
      for f in "$d"/*; do
        if [[ -e "$f" || -L "$f" ]]; then
          tgt=$(readlink "$f" 2>/dev/null || true)
          [[ -z "$tgt" || ! "$tgt" =~ ^"$ROOT" ]] && echo "kept unmanaged: $f"
        fi
      done
    fi
  done
  echo "uninstalled."
fi
