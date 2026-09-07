#!/usr/bin/env python3
"""Optional, scoped format/lint feedback. No shell execution or lifecycle gate."""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def edited_paths(payload, root):
    call = payload.get('toolCall', {})
    args = payload.get('tool_input', call.get('args', {}))
    if not isinstance(args, dict):
        return []
    name = payload.get('tool_name', call.get('name', ''))
    if name not in {'apply_patch', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit',
                    'write_to_file', 'replace_file_content', 'multi_replace_file_content'}:
        return []
    names = [args.get(k) for k in ('file_path', 'notebook_path', 'TargetFile', 'AbsolutePath')]
    if name == 'apply_patch':
        patch = args.get('command', args.get('patch', ''))
        if isinstance(patch, str):
            names += re.findall(r'^\*\*\* (?:Add File|Update File|Move to): (.+)$', patch, re.M)
    cwd = Path(payload.get('cwd', root)).resolve()
    # Ambiguous relative paths are skipped for multi-workspace Agy events.
    if 'workspacePaths' in payload and 'cwd' not in payload:
        spaces = payload['workspacePaths']
        cwd = Path(spaces[0]).resolve() if len(spaces) == 1 else None
    result = set()
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        path = Path(name)
        if not path.is_absolute():
            if cwd is None:
                continue
            path = cwd / path
        path = path.resolve()
        if path.is_file() and path.is_relative_to(root):
            rel = path.relative_to(root)
            if not any(part in {'.git', '.jj'} for part in rel.parts):
                result.add(path)
    return sorted(result)


def run(payload, config):
    if config.get('enabled') is not True or payload.get('error'):
        return ''
    root = Path(config['root'])
    if not root.is_absolute() or not root.is_dir():
        raise ValueError('root must be an existing absolute repository path')
    root = root.resolve()
    messages = []
    for path in edited_paths(payload, root):
        rel = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatchcase(rel, glob) for glob in config.get('exclude', [])):
            continue
        for command in config.get('commands', []):
            if not any(fnmatch.fnmatchcase(rel, glob) for glob in command['match']):
                continue
            argv = command['argv']
            if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
                raise ValueError('argv must be a nonempty string array')
            if '{file}' not in argv:
                raise ValueError('argv must include a separate {file} argument')
            argv = [str(path) if a == '{file}' else a for a in argv]
            timeout = min(15, max(1, float(command.get('timeout', 5))))
            with tempfile.TemporaryFile() as output:
                try:
                    result = subprocess.run(argv, cwd=root, stdout=output, stderr=output,
                                            timeout=timeout, check=False)
                    output.seek(0)
                    detail = output.read(2000).decode(errors='replace').strip()
                    if result.returncode or detail:
                        messages.append(f'{rel}: {argv[0]} exited {result.returncode}\n{detail}')
                except (OSError, subprocess.TimeoutExpired) as error:
                    messages.append(f'{rel}: check unavailable or timed out: {error}')
    return '\n'.join(messages)[:4000]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--harness', choices=['claude', 'codex', 'agy'], required=True)
    parser.add_argument('--config', type=Path, default=os.environ.get('WORKCELL_HOOK_CONFIG'))
    options = parser.parse_args()
    if options.config is None:
        if options.harness == 'agy':
            print('{}')
        return
    try:
        message = run(json.load(sys.stdin), json.loads(options.config.read_text()))
    except (ValueError, OSError, KeyError, TypeError) as error:
        message = f'Workcell post-edit configuration/input error: {error}'
    if options.harness == 'agy':
        if message:
            print(message, file=sys.stderr)
        print('{}')
    elif message:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PostToolUse', 'additionalContext': message}}))
    # Advisory only: never block, approve a tool, or force another turn.


if __name__ == '__main__':
    main()
