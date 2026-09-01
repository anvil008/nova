#!/usr/bin/env bash
# Bootstrap a fresh environment for the Workcell harness: install the external
# tools the agents/skills and the tdd-guard gate depend on, then build tdd-guard
# and the build-hooks wrapper.
#
#   scripts/bootstrap-tools.sh            # report what is present / missing
#   scripts/bootstrap-tools.sh --install  # install what is missing (best effort)
#
# Installs are best effort: they use the first of brew / apt / cargo / npm / uv
# that is present, else print a manual hint. Only an apt fallback needs sudo, and
# it runs in the foreground so the prompt is visible (skipped without a terminal).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$ROOT/scripts/lib.sh"
install=0; [[ ${1:-} == "--install" ]] && install=1
have(){ command -v "$1" >/dev/null 2>&1; }
mkdir -p "$HOME/.local/bin"

# pick <pm:pkg>... -> the install command for the first available package manager
pick(){
  local spec pm pkg
  for spec in "$@"; do
    pm=${spec%%:*}; pkg=${spec#*:}
    case "$pm" in
      brew)  have brew    && { echo "brew install $pkg"; return; };;
      apt)   have apt-get && { echo "sudo apt-get install -y $pkg"; return; };;
      cargo) have cargo   && { echo "cargo install --locked $pkg"; return; };;
      npm)   have npm     && { echo "npm install -g $pkg"; return; };;
      uv)    have uv      && { echo "uv tool install $pkg"; return; };;
      pipx)  have pipx    && { echo "pipx install $pkg"; return; };;
    esac
  done
}

report(){ if p=$(command -v "$1" 2>/dev/null); then printf 'present  %-26s %s\n' "$1" "$p"; return 0; else printf 'missing  %-26s\n' "$1"; return 1; fi; }
need(){ # name | install-cmd | purpose | required(0/1)
  local n=$1 cmd=$2 why=$3 req=${4:-0}
  report "$n" && return 0
  printf '         %s%s\n' "$why" "$( ((req)) && echo '  [required]' )"
  if [[ -z $cmd ]]; then printf '         install it manually for your OS\n'
  elif ((install)); then printf '         + %s\n' "$cmd"; run_install "$cmd" || printf '         (failed — install manually)\n'
  else printf '         install: %s\n' "$cmd"; fi
}

# --- installed-copy drift (#130) ----------------------------------------------------------------
# What lands in ~/.local/bin is a version-stamped copy rather than a link into this working tree,
# so a repository that has moved on since the last --install is invisible unless report mode says
# so. Absent tools, absent receipts and current versions stay quiet, and nothing here can fail:
# report mode's job is to describe the machine, never to refuse to describe it.
WRAPPERS=(build-hooks build-format build-lint build-guard workcell-ws)
# wrapper_src NAME -> the repository file that wrapper is copied from.
wrapper_src(){ case "$1" in workcell-ws) echo "$ROOT/scripts/workcell-ws";; *) echo "$ROOT/scripts/hooks/$1";; esac; }
# version_current INSTALLED REPO -> true when INSTALLED is REPO, or REPO plus a build-metadata
# suffix; callers establish that both are non-empty. The guard is stamped at link time, so a
# correct install records "0.6.0+abc1234"; comparing that against "0.6.0" as plain strings would
# report every install as drift.
version_current(){ [[ $1 == "$2" || $1 == "$2+"* ]]; }
# stale_line NAME DETAIL -> the one drift line. Kept in one place so every stale tool names the
# same remediation, which is the only thing the human has to do about any of them.
stale_line(){ printf '  stale    %-26s %s — re-run: scripts/bootstrap-tools.sh --install\n' "$1" "$2"; }
# report_guard_drift -> names the installed guard when its receipt records a version other than
# the repository's, so the two versions and the fix appear on one line.
report_guard_drift(){
  local dst="$HOME/.local/bin/tdd-guard" have want
  [[ -e $dst ]] || return 0
  have=$(installed_version "$dst"); want=$(repo_semver)
  [[ -n $have && -n $want ]] || return 0
  version_current "$have" "$want" || stale_line tdd-guard "installed $have, repository $want"
}
# report_wrapper_drift -> the same for the shell wrappers, which carry no version of their own:
# the installed copy is current exactly when it is still byte-identical to the file it came from.
report_wrapper_drift(){
  local h dst src
  for h in "${WRAPPERS[@]}"; do
    dst="$HOME/.local/bin/$h"; src=$(wrapper_src "$h")
    { [[ -e $dst ]] && [[ -n $(installed_version "$dst") ]]; } || continue
    cmp -s "$src" "$dst" || stale_line "$h" "the installed copy differs from $src"
  done
}

echo "== core (required) =="
need go      "$(pick brew:go apt:golang-go)"                             "Go toolchain — builds tdd-guard" 1
need git     "$(pick brew:git apt:git)"                                  "version control" 1
need python3 "$(pick brew:python3 apt:python3)"                          "skill helpers (render / waves / docs-check)" 1
need jq      "$(pick brew:jq apt:jq)"                                    "JSON parser — hooks rely on it" 1
need ast-grep "$(pick npm:@ast-grep/cli cargo:ast-grep brew:ast-grep)"  "structural search + tdd-guard arch-check"
need jj      "$(pick brew:jj cargo:jj-cli)"                              "Jujutsu VCS — the builder's jj skill"
need gh      "$(pick brew:gh apt:gh)"                                    "GitHub CLI — planner/build create issues + milestones"
need apm     "curl -sSL https://aka.ms/apm-unix | sh"                    "Agent Package Manager — third-party global agent packages (apm install -g)"
need agent-browser "$(pick npm:agent-browser)"                           "token-lean browser CLI — the builder's runtime check on codex/agy"

echo
echo "== build the tdd-guard gate =="
if [[ -e $ROOT/bin/anvil-guard || -L $ROOT/bin/anvil-guard ]]; then
  if ((install)); then
    rm -f "$ROOT/bin/anvil-guard"
    echo "  removed orphaned $ROOT/bin/anvil-guard (the supported artifact is tdd-guard)"
  else
    echo "  orphaned $ROOT/bin/anvil-guard is present; --install removes it"
  fi
fi
if ! ((install)); then
  echo "  would build and install ~/.local/bin/tdd-guard (run with --install)"
  report_guard_drift
elif have go; then
  # The binary is still a build artifact, so it is built into the repo's gitignored bin/ — but
  # what lands on PATH is a copy, not a link back here. Every harness hook dispatch runs
  # ~/.local/bin/tdd-guard on every tool call, so it has to keep working when this working tree
  # is rebuilt, moved, or checked out at another revision.
  mkdir -p "$ROOT/bin" "$HOME/.local/bin"
  ( cd "$ROOT" && go build -buildvcs=false \
      -ldflags "-X github.com/anvil008/workcell/guard.BuildMetadata=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" \
      -o "$ROOT/bin/tdd-guard" ./cmd/tdd-guard ) || die "go build ./cmd/tdd-guard failed"
  # The receipt records what the binary itself reports, build metadata included, so report mode
  # compares against the thing that was actually installed rather than against a second guess at
  # it. The semver still comes from guard.Version; the stamp only appends the commit.
  gver=$("$ROOT/bin/tdd-guard" version) || die "the freshly built $ROOT/bin/tdd-guard does not run"
  gver=${gver#tdd-guard }
  install_owned "$ROOT/bin/tdd-guard" "$HOME/.local/bin/tdd-guard" "$gver" \
    || die "could not install tdd-guard into ~/.local/bin"
  echo "  built $ROOT/bin/tdd-guard -> copied to ~/.local/bin/tdd-guard ($gver)"
else
  echo "  skipped — install Go, then re-run"
fi

echo
echo "== builder hooks (hooks / format / lint / guard) + the workspace helper =="
if ! ((install)); then
  echo "  would install ~/.local/bin/build-{hooks,format,lint,guard} and workcell-ws (run with --install)"
  report_wrapper_drift
else
  # Copied, not symlinked: a wrapper that runs on every tool call must not resolve through this
  # working tree. None of the five reads $ROOT or sources scripts/lib.sh, so a copy is complete.
  # The price is that editing scripts/hooks/* no longer takes effect until the next --install,
  # which is what report mode above exists to make visible.
  # Agents call the workspace helper by name from whatever project they are working in, so it
  # goes on PATH the same way the hooks do.
  mkdir -p "$HOME/.local/bin"
  semver=$(repo_semver)
  for h in "${WRAPPERS[@]}"; do
    install_owned "$(wrapper_src "$h")" "$HOME/.local/bin/$h" "$semver" \
      || die "could not install $h into ~/.local/bin"
  done
  echo "  installed ~/.local/bin/build-{hooks,format,lint,guard} + workcell-ws as $semver copies"
fi

echo
echo "== optional (language servers + linters; capability-aware, not required) =="
need gopls "go install golang.org/x/tools/gopls@latest" "Go LSP"
need rust-analyzer "rustup component add rust-analyzer" "Rust LSP"
need pyright "$(pick npm:pyright)" "Python type-check + LSP"
need typescript-language-server "$(pick npm:'typescript typescript-language-server')" "TS/JS LSP"
need ruff "$(pick uv:ruff pipx:ruff)" "Python lint / format (build-format + build-lint)"
need shellcheck "$(pick brew:shellcheck apt:shellcheck)" "shell script check (build-lint)"
need goimports "go install golang.org/x/tools/cmd/goimports@latest" "Go import-aware format (build-format)"
need prettier "$(pick npm:prettier)" "JS/TS/JSON/MD format (build-format)"
need eslint "$(pick npm:eslint)" "JS/TS lint (build-lint)"

echo
echo "Next: install the Workcell plugin into your harness(es) via:"
echo "  scripts/bootstrap-plugins.sh"
echo "That is the second and last bootstrap step. See README.md."
