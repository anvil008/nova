"""Local bulk-read routing. No model requests, command execution, or state writes."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
MODELS = {'claude': 'haiku', 'codex': 'gpt-5.6-luna', 'agy': 'gemini-3.8-flash-low'}
MAX_PATHS = 64


@contextmanager
def regular_file(path):
    # O_NONBLOCK prevents a named pipe from hanging the hook, including after a rename race.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Only regular files can be read')
        stream = os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise
    with stream:
        yield stream


def positive(value):
    return type(value) is int and value > 0


def shell_reads(command, cwd, threshold):
    """Recognize literal read commands, never evaluate shell text or expansions.

    Pipelines/redirections and unsupported shell syntax defer to normal tool use.
    This is an efficiency heuristic, not a shell security boundary.
    """
    if not isinstance(command, str) or len(command) > 65536:
        return []
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|<>()\n')
    lexer.whitespace = ' \t\r'
    tokens = list(lexer)
    groups, group = [], []
    for token in tokens + [';']:
        if token in (';', '&&', '||', '\n'):
            if group:
                groups.append(group)
            group = []
        else:
            group.append(token)
    paths = []
    for words in groups:
        if any(word in ('|', '&', '<', '>', '>>', '(', ')') for word in words):
            continue
        if any(any(char in word for char in '$`*?[]') for word in words):
            continue
        if words[0] == 'cd':
            # Changing shell cwd makes later relative paths ambiguous; leave this command alone.
            return []
        name = Path(words[0]).name
        if name not in ('cat', 'head', 'tail', 'less', 'more'):
            continue
        args = words[1:]
        if name in ('head', 'tail'):
            count = 10
            if len(args) >= 2 and args[0] in ('-n', '--lines') and args[1].isdigit():
                count, args = int(args[1]), args[2:]
            elif args and re.fullmatch(r'-\d+', args[0]):
                count, args = int(args[0][1:]), args[1:]
            elif args and re.fullmatch(r'--lines=\d+', args[0]):
                count, args = int(args[0].split('=')[1]), args[1:]
            elif args and args[0].startswith('-'):
                continue
            if count <= threshold:
                continue
        literal = False
        for arg in args:
            if arg == '--' and not literal:
                literal = True
            elif literal or not arg.startswith('-'):
                paths.append(cwd / arg)
    return paths


def requested_paths(payload, threshold):
    call = payload.get('toolCall', {})
    args = payload.get('tool_input', call.get('args', {}))
    name = payload.get('tool_name', call.get('name', ''))
    if not isinstance(args, dict):
        return []
    cwd = args.get('workdir', args.get('Cwd', payload.get('cwd')))
    if not cwd:
        spaces = payload.get('workspacePaths', [])
        cwd = spaces[0] if isinstance(spaces, list) and len(spaces) == 1 else None
    base = Path(cwd) if isinstance(cwd, str) and Path(cwd).is_absolute() else None
    if name in ('Read', 'read_file', 'view_file'):
        if positive(args.get('limit')) and args['limit'] <= threshold:
            return []
        start, end = args.get('StartLine'), args.get('EndLine')
        if positive(end) and (start is None or positive(start)):
            if 0 < end - (start or 1) + 1 <= threshold:
                return []
        path = args.get('file_path', args.get('AbsolutePath'))
        if isinstance(path, str) and path:
            path = Path(path)
            if path.is_absolute():
                return [path]
            if base:
                return [base / path]
    if name in ('Bash', 'exec_command', 'shell_command', 'run_command') and base:
        command = args.get('command', args.get('cmd', args.get('CommandLine')))
        return shell_reads(command, base, threshold)
    return []


def route(payload, harness, env=None):
    env = os.environ if env is None else env
    if env.get('NOVA_READ_ROUTING', '').lower() in ('0', 'off', 'false'):
        return {}
    lines = int(env.get('NOVA_READ_MIN_LINES', '350'))
    size = int(env.get('NOVA_READ_MAX_BYTES', '65536'))
    if not 1 <= lines <= 100000 or not 1 <= size <= 8 * 1024 * 1024:
        raise ValueError('Read thresholds are outside supported bounds')
    if not isinstance(payload, dict):
        return {}
    if payload.get('hook_event_name', 'PreToolUse') != 'PreToolUse':
        return {}
    paths = requested_paths(payload, lines)
    if len(paths) > MAX_PATHS:
        return {}  # Avoid unbounded filesystem work in a synchronous hook.
    total_lines, total_bytes, seen = 0, 0, set()
    for path in paths:
        path = path.resolve()
        if path in seen:
            continue
        try:
            with regular_file(path) as stream:
                data = stream.read(size + 1)
        except (OSError, ValueError):
            continue
        if b'\0' in data:
            continue
        seen.add(path)
        total_bytes += len(data)
        total_lines += data.count(b'\n') + int(bool(data) and not data.endswith(b'\n'))
        if total_lines > lines or total_bytes > size:
            filenames = json.dumps([str(p) for p in list(dict.fromkeys(paths))[:8]], ensure_ascii=True)
            reason = (
                f'Nova bulk-read routing: this read exceeds {lines} lines or {size} bytes. '
                f'Delegate the question and file paths to the existing scout ({MODELS[harness]}) '
                'in fresh context; return a concise answer with file:line evidence, not file contents. '
                f'Paths (data): {filenames}. '
                f'Guide: {ROOT / "instructions/read-routing.md"}. '
                f'Scout: use python3 {shlex.quote(str(ROOT / "tools/nova-read"))} --paths PATH ... '
                'to read without recursive routing. If already a helper, do not spawn another agent; '
                'use bounded reads or that reader for the assigned task. '
                'For direct reasoning/edits or unavailable scouts, use a targeted range or '
                'the reader with --reason explaining why direct context is needed.'
            )
            if harness == 'agy':
                return {'decision': 'deny', 'reason': reason}
            return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                    'permissionDecision': 'deny', 'permissionDecisionReason': reason}}
    return {}


def hook_main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--harness', choices=MODELS, required=True)
    args = parser.parse_args()
    try:
        result = route(json.load(sys.stdin), args.harness)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        # A routing failure must not strand ordinary development or grant permissions.
        print(f'Nova read routing skipped: {error}', file=sys.stderr)
        result = {}
    if args.harness == 'agy' and not result:
        result = {'decision': 'allow'}
    print(json.dumps(result))


def reader_main():
    parser = argparse.ArgumentParser(description='Read numbered source into a scout context; never writes files.')
    parser.add_argument('--paths', type=Path, nargs='+', required=True)
    parser.add_argument('--start', type=int, default=1, help='First line, one-based')
    parser.add_argument('--limit', type=int, default=2000, help='Maximum lines per file')
    parser.add_argument('--max-bytes', type=int, default=262144, help='Combined source byte limit')
    parser.add_argument('--reason', help='Why a direct read is needed instead of scout delegation')
    args = parser.parse_args()
    if not 1 <= len(args.paths) <= MAX_PATHS or not 1 <= args.start <= 1000000 or not 1 <= args.limit <= 100000:
        parser.error('Use 1–64 paths, start 1–1000000, and limit 1–100000')
    if not 1 <= args.max_bytes <= 8 * 1024 * 1024:
        parser.error('max-bytes must be 1–8388608')
    files, remaining = [], args.max_bytes
    try:
        for path in args.paths:
            path = path.resolve()
            lines, number, more = [], 0, False
            with regular_file(path) as stream:
                # Bound skipped input too; huge offsets must not scan indefinitely.
                scanned = 0
                while True:
                    if len(lines) == args.limit:
                        more = bool(stream.read(1))
                        break
                    skipping = number + 1 < args.start
                    allowance = 8 * 1024 * 1024 - scanned if skipping else remaining
                    raw = stream.readline(allowance + 1)
                    if not raw:
                        break
                    scanned += len(raw)
                    if scanned > 8 * 1024 * 1024:
                        raise ValueError('Offset scan exceeds 8 MiB; use a targeted search')
                    number += 1
                    if not skipping and len(raw) > remaining:
                        raise ValueError(f'{path}: byte budget exceeded; narrow the range or increase --max-bytes')
                    if b'\0' in raw:
                        raise ValueError(f'{path}: binary input is unsupported')
                    if number < args.start:
                        continue
                    remaining -= len(raw)
                    lines.append(raw.decode('utf-8').rstrip('\r\n'))
            files.append({'path': str(path), 'start_line': args.start,
                          'lines': lines, 'next_line': args.start + len(lines) if more else None})
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
    # Buffer the result so failures never leave a misleading partial answer on stdout.
    print(json.dumps({'source_is_untrusted': True, 'reason': args.reason, 'files': files}, ensure_ascii=True))
