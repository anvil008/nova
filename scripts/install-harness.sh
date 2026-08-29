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
  for a in "${AGENTS[@]}"; do plan "$ROOT/agents/claude/$a.md" "$HOME/.claude/agents/$a.md"; done
  plan_skills "$HOME/.claude/skills"
  [[ -d "$ROOT/plugins/claude/swarm-coder" ]] && plan "$ROOT/plugins/claude/swarm-coder" "$HOME/.claude/plugins/swarm-coder"
fi
if want codex && [[ -d $HOME/.codex ]]; then
  plan_skills "$HOME/.codex/skills"
  for a in "${AGENTS[@]}"; do plan "$DIST/$a.config.toml" "$HOME/.codex/$a.config.toml"; done
  [[ -d "$ROOT/plugins/codex/swarm-coder" ]] && plan "$ROOT/plugins/codex/swarm-coder" "$HOME/.codex/plugins/swarm-coder"
fi
if want agy; then
  for a in "${AGENTS[@]}"; do [[ -d $ROOT/agents/agy/$a ]] && plan "$ROOT/agents/agy/$a" "$HOME/.gemini/config/agents/$a"; done
  plan_skills "$HOME/.gemini/config/skills"
  [[ -d $HOME/.agents ]] && plan_skills "$HOME/.agents/skills"
  [[ -d "$ROOT/plugins/agy/swarm-coder" ]] && plan "$ROOT/plugins/agy/swarm-coder" "$HOME/.gemini/antigravity-cli/plugins/swarm-coder"
fi

if [[ $MODE == install ]]; then
  # Codex agent projection: agents/codex/*.md -> dist/codex/*.config.toml (linked below).
  if want codex && [[ -d $HOME/.codex ]]; then
    mkdir -p "$DIST"
    python3 - "$ROOT" "$DIST" "${AGENTS[@]}" <<'PY'
import json, sys
from pathlib import Path
ROOT, DIST, AGENTS = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
for name in AGENTS:
    source = ROOT / "agents" / "codex" / f"{name}.md"
    _, frontmatter, body = source.read_text().split("---", 2)
    fields = {}
    for line in frontmatter.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip("\"'")
    (DIST / f"{name}.config.toml").write_text(
        "# Generated by install-harness.sh from agents/codex/%s.md — do not hand-edit.\n" % name
        + f"description = {json.dumps(fields.get('description', ''))}\n"
        + f'model = "{fields.get("model", "gpt-5.6-sol")}"\n'
        + f'model_reasoning_effort = "{fields.get("model_reasoning_effort", "medium")}"\n'
        + f'sandbox_mode = "{fields.get("sandbox_mode", "workspace-write")}"\n'
        + f"developer_instructions = {json.dumps(body.strip())}\n"
    )
PY
  fi

  # Each foreign target is refused on its own; the rest are linked and the run ends non-zero.
  bad=0
  for i in "${!PLAN_DST[@]}"; do link_owned "${PLAN_SRC[$i]}" "${PLAN_DST[$i]}" $FORCE || bad=$((bad+1)); done
  want claude && [[ -d $HOME/.claude ]] && echo "claude: ${#AGENTS[@]} agents + ${#SKILLS[@]} skills linked"
  want agy && echo "agy: ${#AGENTS[@]} agents + ${#SKILLS[@]} skills linked"
else
  for i in "${!PLAN_DST[@]}"; do unlink_owned "${PLAN_DST[$i]}"; done
  for h in build-hooks build-format build-lint build-guard tdd-guard; do unlink_owned "$BIN/$h"; done
  [[ -d $DIST ]] && rm -f "$DIST"/*.config.toml
  echo "links into $ROOT removed (harness plugins, agents, skills, codex toml, ~/.local/bin/build-* and tdd-guard)"
fi

# ---- Codex config.toml: the [agents.*] block pointing at the linked TOMLs ----
if want codex && [[ -d $HOME/.codex ]]; then
  python3 - "$MODE" "$HOME/.codex/config.toml" "${AGENTS[@]}" <<'PY'
import re, sys
from pathlib import Path
MODE, cfg, AGENTS = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
text = cfg.read_text() if cfg.exists() else ""
text = re.sub(
    r"\n*# BEGIN SWARM CODER(?: V3)? AGENTS.*?# END SWARM CODER(?: V3)? AGENTS\n",
    "\n", text, flags=re.DOTALL,
)
if MODE == "install":
    block = "# BEGIN SWARM CODER AGENTS\n" + "".join(
        f'[agents.{name}]\nconfig_file = "{cfg.parent}/{name}.config.toml"\n'
        for name in AGENTS
    ) + "# END SWARM CODER AGENTS\n"
    cfg.write_text((text.rstrip() + "\n\n" + block) if text.strip() else block)
    print(f"codex: {len(AGENTS)} agents generated into dist/codex and linked, {cfg} updated")
else:
    cfg.write_text(text)
    print(f"codex: agents block removed from {cfg}")
PY
fi

if [[ $MODE == install ]]; then
  ((bad == 0)) || die "$bad target(s) refused (see above); the rest were linked"
  command -v tdd-guard >/dev/null || echo "note: tdd-guard/build-hooks not found — run scripts/bootstrap-tools.sh --install"
  echo "done."
else
  echo "uninstalled."
fi
