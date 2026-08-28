#!/usr/bin/env bash
# project-bootstrap.sh — make ONE project folder ready for the Swarm Coder builder,
# idempotently and non-interactively (safe to call from a benchmark / SWE-eval setup step).
#
#   scripts/project-bootstrap.sh [DIR]              report: detected stack + tool readiness
#   scripts/project-bootstrap.sh --install [DIR]    install the aux hooks + missing per-stack tools
#   scripts/project-bootstrap.sh --with-hooks [DIR] also wire format/lint/guard INTO the repo, so a
#                                                   single-agent run in DIR gets them without the
#                                                   builder subagent's frontmatter
#
# Design notes:
#  * Stacks are detected by manifest; everything is best-effort and offline-tolerant — a missing
#    tool is reported, never fatal.
#  * --with-hooks writes .claude/settings.local.json and local-ignores it via the repo's
#    info/exclude (resolved with git rev-parse, so worktrees and jj workspaces are covered too),
#    so the gates never show up in a scored eval patch.
#  * It wires ONLY the advisory gates (build-format / build-lint / build-guard), NOT the tdd-guard
#    RED->seal->GREEN ceremony: that assumes the agent authors the failing tests, whereas an eval
#    supplies them. The TDD gate stays with the builder subagent's own frontmatter.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$ROOT/scripts/lib.sh"
BIN="$HOME/.local/bin"
install=0; withhooks=0; DIR=""
for a in "$@"; do case "$a" in
  --install) install=1;; --with-hooks) withhooks=1; install=1;;
  -h|--help) sed -n '2,17p' "$0"; exit 0;; *) DIR="$a";; esac; done
DIR="${DIR:-$PWD}"; cd "$DIR" || die "no such dir: $DIR"
have(){ command -v "$1" >/dev/null 2>&1; }
pick(){ local s pm pkg; for s in "$@"; do pm=${s%%:*}; pkg=${s#*:}; case "$pm" in
  brew) have brew&&{ echo "brew install $pkg";return;};; apt) have apt-get&&{ echo "sudo apt-get install -y $pkg";return;};;
  cargo) have cargo&&{ echo "cargo install --locked $pkg";return;};; npm) have npm&&{ echo "npm install -g $pkg";return;};;
  uv) have uv&&{ echo "uv tool install $pkg";return;};; pipx) have pipx&&{ echo "pipx install $pkg";return;};;
  go) have go&&{ echo "go install $pkg";return;};; rustup) have rustup&&{ echo "rustup component add $pkg";return;};; esac; done; }
need(){ # name | install-cmd | purpose
  local n=$1 cmd=$2 why=$3
  if have "$n"; then printf '  present  %-14s %s\n' "$n" "$why"; return 0; fi
  if   [[ -z $cmd ]]; then printf '  missing  %-14s %s  (install manually)\n' "$n" "$why"
  elif ((install)); then printf '  install  %-14s %s\n           + %s\n' "$n" "$why" "$cmd"; run_install "$cmd" || printf '           (failed — do it manually)\n'
  else printf '  missing  %-14s %s\n           install: %s\n' "$n" "$why" "$cmd"; fi; }

echo "project-bootstrap: $DIR"

# --- detect stacks by manifest -----------------------------------------------------------------
stacks=()
[[ -f go.mod ]] && stacks+=(go)
{ [[ -f pyproject.toml || -f setup.py || -f setup.cfg ]] || compgen -G 'requirements*.txt' >/dev/null; } && stacks+=(py)
[[ -f Cargo.toml ]] && stacks+=(rust)
[[ -f package.json ]] && stacks+=(node)
[[ ${#stacks[@]} -eq 0 ]] && echo "  (no known manifest — go.mod / pyproject.toml / Cargo.toml / package.json)"
echo "  stacks: ${stacks[*]-none}"

# --- per-stack format/lint tools ---------------------------------------------------------------
echo "== tools the builder hooks use for this stack =="
for s in ${stacks[@]+"${stacks[@]}"}; do case "$s" in
  go)   need gofmt "" "Go format";                        need goimports "$(pick go:golang.org/x/tools/cmd/goimports@latest)" "Go imports" ;;
  py)   need ruff "$(pick uv:ruff pipx:ruff)" "Python format+lint";  need pyright "$(pick npm:pyright)" "Python types" ;;
  rust) need rustfmt "$(pick rustup:rustfmt)" "Rust format";         need clippy-driver "$(pick rustup:clippy)" "Rust lint" ;;
  node) need prettier "$(pick npm:prettier)" "JS/TS format";         need eslint "$(pick npm:eslint)" "JS/TS lint" ;;
esac; done

# --- the gate binaries themselves --------------------------------------------------------------
echo "== gate binaries =="
if ((install)); then
  # Symlinked, not copied (same as bootstrap-tools.sh): editing scripts/hooks/* takes effect immediately.
  for b in build-format build-lint build-guard; do link_owned "$ROOT/scripts/hooks/$b" "$BIN/$b" || die "could not link $b into $BIN"; done
  echo "  linked build-{format,lint,guard} -> $ROOT/scripts/hooks/"
fi
for b in build-format build-lint build-guard; do
  [[ -x $BIN/$b ]] && printf '  present  %s\n' "$b" || printf '  missing  %s  (run scripts/project-bootstrap.sh --install)\n' "$b"; done
[[ -x $BIN/tdd-guard ]] && printf '  present  tdd-guard (TDD gate, builder-subagent only)\n' \
                        || printf '  missing  tdd-guard  (run scripts/bootstrap-tools.sh --install)\n'

# --- optional: wire advisory gates into the repo for single-agent runs -------------------------
if ((withhooks)); then
  echo "== wiring advisory gates into .claude/settings.local.json =="
  mkdir -p .claude
  ROOT="$ROOT" BIN="$BIN" python3 - <<'PY'
import json, os
BIN = os.environ["BIN"]
p = ".claude/settings.local.json"
cfg = {}
if os.path.exists(p):
    try: cfg = json.load(open(p))
    except Exception: cfg = {}
hooks = cfg.setdefault("hooks", {})
want = {
  "PreToolUse":  [("Bash", [f"{BIN}/build-guard claude"])],
  "PostToolUse": [("Edit|Write|MultiEdit|NotebookEdit", [f"{BIN}/build-format claude", f"{BIN}/build-lint claude"])],
}
def has(group, cmd):
    return any(h.get("command") == cmd for h in group.get("hooks", []))
for ev, entries in want.items():
    arr = hooks.setdefault(ev, [])
    for matcher, cmds in entries:
        grp = next((g for g in arr if g.get("matcher") == matcher), None)
        if grp is None:
            grp = {"matcher": matcher, "hooks": []}; arr.append(grp)
        for c in cmds:
            if not has(grp, c): grp["hooks"].append({"type": "command", "command": c})
json.dump(cfg, open(p, "w"), indent=2); open(p, "a").write("\n")
print(f"  wrote {p} (format + lint + guard; NOT the TDD seal ceremony)")
PY
  # keep it out of any scored patch / commit; --git-path resolves to the common dir, so a
  # worktree (.git is a file) or jj workspace gets the shared info/exclude, not a dead path
  if ex=$(git rev-parse --git-path info/exclude 2>/dev/null); then
    mkdir -p "$(dirname "$ex")"
    if ! grep -qxF '.claude/settings.local.json' "$ex" 2>/dev/null; then
      echo '.claude/settings.local.json' >> "$ex"; echo "  local-ignored via $ex (invisible to git diff)"
    fi
  else
    echo "  not a git repository: .claude/settings.local.json is not local-ignored"
  fi
fi
echo "done."
