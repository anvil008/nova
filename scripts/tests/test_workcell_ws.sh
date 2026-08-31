#!/usr/bin/env bash
# Tests for scripts/workcell-ws — the one isolated-workspace helper.
# Every case builds throwaway repositories under mktemp: a colocated jj repo with a local
# origin/main (so trunk() resolves without a network) and a git-only repo with no remote at all,
# so both default-branch paths are exercised. git and jj configuration is redirected at throwaway
# files, so the developer's real config is never read or written. The jj half skips when jj is
# absent; the git half always runs.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
WS="$ROOT/scripts/workcell-ws"
TMP="$(mktemp -d)"; trap 'rm -rf -- "$TMP"' EXIT
pass=0; fail=0
ok(){ printf 'ok   %s\n' "$1"; pass=$((pass+1)); }
no(){ printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
check(){ if "$@"; then ok "$name"; else no "$name"; fi; }
nope(){ ! "$@"; }   # check nope CMD... -> the command must fail

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_CONFIG_NOSYSTEM=1
printf '[user]\nname = "t"\nemail = "t@example.invalid"\n' > "$TMP/jj.toml"
export JJ_CONFIG="$TMP/jj.toml"

# --- throwaway repositories ----------------------------------------------------------------------
seed(){  # seed DIR -> a git repo with one commit on main and a usable identity
  mkdir -p "$1"
  git -c init.defaultBranch=main init -q "$1"
  git -C "$1" config user.email t@example.invalid
  git -C "$1" config user.name t
  printf 'seed\n' > "$1/seed.txt"
  git -C "$1" add -A
  git -C "$1" -c commit.gpgsign=false commit -qm init
}
mkjj(){  # mkjj DIR -> a colocated jj repo whose trunk() resolves through a local origin/main
  seed "$1"
  git -C "$1" remote add origin "$TMP/remotes/$(basename "$1").git"
  git -C "$1" update-ref refs/remotes/origin/main HEAD
  git -C "$1" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
  jj git init --colocate "$1" >/dev/null 2>&1
}
# merge_in VCS REPO REF -> put REF strictly behind the default branch, the way a merged pull
# request leaves it. The jj side moves the remote-tracking ref trunk() resolves through.
merge_in(){
  local vcs=$1 repo=$2 ref=$3 tip new
  if [[ $vcs == jj ]]; then
    tip=$(jj -R "$repo" --ignore-working-copy log --no-graph -r "$ref" -T 'commit_id') || return 1
    new=$(git -C "$repo" commit-tree "$tip^{tree}" -p "$tip" -m "merge $ref") || return 1
    git -C "$repo" update-ref refs/remotes/origin/main "$new" || return 1
    jj -R "$repo" --ignore-working-copy git import >/dev/null 2>&1
  else
    git -C "$repo" merge --no-ff --no-edit -q "$ref"
  fi
}

mkjj_noremote(){ seed "$1"; jj git init --colocate "$1" >/dev/null 2>&1; }
# orphan VCS REPO KEY -> take the registration away but leave the directory: the shape a crashed
# agent leaves, and the only honest way to build a stale-dir (a bare .jj/.git directory is a
# different repository, not a workspace of ours).
orphan(){
  local vcs=$1 repo=$2 key=$3
  if [[ $vcs == jj ]]; then jj -R "$repo" --ignore-working-copy workspace forget "$key" >/dev/null 2>&1
  else rm -rf "$repo/.git/worktrees/$(basename "$repo")-$key"; git -C "$repo" worktree prune
  fi
}
siblings(){ find "$(dirname "$1")" -mindepth 1 -maxdepth 1 -name "$(basename "$1")*" | sort; }
state_of(){ "$WS" list --repo "$1" | awk -v k="$2" '$1 == k { print $3 }'; }
is_state(){ [[ $(state_of "$1" "$2") == "$3" ]]; }
listed(){ "$WS" list --repo "$1" | grep -q "^$2 "; }
has_ref(){  # has_ref REPO NAME -> the bookmark / branch still exists
  if [[ -d $1/.jj ]]; then
    jj -R "$1" --ignore-working-copy bookmark list --all-remotes \
      -T 'if(remote, "", name ++ "\n")' 2>/dev/null | grep -qxF "$2"
  else
    git -C "$1" show-ref --verify --quiet "refs/heads/$2"
  fi
}
saw(){ grep -qE "$2" "$TMP/$1"; }   # saw FILE ERE -> the captured output matched
# oplog VCS REPO -> the number of recorded operations, so a read-only run can be proved read-only
oplog(){ if [[ $1 == jj ]]; then jj -R "$2" --ignore-working-copy op log --no-graph -T '"x\n"'
         else git -C "$2" reflog --all; fi | wc -l; }

# --- refusals that need no repository -------------------------------------------------------------
mkdir -p "$TMP/remotes" "$TMP/bare"
name="workcell-ws parses as bash";               check bash -n "$WS"
name="refuses to run outside a repository";      check nope "$WS" list --repo "$TMP/bare"
name="refuses an unknown subcommand";            check nope "$WS" frobnicate
name="refuses --apply on anything but sweep";    check nope "$WS" list --apply
name="refuses --base on anything but add";       check nope "$WS" forget x --base main
name="--help names every subcommand"
check bash -c '"$1" --help | grep -qE "add .*<key>" && "$1" --help | grep -q "sweep"' _ "$WS"

# --- one suite, run against both version-control systems ------------------------------------------
suite(){
  local vcs=$1 repo=$2 tag="$1:" before after log_before log_after key leak rc out

  name="$tag add creates the sibling workspace, populated"
  "$WS" add feat-one --repo "$repo" > "$TMP/$vcs-add.out" 2>&1
  check test -e "$repo-feat-one/seed.txt"
  name="$tag add names the created path and the one rule"
  check bash -c 'grep -qF "$2" "$1" && grep -q "work only inside" "$1"' _ "$TMP/$vcs-add.out" "$repo-feat-one"
  name="$tag add creates the bookmark/branch named after the key"
  check has_ref "$repo" feat-one
  name="$tag the workspace is a $vcs working copy, not the other kind"
  if [[ $vcs == jj ]]; then check test -e "$repo-feat-one/.jj"
  else check bash -c '[ -e "$1/.git" ] && [ ! -e "$1/.jj" ]' _ "$repo-feat-one"; fi
  name="$tag add refuses a key that is not [a-z0-9][a-z0-9-]*"
  check nope "$WS" add Feat_Two --repo "$repo"
  name="$tag add refuses an existing directory at the target path"
  check nope "$WS" add feat-one --repo "$repo"

  name="$tag list reports the primary working copy as default/active"
  check is_state "$repo" default active
  name="$tag list reports a fresh workspace as active, never as merged"
  check is_state "$repo" feat-one active
  name="$tag subcommands work from inside a workspace, with no --repo"
  check bash -c 'cd "$2-feat-one" && "$1" list | grep -q "^feat-one " && "$1" add feat-two >/dev/null' _ "$WS" "$repo"

  name="$tag forget removes the working copy"
  "$WS" forget feat-two --repo "$repo" >/dev/null 2>&1
  check nope test -d "$repo-feat-two"
  name="$tag forget deregisters the workspace"
  check nope listed "$repo" feat-two
  name="$tag forget keeps the bookmark/branch and its commits"
  check has_ref "$repo" feat-two
  name="$tag forget refuses the primary working copy"
  check nope "$WS" forget default --repo "$repo"
  name="$tag forget refuses a key it has no workspace for"
  check nope "$WS" forget never-existed --repo "$repo"

  # --- the leak shapes a crashed agent leaves behind -----------------------------------------------
  "$WS" add stale-one --repo "$repo" >/dev/null 2>&1   # loses its directory     -> stale-reg
  "$WS" add live-one  --repo "$repo" >/dev/null 2>&1   # unmerged work           -> active
  "$WS" add gone-one  --repo "$repo" >/dev/null 2>&1   # merged into the default -> merged
  for key in live-one gone-one; do
    printf '%s\n' "$key" > "$repo-$key/$key.txt"
    if [[ $vcs == jj ]]; then (cd "$repo-$key" && jj describe -m "$key work" >/dev/null 2>&1)
    else git -C "$repo-$key" add -A && git -C "$repo-$key" -c commit.gpgsign=false commit -qm "$key work"
    fi
  done
  merge_in "$vcs" "$repo" gone-one
  "$WS" add ghost-one --repo "$repo" >/dev/null 2>&1   # a real workspace whose registration is lost
  printf 'leftover\n' > "$repo-ghost-one/leftover.txt"
  orphan "$vcs" "$repo" ghost-one
  # After the orphan step, because git's prune deregisters every worktree whose directory is gone.
  rm -rf "$repo-stale-one"                             # the directory an agent removed by hand
  # An INDEPENDENT repository that merely collides with the naming convention. Nothing here may
  # touch it, however much it looks like one of ours from the outside.
  seed "$repo-other-one"
  [[ $vcs == jj ]] && jj git init --colocate "$repo-other-one" >/dev/null 2>&1

  name="$tag list detects stale-reg (registered, directory gone)"
  check is_state "$repo" stale-one stale-reg
  name="$tag list detects stale-dir (directory there, nothing registered it)"
  check is_state "$repo" ghost-one stale-dir
  name="$tag list calls an independent repo that collides on the name foreign"
  check is_state "$repo" other-one foreign
  name="$tag list reports a merged workspace as merged"
  check is_state "$repo" gone-one merged
  name="$tag list reports an unmerged workspace as active"
  check is_state "$repo" live-one active

  # --- sweep is read-only without --apply ----------------------------------------------------------
  before=$(siblings "$repo"); log_before=$(oplog "$vcs" "$repo")
  "$WS" sweep --repo "$repo" > "$TMP/$vcs-sweep.out" 2>&1
  after=$(siblings "$repo"); log_after=$(oplog "$vcs" "$repo")

  for leak in 'stale-reg +stale-one' 'stale-dir +ghost-one' 'merged +gone-one' 'ref +gone-one'; do
    name="$tag sweep without --apply reports: $leak"; check saw "$vcs-sweep.out" "$leak"
  done
  name="$tag sweep without --apply never names an unmerged workspace"
  check nope saw "$vcs-sweep.out" live-one
  name="$tag sweep reports a colliding foreign repo as a note, never as a leak"
  check saw "$vcs-sweep.out" 'note +foreign +other-one.*never swept'
  name="$tag sweep without --apply says how to act on it"
  check saw "$vcs-sweep.out" 're-run with --apply'
  name="$tag sweep without --apply leaves every directory in place"
  check test "$before" = "$after"
  name="$tag sweep without --apply writes nothing to the operation log"
  check test "$log_before" = "$log_after"

  # --- sweep --apply removes exactly the leaks -----------------------------------------------------
  "$WS" sweep --apply --repo "$repo" > "$TMP/$vcs-apply.out" 2>&1; rc=$?
  name="$tag sweep --apply exits zero";                      check test "$rc" -eq 0
  name="$tag sweep --apply removes the merged workspace";    check nope test -d "$repo-gone-one"
  name="$tag sweep --apply deregisters the stale registration"
  check nope listed "$repo" stale-one
  # DEFECT 1/2: an unvouchable directory and a foreign repository both survive a plain --apply.
  name="$tag sweep --apply keeps a stale directory nothing can vouch for"
  check test -e "$repo-ghost-one/leftover.txt"
  name="$tag sweep --apply says why it kept it, and how to override"
  check saw "$vcs-apply.out" 'kept +stale-dir +ghost-one.*--force overrides'
  name="$tag sweep --apply never deletes a colliding foreign repository"
  check test -e "$repo-other-one/seed.txt"
  name="$tag sweep --apply --force does reclaim the stale directory"
  "$WS" sweep --apply --force --repo "$repo" >/dev/null 2>&1
  check nope test -d "$repo-ghost-one"
  name="$tag sweep --apply --force still never deletes a foreign repository"
  check test -e "$repo-other-one/seed.txt"
  name="$tag sweep --apply keeps the unmerged workspace";    check test -d "$repo-live-one"
  name="$tag sweep --apply deletes the merged bookmark/branch"
  check nope has_ref "$repo" gone-one
  name="$tag sweep --apply never deletes an unmerged bookmark/branch"
  check has_ref "$repo" live-one
  name="$tag sweep --apply never deletes the default branch"; check has_ref "$repo" main
  name="$tag sweep --apply leaves the repository itself alone"
  check test -e "$repo/seed.txt"
  name="$tag a second sweep has nothing left to do"
  check bash -c '"$1" sweep --repo "$2" | grep -q "nothing to sweep"' _ "$WS" "$repo"

  # --- DEFECT 1: uncommitted work is never destroyed ----------------------------------------------
  "$WS" add dirty-one --repo "$repo" >/dev/null 2>&1
  printf 'PRECIOUS\n' > "$repo-dirty-one/precious.txt"   # untracked, never committed anywhere
  "$WS" forget dirty-one --repo "$repo" > "$TMP/$vcs-dirty.out" 2>&1; rc=$?
  if [[ $vcs == jj ]]; then
    # jj's working copy IS a commit: forgetting snapshots it first, so the directory can go.
    name="$tag forget succeeds on a dirty jj workspace"; check test "$rc" -eq 0
    name="$tag ... having snapshotted the untracked file into the bookmark, losing nothing"
    check bash -c 'jj -R "$1" --ignore-working-copy file show -r dirty-one "$1/precious.txt" \
                     2>/dev/null | grep -q PRECIOUS' _ "$repo"
  else
    # git's is not, so the only safe answer is to refuse and say what would have been lost.
    name="$tag forget refuses a dirty git worktree"; check test "$rc" -ne 0
    name="$tag ... naming the uncommitted path"; check saw "$vcs-dirty.out" 'precious.txt'
    name="$tag ... and the file is still on disk"; check test -e "$repo-dirty-one/precious.txt"
    name="$tag forget --force removes it once the caller says so"
    "$WS" forget dirty-one --force --repo "$repo" >/dev/null 2>&1
    check nope test -d "$repo-dirty-one"
  fi

  # --- DEFECT 4: a forget that would strand the caller's shell ------------------------------------
  "$WS" add cwd-one --repo "$repo" >/dev/null 2>&1
  out=$(cd "$repo-cwd-one" && "$WS" forget cwd-one 2>&1); rc=$?
  name="$tag forget refuses while the caller's shell is inside the workspace"
  check test "$rc" -ne 0
  name="$tag ... telling the caller to cd out first"
  check bash -c 'printf "%s" "$1" | grep -q "cd out of the workspace first"' _ "$out"
  name="$tag ... and the workspace survives"; check test -d "$repo-cwd-one"
  name="$tag ... and not even --force will strand a live shell"
  check bash -c 'cd "$2-cwd-one" && ! "$1" forget cwd-one --force >/dev/null 2>&1' _ "$WS" "$repo"
  name="$tag forget works again from outside the workspace"
  check bash -c '"$1" forget cwd-one --repo "$2" >/dev/null' _ "$WS" "$repo"

  # --- REGRESSION: a merged ref whose workspace was kept is not the sweep's to delete -------------
  "$WS" add keptref-one --repo "$repo" >/dev/null 2>&1
  printf 'work\n' > "$repo-keptref-one/work.txt"
  if [[ $vcs == jj ]]; then (cd "$repo-keptref-one" && jj describe -m 'keptref work' >/dev/null 2>&1)
  else git -C "$repo-keptref-one" add -A
       git -C "$repo-keptref-one" -c commit.gpgsign=false commit -qm 'keptref work'
  fi
  merge_in "$vcs" "$repo" keptref-one
  # Make it unremovable without --force. git: leave the tree dirty. jj: orphan it, since a jj
  # workspace that can still be snapshotted is never kept, so stale-dir is the shape that gets here.
  if [[ $vcs == jj ]]; then orphan "$vcs" "$repo" keptref-one
  else printf 'UNCOMMITTED\n' > "$repo-keptref-one/dirty.txt"
  fi
  "$WS" sweep --apply --repo "$repo" > "$TMP/$vcs-keptref.out" 2>&1; rc=$?
  name="$tag sweep --apply exits zero when it keeps a workspace whose ref is merged"
  check test "$rc" -eq 0
  name="$tag ... noting the ref it skipped rather than failing on it"
  check saw "$vcs-keptref.out" 'kept +ref +keptref-one +workspace kept, remove it first'
  name="$tag ... with no FAILED line anywhere"
  check nope saw "$vcs-keptref.out" FAILED
  name="$tag ... the merged ref survives";     check has_ref "$repo" keptref-one
  name="$tag ... and so does its workspace";   check test -d "$repo-keptref-one"

  "$WS" sweep --apply --force --repo "$repo" > "$TMP/$vcs-keptref2.out" 2>&1; rc=$?
  name="$tag sweep --apply --force exits zero and clears both"; check test "$rc" -eq 0
  name="$tag ... the workspace is gone";       check nope test -d "$repo-keptref-one"
  name="$tag ... and the merged ref with it";  check nope has_ref "$repo" keptref-one
}

mkdir -p "$TMP/remotes"
mkjj "$TMP/jjproj"
if [[ -d $TMP/jjproj/.jj ]]; then
  suite jj "$TMP/jjproj"
else
  printf 'skip jj cases (no jj CLI)\n'
fi

# --- DEFECT 3: a jj repo with no remote for trunk() to resolve through -----------------------------
if command -v jj >/dev/null 2>&1; then
  mkjj_noremote "$TMP/jjsolo"
  name="jj-solo: trunk() really does degrade to the root commit here"
  check bash -c '[ -z "$(jj -R "$1" --ignore-working-copy log --no-graph \
                          -r "trunk() ~ root()" -T "\"x\"" 2>/dev/null)" ]' _ "$TMP/jjsolo"
  "$WS" add feat --repo "$TMP/jjsolo" > "$TMP/solo-add.out" 2>&1
  name="jj-solo: add falls back to the local default bookmark instead of root()"
  check saw solo-add.out 'base bookmarks\(exact:"main"\)'
  name="jj-solo: the workspace is populated, not an empty tree"
  check test -e "$TMP/jjsolo-feat/seed.txt"
  jj -R "$TMP/jjsolo" --ignore-working-copy bookmark delete main >/dev/null 2>&1
  name="jj-solo: with no default bookmark at all, add refuses plainly rather than guessing"
  check nope "$WS" add feat-two --repo "$TMP/jjsolo"
fi

seed "$TMP/gitproj"
suite git "$TMP/gitproj"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
