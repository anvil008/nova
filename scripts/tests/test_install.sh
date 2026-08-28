#!/usr/bin/env bash
# Tests for the installers (install-harness.sh / project-bootstrap.sh / bootstrap-tools.sh).
# Every case runs against a throwaway HOME under mktemp; the real ~/.claude, ~/.codex,
# ~/.gemini and ~/.local/bin are never read or written.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
INSTALL="$ROOT/scripts/install-harness.sh"
BOOTSTRAP="$ROOT/scripts/project-bootstrap.sh"
REAL_HOME=$HOME
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ printf 'ok   %s\n' "$1"; pass=$((pass+1)); }
no(){ printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
# fresh_home NAME -> creates $TMP/NAME with the harness dirs the installers look for, exports HOME
fresh_home(){ HOME="$TMP/$1"; export HOME
  mkdir -p "$HOME/.claude" "$HOME/.codex" "$HOME/.gemini/config" "$HOME/.local/bin"
  [[ $HOME != "$REAL_HOME" ]] || { echo "refusing to test against the real HOME" >&2; exit 99; }; }
# links_into_root DIR -> prints every symlink under DIR whose literal target is inside $ROOT
links_into_root(){ local l; find "$1" -type l | while read -r l; do
  case "$(readlink "$l")" in "$ROOT"/*) echo "$l";; esac; done; }
# git_repo DIR -> initialised repo with one commit, so worktrees can be added
git_repo(){ mkdir -p "$1" && ( cd "$1" && git init -q && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init ); }
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null

# --- install-refuses-foreign-target --------------------------------------------------------------
fresh_home foreign
mkdir -p "$HOME/.claude/skills/jj" "$HOME/.claude/agents"
echo "user's own jj skill" > "$HOME/.claude/skills/jj/SKILL.md"
echo "user's own builder" > "$HOME/.claude/agents/builder.md"
cp -R "$HOME/.claude" "$TMP/foreign-before"
out=$("$INSTALL" --install --harness claude 2>&1); rc=$?
[[ $rc -ne 0 ]] && ok "install exits non-zero on foreign targets" || no "install exits non-zero on foreign targets (rc=$rc)"
grep -q "skills/jj" <<<"$out" && grep -q "agents/builder.md" <<<"$out" && ok "refusal names both foreign targets" || no "refusal names both foreign targets: $out"
grep -q "done\." <<<"$out" && no "refused install must not print done." || ok "refused install does not print done."
[[ ! -L $HOME/.claude/skills/jj && ! -L $HOME/.claude/agents/builder.md ]] \
  && cmp -s "$TMP/foreign-before/skills/jj/SKILL.md" "$HOME/.claude/skills/jj/SKILL.md" \
  && cmp -s "$TMP/foreign-before/agents/builder.md" "$HOME/.claude/agents/builder.md" \
  && ok "foreign targets left byte-identical" || no "foreign targets left byte-identical"

# --- uninstall-removes-only-owned-links ----------------------------------------------------------
fresh_home owned
mkdir -p "$TMP/elsewhere"; echo foreign > "$TMP/elsewhere/research.md"
out=$("$INSTALL" --install 2>&1); rc=$?
[[ $rc -eq 0 ]] && grep -q "done\." <<<"$out" && ok "install into fresh HOME succeeds" || no "install into fresh HOME succeeds (rc=$rc): $out"
[[ -L $HOME/.claude/agents/builder.md && -L $HOME/.codex/skills/jj && -L $HOME/.gemini/config/skills/jj && -L $HOME/.codex/builder.config.toml ]] \
  && ok "install links agents, skills and codex toml" || no "install links agents, skills and codex toml"
git_repo "$TMP/owned-proj"
"$BOOTSTRAP" --install "$TMP/owned-proj" >/dev/null 2>&1
ln -sfn "$ROOT/bin/tdd-guard" "$HOME/.local/bin/tdd-guard"; ln -sfn "$ROOT/scripts/hooks/build-hooks" "$HOME/.local/bin/build-hooks"
ln -sfn "$TMP/elsewhere/research.md" "$HOME/.claude/agents/research.md"      # foreign link, same name as ours
out=$("$INSTALL" --uninstall 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "uninstall exits zero" || no "uninstall exits zero (rc=$rc): $out"
left=$(links_into_root "$HOME")
[[ -z $left ]] && ok "uninstall removes every link into ROOT (incl. ~/.local/bin/build-* and tdd-guard)" || no "links into ROOT left behind: $left"
[[ -L $HOME/.claude/agents/research.md && $(readlink "$HOME/.claude/agents/research.md") == "$TMP/elsewhere/research.md" ]] \
  && ok "uninstall leaves the foreign research.md link" || no "uninstall leaves the foreign research.md link"
grep -q "research.md" <<<"$out" && ok "uninstall reports what it left behind" || no "uninstall reports what it left behind: $out"

# --- hooks-are-symlinks-after-project-bootstrap --------------------------------------------------
fresh_home hooks
git_repo "$TMP/hooks-proj"
out=$("$BOOTSTRAP" --with-hooks "$TMP/hooks-proj" 2>&1); rc=$?
[[ $rc -eq 0 ]] && ok "project-bootstrap --with-hooks exits zero" || no "project-bootstrap --with-hooks exits zero (rc=$rc): $out"
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
synok=1; for f in "$ROOT"/scripts/*.sh "$ROOT"/scripts/tests/*.sh; do bash -n "$f" || synok=0; done
[[ $synok -eq 1 ]] && ok "bash -n passes for every script" || no "bash -n passes for every script"
grep -q 'set -euo pipefail' "$INSTALL" && grep -q 'set -euo pipefail' "$BOOTSTRAP" && grep -q 'set -euo pipefail' "$ROOT/scripts/bootstrap-tools.sh" \
  && ok "installers use set -euo pipefail" || no "installers use set -euo pipefail"
grep -q 'install -m' "$BOOTSTRAP" && no "project-bootstrap still copies hooks with install -m" || ok "project-bootstrap has no install -m copy"

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
mkdir -p "$HOME/.claude/agents" "$HOME/.claude/skills"
ln -sfn "$TMP/elsewhere/research.md" "$HOME/.claude/agents/builder.md"
mkdir -p "$HOME/.claude/skills/jj"; echo real > "$HOME/.claude/skills/jj/SKILL.md"
out=$("$INSTALL" --install --harness claude --force 2>&1); rc=$?
[[ -L $HOME/.claude/agents/builder.md && $(readlink "$HOME/.claude/agents/builder.md") == "$ROOT/agents/claude/builder.md" ]] \
  && ok "--force replaces a foreign symlink" || no "--force replaces a foreign symlink"
[[ $rc -ne 0 && ! -L $HOME/.claude/skills/jj && -f $HOME/.claude/skills/jj/SKILL.md ]] \
  && ok "--force still refuses a real directory" || no "--force still refuses a real directory (rc=$rc): $out"

# --- frontmatter validated before any harness is touched -----------------------------------------
fresh_home fm
BROKEN="$TMP/broken-root"; mkdir -p "$BROKEN/scripts" "$BROKEN/skills"
cp -R "$ROOT/agents" "$BROKEN/agents"; cp -R "$ROOT/skills/jj" "$BROKEN/skills/jj"; cp "$ROOT"/scripts/*.sh "$BROKEN/scripts/"
printf 'no frontmatter here\n' > "$BROKEN/agents/codex/docs.md"
out=$("$BROKEN/scripts/install-harness.sh" --install 2>&1); rc=$?
[[ $rc -ne 0 ]] && grep -q "agents/codex/docs.md" <<<"$out" && ok "invalid frontmatter fails and is named" || no "invalid frontmatter fails and is named (rc=$rc): $out"
[[ -z $(find "$HOME/.claude" "$HOME/.codex" "$HOME/.gemini" -type l) ]] && ok "invalid frontmatter: no harness touched" || no "invalid frontmatter: no harness touched"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
