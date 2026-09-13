#!/usr/bin/env python3
"""Claude WorktreeCreate/WorktreeRemove adapter for Nova workspace placement."""
import json
from pathlib import Path
import re
import subprocess
import sys


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f'Command failed: {args[0]}')
    return result.stdout.strip()


def primary(cwd):
    for parent in (cwd, *cwd.parents):
        repo = parent / '.jj/repo'
        if repo.exists():
            shared = (repo.parent / repo.read_text().strip()).resolve() if repo.is_file() else repo.resolve()
            root = shared.parent.parent
            if not (root / '.jj').is_dir():
                raise ValueError('Cannot resolve the primary JJ checkout')
            return root, 'jj'
        if (parent / '.git').exists():
            common = Path(run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], parent)).resolve()
            root = common.parent
            if common.name != '.git':
                raise ValueError('A primary non-bare checkout with .git is required')
            # A Git worktree can still belong to a colocated JJ repository.
            return root, 'jj' if (root / '.jj/repo').exists() else 'git'
    raise ValueError('No JJ or Git repository found')


def create(payload):
    name = payload.get('name', '')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', name):
        raise ValueError('Workspace name must be a single alphanumeric/dash/underscore slug')
    root, vcs = primary(Path(payload['cwd']).resolve())
    container = root / '.workspaces'
    if container.is_symlink():
        raise ValueError('Refusing a symlinked .workspaces directory')
    destination = container / name
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Workspace already exists: {destination}')
    # Ensure nesting cannot be snapshotted by the primary repository, without editing tracked files.
    exclude = root / '.git/info/exclude'
    if (root / '.git').is_dir():
        exclude.parent.mkdir(parents=True, exist_ok=True)
        old = exclude.read_text() if exclude.exists() else ''
        if '/.workspaces/' not in old.splitlines():
            exclude.write_text(old + ('\n' if old and not old.endswith('\n') else '') + '/.workspaces/\n')
    elif '/.workspaces/' not in (root / '.gitignore').read_text().splitlines():
        raise ValueError('Add /.workspaces/ to the primary .gitignore before creating a non-colocated JJ workspace')
    container.mkdir(exist_ok=True)
    if vcs == 'jj':
        # Resolve the local trunk alias; never inherit an unrelated task's parents.
        run(['jj', 'workspace', 'add', '-r', 'trunk()', '--name', name, str(destination)], root)
    else:
        try:
            base = run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], root)
        except ValueError:
            base = None
            for candidate in ('refs/remotes/origin/main', 'refs/remotes/origin/master',
                              'refs/heads/main', 'refs/heads/master'):
                try:
                    run(['git', 'rev-parse', '--verify', candidate + '^{commit}'], root)
                    base = candidate
                    break
                except ValueError:
                    continue
            if base is None:
                raise ValueError('Cannot identify trunk; configure origin/HEAD before creating a workspace')
        run(['git', 'worktree', 'add', '-b', f'worktree-{name}', str(destination), base], root)
    return str(destination)


def remove(payload):
    path = Path(payload['worktree_path']).absolute()
    if not path.exists():
        return
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Refusing symlinked workspace cleanup')
    root, vcs = primary(path.resolve())
    if path.parent != root / '.workspaces' or path == root:
        raise ValueError('Refusing cleanup outside the primary .workspaces directory')
    if vcs == 'jj':
        raise ValueError(f'JJ workspace retained at {path}; inspect and clean up explicitly with jj workspace forget and file removal')
    # Git worktree remove alone may delete ignored files. Check those explicitly.
    if run(['git', 'status', '--porcelain', '--untracked-files=all', '--ignored'], path):
        raise ValueError(f'Workspace retained: modified, untracked, or ignored files in {path}')
    # A clean checkout may still contain commits absent from local trunk.
    try:
        trunk = run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], root).split('/')[-1]
    except ValueError:
        trunk = 'main'
    run(['git', 'merge-base', '--is-ancestor', 'HEAD', f'refs/heads/{trunk}'], path)
    # Never force or delete branches here.
    run(['git', 'worktree', 'remove', str(path)], root)


def main():
    try:
        payload = json.load(sys.stdin)
        if payload['hook_event_name'] == 'WorktreeCreate':
            print(create(payload))
        elif payload['hook_event_name'] == 'WorktreeRemove':
            remove(payload)
        else:
            raise ValueError('Unsupported workspace event')
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(f'Nova workspace: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
