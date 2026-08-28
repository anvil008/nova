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
