#!/usr/bin/env bash
# Report, and optionally install, the external verifier tools the Coding Fleet
# toolchain checks call. Run this yourself: the codingfleet installer never
# installs software, and a missing verifier makes its check unverified rather
# than passed.
#
#   scripts/bootstrap-tools.sh           # report what is present
#   scripts/bootstrap-tools.sh --install # install what is missing
set -euo pipefail

install=0
[[ ${1:-} == "--install" ]] && install=1

# tool|what it verifies|install command
tools=(
  "ast-grep|structural search and deterministic multi-site AST rewrite|cargo install ast-grep --locked"
  "golangci-lint|aggregate Go linters|go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@latest"
  "ruff|Python lint and format check|uv tool install ruff"
  "pyright|Python type checking (ships pyright-langserver LSP)|npm install -g pyright"
  "tsc|TypeScript type checking|npm install -g typescript"
  "actionlint|GitHub Actions workflow checking|go install github.com/rhysd/actionlint/cmd/actionlint@latest"
  "shellcheck|shell script checking|sudo apt-get install -y shellcheck"
  # Language servers: symbol resolution (go-to-definition, find-references) is
  # ground truth the model cannot hallucinate. See the harness note below for
  # how each harness consumes these.
  "gopls|Go language server|go install golang.org/x/tools/gopls@latest"
  "rust-analyzer|Rust language server|rustup component add rust-analyzer"
  "typescript-language-server|TypeScript/JS language server|npm install -g typescript-language-server"
)

missing=0
for entry in "${tools[@]}"; do
  IFS='|' read -r tool purpose command <<<"$entry"
  if location=$(command -v "$tool" 2>/dev/null); then
    printf 'present  %-16s %s\n' "$tool" "$location"
    continue
  fi
  missing=$((missing + 1))
  printf 'missing  %-16s %s\n' "$tool" "$purpose"
  if ((install)); then
    printf '         installing: %s\n' "$command"
    eval "$command"
  else
    printf '         install with: %s\n' "$command"
  fi
done

if ((missing == 0)); then
  echo "all verifier tools are present"
elif ((install == 0)); then
  echo "$missing verifier tool(s) missing; re-run with --install or install them yourself"
  echo "until then, report those checks as unverified, never as passed"
fi

cat <<'NOTE'

language-server enablement is per harness (installing the binaries above is
necessary but not sufficient):
  - Claude Code: LSP is plugin-driven and opt-in. Install the per-language
    plugin so the agent (and its subagents) use it automatically:
      claude plugin install gopls-lsp pyright-lsp rust-analyzer-lsp typescript-lsp
  - Antigravity (agy): code intelligence is built into the runtime; nothing to
    enable per run.
  - Codex: no built-in LSP yet. It navigates by text search; rely on the
    verifier type-checkers (pyright/tsc/go vet/clippy) for symbol-level ground
    truth and on ast-grep for structural edits.
NOTE
