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

echo "== core (required) =="
need go      "$(pick brew:go apt:golang-go)"                             "Go toolchain — builds tdd-guard" 1
need git     "$(pick brew:git apt:git)"                                  "version control" 1
need python3 "$(pick brew:python3 apt:python3)"                          "skill helpers (render / waves / docs-check)" 1
need jq      "$(pick brew:jq apt:jq)"                                    "JSON parser — hooks rely on it" 1
need ast-grep "$(pick npm:@ast-grep/cli cargo:ast-grep brew:ast-grep)"  "structural search + tdd-guard arch-check"
need jj      "$(pick brew:jj cargo:jj-cli)"                              "Jujutsu VCS — the builder's jj skill"
need gh      "$(pick brew:gh apt:gh)"                                    "GitHub CLI — planner/build create issues + milestones"

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
  echo "  would build ~/.local/bin/tdd-guard + build-hooks (run with --install)"
elif have go; then
  # The binary is a build artifact, so it is built into the repo's gitignored
  # bin/ and linked — same rule as everything else: the repo is the source.
  mkdir -p "$ROOT/bin" "$HOME/.local/bin"
  ( cd "$ROOT" && go build -buildvcs=false -o "$ROOT/bin/tdd-guard" ./cmd/tdd-guard ) || die "go build ./cmd/tdd-guard failed"
  link_owned "$ROOT/bin/tdd-guard" "$HOME/.local/bin/tdd-guard" || die "could not link tdd-guard into ~/.local/bin"
  echo "  built $ROOT/bin/tdd-guard -> ~/.local/bin/tdd-guard"
else
  echo "  skipped — install Go, then re-run"
fi

echo
echo "== builder hooks (hooks / format / lint / guard) + the workspace helper =="
if ! ((install)); then
  echo "  would link ~/.local/bin/build-{hooks,format,lint,guard} and workcell-ws (run with --install)"
else
  # Symlinked, not copied: editing scripts/hooks/* takes effect immediately.
  mkdir -p "$HOME/.local/bin"
  for h in build-hooks build-format build-lint build-guard; do
    link_owned "$ROOT/scripts/hooks/$h" "$HOME/.local/bin/$h" || die "could not link $h into ~/.local/bin"
  done
  # Agents call the workspace helper by name from whatever project they are working in, so it has
  # to be on PATH the same way the hooks are.
  link_owned "$ROOT/scripts/workcell-ws" "$HOME/.local/bin/workcell-ws" \
    || die "could not link workcell-ws into ~/.local/bin"
  echo "  linked ~/.local/bin/build-{hooks,format,lint,guard} -> scripts/hooks/, workcell-ws -> scripts/"
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
