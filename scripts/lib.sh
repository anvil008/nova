#!/usr/bin/env bash
# Shared helpers for the installers. Sourced, not executed; bash 3.2 syntax only
# (stock macOS), so nothing that needs bash 4 or GNU coreutils.
# Callers set ROOT (this repository) before sourcing.

die(){ echo "error: $*" >&2; exit 1; }

# owned_link DST -> true when DST is a symlink whose literal target is inside $ROOT.
# Compared textually, without canonicalising: every link we create carries an absolute
# $ROOT-based target, so this is exact and portable.
owned_link(){ [[ -L $1 ]] && case "$(readlink "$1")" in "$ROOT"/*) return 0;; esac; return 1; }

# link_owned SRC DST [--force]
# Creates DST -> SRC only when DST is absent or already one of our links. A foreign
# file, directory, or symlink is refused with a message; --force additionally
# replaces a foreign *symlink*, never a real file or directory.
link_owned(){
  local src=$1 dst=$2 force=${3:-}
  if [[ -e $dst || -L $dst ]] && ! owned_link "$dst"; then
    if [[ -L $dst && $force == --force ]]; then
      echo "  replacing foreign symlink $dst (--force)"
    elif [[ -L $dst ]]; then
      echo "refusing $dst: symlink to $(readlink "$dst") is not ours (use --force to replace symlinks)" >&2; return 1
    else
      echo "refusing $dst: real file or directory already exists, will not replace it" >&2; return 1
    fi
  fi
  mkdir -p "$(dirname "$dst")"
  ln -sfn "$src" "$dst"
}

# unlink_owned DST -> removes DST only if it is one of our links; reports anything else left.
unlink_owned(){
  local dst=$1
  if owned_link "$dst"; then rm -f "$dst"
  elif [[ -e $dst || -L $dst ]]; then echo "  left $dst (not ours)"; fi
}

# check_frontmatter FILE -> the file starts with a '---' block that closes and carries name + description.
check_frontmatter(){
  local f=$1 fm
  [[ $(head -n1 "$f") == '---' ]] || { echo "$f: missing frontmatter" >&2; return 1; }
  fm=$(sed -n '2,/^---$/p' "$f")
  grep -qx -- '---' <<<"$fm" || { echo "$f: frontmatter never closes" >&2; return 1; }
  grep -qE '^name:[[:space:]]*[^[:space:]]' <<<"$fm" || { echo "$f: frontmatter lacks name" >&2; return 1; }
  grep -qE '^description:[[:space:]]*[^[:space:]]' <<<"$fm" || { echo "$f: frontmatter lacks description" >&2; return 1; }
}

# run_install CMD -> runs an install command in the foreground so any sudo prompt is
# visible; when the command needs sudo and there is no terminal, skip it instead.
run_install(){
  local cmd=$1
  if [[ $cmd == sudo* ]] && ! [[ -t 0 && -t 2 ]]; then
    echo "         skipped (needs sudo, no terminal): $cmd"; return 1
  fi
  eval "$cmd"
}

# git_exclude_add PATH... -> local-ignores each PATH via the repository's info/exclude,
# so the entry never shows up in a scored patch or a commit. --git-path resolves to the
# common dir, so a worktree (.git is a file) or a jj workspace gets the shared
# info/exclude, not a dead path. Returns non-zero outside a repository.
git_exclude_add(){
  local ex p
  ex=$(git rev-parse --git-path info/exclude 2>/dev/null) || return 1
  mkdir -p "$(dirname "$ex")"
  for p in "$@"; do
    grep -qxF "$p" "$ex" 2>/dev/null && continue
    echo "$p" >> "$ex"; echo "  local-ignored $p via $ex (invisible to git diff)"
  done
}

# git_exclude_remove PATH... -> the inverse: drops each PATH from the repository's info/exclude
# and leaves every other line, so an uninstall gives back exactly the file it found. Rewritten
# through a temp file, since in-place editing is not portable. Non-zero outside a repository.
git_exclude_remove(){
  local ex tmp p
  ex=$(git rev-parse --git-path info/exclude 2>/dev/null) || return 1
  [[ -f $ex ]] || return 0
  for p in "$@"; do
    grep -qxF "$p" "$ex" || continue
    tmp="$ex.workcell.$$"
    grep -vxF "$p" "$ex" > "$tmp" || true
    cat "$tmp" > "$ex"; rm -f "$tmp"
    echo "  un-ignored $p in $ex"
  done
}

# report_unowned DIR... -> names every entry in each DIR that is not one of our links,
# so an uninstall says what it deliberately left behind. Same ownership test as
# unlink_owned, so the two can never disagree.
report_unowned(){
  local d f
  for d in "$@"; do
    for f in "$d"/*; do
      [[ -e $f || -L $f ]] || continue
      owned_link "$f" || echo "kept unmanaged: $f"
    done
  done
}
