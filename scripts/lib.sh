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

# --- copy ownership (#129) ----------------------------------------------------------------
# The copy-side equivalent of the link helpers above, with the same three guarantees: install
# only over absent-or-ours, refuse a foreign destination by name with a non-zero return, and
# on uninstall remove only what we installed while reporting what was left behind. A copy
# cannot carry its provenance the way a link carries a target, so ownership is recorded in a
# receipt under the state dir and re-checked against the destination's current digest: a
# destination the human has since edited is no longer ours to replace or delete.

# workcell_state_dir / workcell_share_dir -> the two $HOME-derived roots the installers share.
# Deriving them from $HOME rather than baking in an absolute path is what keeps the
# throwaway-HOME tests hermetic and lets one installer's uninstall read another's receipt.
workcell_state_dir(){ echo "${WORKCELL_STATE:-$HOME/.local/state/workcell}"; }
workcell_share_dir(){ echo "${WORKCELL_SHARE:-$HOME/.local/share/workcell}"; }

# _sha256 -> hex digest of stdin. shasum ships with macOS, sha256sum with GNU coreutils.
_sha256(){ { if command -v shasum >/dev/null 2>&1; then shasum -a 256; else sha256sum; fi; } | awk '{print $1}'; }
# _sha256s STR -> hex digest of a string, so a name can go into a digest line as a fixed-width
# field instead of as free text that could contain the delimiter.
_sha256s(){ printf '%s' "$1" | _sha256; }

# _digest_path PATH -> the digest of a regular file, or for a directory the digest of its
# sorted per-entry lines, which is stable across machines and inode order. Every entry counts,
# whatever its kind: a digest blind to a link, a directory or a fifo would let an uninstall
# rm -rf something the human added inside a tree we installed. Only the top-level stamp is
# excluded, because it carries this digest and counting it would be self-referential.
# Each line is a kind keyword followed by fixed-width digests of the name and of the content,
# never the raw text: interpolating a name would let a directory called "a link b" and a
# symlink "a" pointing at "b dir" produce the same line, and so hash as the same tree.
_digest_path(){
  if [[ -d $1 ]]; then
    ( cd "$1" && find . ! -path . ! -path ./.workcell-stamp.json | LC_ALL=C sort | while IFS= read -r f; do
        if [[ -L $f ]]; then printf 'link %s %s\n' "$(_sha256s "${f#./}")" "$(_sha256s "$(readlink "$f")")"
        elif [[ -d $f ]]; then printf 'dir %s\n' "$(_sha256s "${f#./}")"
        elif [[ -f $f ]]; then printf 'file %s %s\n' "$(_sha256s "${f#./}")" "$(_sha256 < "$f")"
        else printf 'other %s\n' "$(_sha256s "${f#./}")"
        fi
      done ) | _sha256
  else
    _sha256 < "$1"
  fi
}

# _clean_path PATH -> one canonical spelling of PATH: absolute, single slashes, no trailing
# slash. Ownership has to be a property of the file rather than of how a caller spelled it, or
# the three helpers disagree between two call sites; and a trailing slash would otherwise
# stage the new copy *inside* the destination it is about to replace.
_clean_path(){
  local p=$1
  [[ -n $p ]] || return 1     # an empty destination would otherwise canonicalise to $PWD
  case $p in /*) ;; *) p="$PWD/$p";; esac
  p=$(printf '%s' "$p" | sed -e 's|//*|/|g' -e 's|/*$||')
  printf '%s\n' "${p:-/}"
}

# _json_escape STR -> STR as a JSON string body. Receipts are written with plain shell, never
# jq, so a bootstrap cannot deadlock on the tool it is in the middle of installing.
_json_escape(){ printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

# _receipt_path DST -> the one receipt file for DST: readable basename plus a digest of the
# full path, so two destinations sharing a basename never collide.
_receipt_path(){
  local key base
  key=$(printf '%s' "$1" | _sha256)
  base=$(printf '%s' "$(basename "$1")" | tr -c 'A-Za-z0-9._-' '_')
  printf '%s/receipts/%s-%s.json\n' "$(workcell_state_dir)" "$base" "${key:0:12}"
}

# _json_field FILE KEY -> the recorded value of KEY, from a receipt or a stamp. Both are
# written one field per line in a fixed shape, so reading them back needs no JSON parser.
_json_field(){ sed -n 's/^  "'"$2"'": "\(.*\)",*$/\1/p' "$1" | head -1; }

# owned_copy DST -> true when DST's current digest still matches the one we recorded for it.
# The receipt answers first; a stamped tree that has lost its receipt still describes itself,
# which is what keeps a crash between the two writes from orphaning a destination forever. The
# stamp is only believed at the name it was installed under, so that a human's `cp -R` of one
# of our trees, which carries a perfectly valid stamp with it, is not read as ours to delete.
# A symlink is never an owned copy — that is owned_link's question — and a missing, empty or
# unreadable digest answers "not ours", never "ours": every wrong answer here has to fall on
# the side that keeps the human's file. The digest is computed last so that a foreign entry,
# which has neither receipt nor stamp, is never walked at all.
owned_copy(){
  local dst rcpt stamp want have
  dst=$(_clean_path "$1") || return 1
  [[ -e $dst && ! -L $dst ]] || return 1
  rcpt=$(_receipt_path "$dst"); stamp="$dst/.workcell-stamp.json"
  if [[ -f $rcpt ]]; then want=$(_json_field "$rcpt" digest)
  elif [[ -d $dst && -f $stamp ]] && [[ $(_json_field "$stamp" name) == "$(basename "$dst")" ]]; then
    want=$(_json_field "$stamp" contentDigest)
  else return 1
  fi
  [[ -n $want ]] || return 1
  have=$(_digest_path "$dst")
  [[ $have == "$want" ]]
}

# install_owned SRC DST VERSION [--force]
# Copies a regular file (mode 0755) or a directory tree to DST when DST is absent, is already
# an owned copy, or is one of our own symlinks left by a pre-milestone install — that last one
# is the upgrade path and is silent. A foreign file, directory, or symlink is refused by name
# on stderr, wording as in link_owned; --force additionally replaces a foreign *symlink*,
# never a real file or directory. Staged beside the destination and moved into place, so a
# failed copy or an unwritable receipt never leaves a half-written or unowned destination.
install_owned(){
  local src=$1 dst version=$3 force=${4:-} kind stage digest rcpt now rcpt_failed=
  dst=$(_clean_path "$2") || return 1
  [[ -e $src ]] || { echo "refusing $dst: source $src does not exist" >&2; return 1; }
  rcpt=$(_receipt_path "$dst"); stamp="$dst/.workcell-stamp.json"
  has_stamp=
  if [[ -d $dst && -f $stamp ]] && [[ $(_json_field "$stamp" name) == "$(basename "$dst")" ]]; then
    has_stamp=1
  fi
  if [[ -e $dst || -L $dst ]] && ! owned_copy "$dst" && ! owned_link "$dst" && [[ ! -f $rcpt && -z $has_stamp ]]; then
    if [[ -L $dst && $force == --force ]]; then
      echo "  replacing foreign symlink $dst (--force)"
    elif [[ -L $dst ]]; then
      echo "refusing $dst: symlink to $(readlink "$dst") is not ours (use --force to replace symlinks)" >&2; return 1
    else
      echo "refusing $dst: real file or directory already exists, will not replace it" >&2; return 1
    fi
  fi
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  mkdir -p "$(dirname "$dst")"
  stage="$dst.workcell-stage.$$"; rm -rf "$stage"
  if [[ -d $src ]]; then
    kind="tree"   # quoted: unquoted, shellcheck reads tree/file as the commands of those names
    mkdir -p "$stage"
    cp -R "$src/." "$stage/" || { rm -rf "$stage"; echo "refusing $dst: could not copy $src" >&2; return 1; }
    rm -f "$stage/.workcell-stamp.json"
    digest=$(_digest_path "$stage")
    printf '{\n  "name": "%s",\n  "version": "%s",\n  "builtAt": "%s",\n  "sourceRoot": "%s",\n  "contentDigest": "%s"\n}\n' \
      "$(_json_escape "$(basename "$dst")")" "$(_json_escape "$version")" "$now" \
      "$(_json_escape "$src")" "$digest" > "$stage/.workcell-stamp.json"
  else
    kind="file"
    cp "$src" "$stage" || { rm -f "$stage"; echo "refusing $dst: could not copy $src" >&2; return 1; }
    chmod 0755 "$stage"
    digest=$(_digest_path "$stage")
  fi
  # The receipt is written to its temp file before the destination is touched: a state dir we
  # cannot write to has to fail while the old destination is still intact and still owned,
  # never after it has been replaced by a copy nothing has a receipt for. What is left is two
  # renames, and for a tree the stamp covers even that.
  rcpt=$(_receipt_path "$dst"); mkdir -p "$(dirname "$rcpt")" 2>/dev/null
  printf '{\n  "destination": "%s",\n  "kind": "%s",\n  "digest": "%s",\n  "version": "%s",\n  "source": "%s",\n  "installedAt": "%s"\n}\n' \
    "$(_json_escape "$dst")" "$kind" "$digest" "$(_json_escape "$version")" \
    "$(_json_escape "$src")" "$now" 2>/dev/null > "$rcpt.tmp.$$" || rcpt_failed=1
  if [[ -n $rcpt_failed ]]; then
    rm -rf "$stage"; rm -f "$rcpt.tmp.$$"
    echo "refusing $dst: could not write the receipt $rcpt, leaving the destination as it was" >&2; return 1
  fi
  rm -rf "$dst"
  if ! mv "$stage" "$dst"; then
    rm -rf "$stage"; rm -f "$rcpt.tmp.$$"
    echo "refusing $dst: could not move the staged copy into place" >&2; return 1
  fi
  mv "$rcpt.tmp.$$" "$rcpt" || { echo "refusing $dst: could not record the receipt $rcpt" >&2; return 1; }
}

# uninstall_owned DST -> removes DST and its receipt only when it is still the copy we
# installed; anything else is reported and left exactly as found, matching unlink_owned's
# wording so the link and copy sides can never disagree. A destination the human has edited
# is named as kept, not silently deleted.
uninstall_owned(){
  local dst rcpt
  dst=$(_clean_path "$1") || return 1
  rcpt=$(_receipt_path "$dst")
  if owned_copy "$dst"; then
    rm -rf "$dst"; rm -f "$rcpt"
  elif [[ -e $dst || -L $dst ]]; then
    if [[ -f $rcpt ]]; then echo "  left $dst (locally modified)"
    else echo "  left $dst (not ours)"; fi
  else
    rm -f "$rcpt"
  fi
}

# installed_version DST -> prints the recorded version, empty when there is no receipt.
installed_version(){
  local rcpt; rcpt=$(_receipt_path "$(_clean_path "$1")")
  [[ -f $rcpt ]] || return 0
  _json_field "$rcpt" version
}

# repo_semver -> the release semver from its single source of truth, guard/version.go. The
# wrappers carry no version of their own, so both installers stamp their copies with this one;
# it lives here rather than in either of them so the two can never stamp different numbers.
repo_semver(){ sed -n 's/^const Version = "\(.*\)"$/\1/p' "$ROOT/guard/version.go" 2>/dev/null; }

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

# report_unowned DIR... -> names every entry in each DIR that is neither one of our links nor
# one of our copies, so an uninstall says what it deliberately left behind. Same ownership
# tests as unlink_owned and uninstall_owned, so the three can never disagree.
report_unowned(){
  local d f
  for d in "$@"; do
    for f in "$d"/*; do
      [[ -e $f || -L $f ]] || continue
      owned_link "$f" || owned_copy "$f" || echo "kept unmanaged: $f"
    done
  done
}
