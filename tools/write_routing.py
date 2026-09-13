"""Conservative PreToolUse routing for file-authoring requests.

This is an efficiency aid, not a security or ownership boundary.  It only
recognizes native editor tools and a small set of obvious shell writers; shell
scripts and arbitrary program side effects deliberately remain outside scope.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import sys


ROOT = Path(__file__).resolve().parents[1]
HARNESSES = {'codex', 'claude', 'agy'}
NATIVE_WRITES = {'edit', 'write', 'multiedit', 'notebookedit', 'apply_patch',
                 'write_file', 'write_to_file', 'replace', 'replace_file',
                 'replace_file_content', 'multi_replace_file_content'}


def normalized_name(value):
    """Return the final native tool segment without trusting arbitrary metadata."""
    if not isinstance(value, str):
        return ''
    return re.split(r'(?:__|[:./]+)', value.lower())[-1].replace('-', '_')


def tool_name(payload):
    if not isinstance(payload, dict):
        return ''
    call = payload.get('toolCall')
    candidates = (payload.get('tool_name'),
                  call.get('name') if isinstance(call, dict) else None)
    for candidate in candidates:
        name = normalized_name(candidate)
        if name:
            return name
    return ''


def tool_args(payload):
    if not isinstance(payload, dict):
        return {}
    call = payload.get('toolCall')
    args = payload.get('tool_input')
    if args is None and isinstance(call, dict):
        args = call.get('args')
    return args if isinstance(args, dict) else {}


def command_from(payload):
    args = tool_args(payload)
    for key in ('command', 'cmd', 'CommandLine'):
        value = args.get(key)
        if isinstance(value, str):
            return value
    return None


def shell_words(command):
    if not isinstance(command, str) or len(command) > 65536:
        return None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|<>()\n')
        lexer.whitespace = ' \t\r'
        return list(lexer)
    except ValueError:
        return None


def has_unquoted_operator(command, operators):
    """Check shell syntax without treating quoted literal argv as syntax."""
    quote = None
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == '\\' and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char in operators:
            return True
    return False


def shell_segments(command):
    """Split only unquoted shell command boundaries; never execute or expand text."""
    if not isinstance(command, str):
        return []
    result, start, quote, escaped = [], 0, None, False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
        elif char == '\\' and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char in ';|&\n':
            piece = command[start:index].strip()
            if piece:
                result.append(piece)
            if char in '|&' and index + 1 < len(command) and command[index + 1] == char:
                index += 1
            start = index + 1
        index += 1
    piece = command[start:].strip()
    return result + ([piece] if piece else [])


def authoring_redirection(segment, words):
    """Return true for an output redirect other than /dev/null in one command."""
    if not has_unquoted_operator(segment, {'>'}):
        return False
    for index, word in enumerate(words[:-1]):
        if word in ('>', '>>') and words[index + 1] != '/dev/null':
            return True
    return False


def runner_invocation(command):
    """Only exempt the bundled runner as a whole, never a shell chain around it."""
    if not isinstance(command, str) or has_unquoted_operator(command, set(';&|<>()\n')):
        return False
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        return False
    if not words:
        return False
    runner = str(ROOT / 'tools/nova-write')
    if words[0] == runner:
        return len(words) >= 2 and words[1] == '--'
    if len(words) >= 3 and words[0] in ('python', 'python3', sys.executable) and words[1] == runner:
        return words[2] == '--'
    return False


def shell_writes(command):
    """Recognize only direct, obvious authoring commands without evaluating text."""
    for segment in shell_segments(command):
        words = shell_words(segment)
        if not words:
            continue
        name = Path(words[0]).name
        args = words[1:]
        # Limit redirection routing to direct authoring commands. Test/build output
        # redirection is ordinary verification and should remain untouched.
        if name in ('echo', 'printf', 'cat', 'sed', 'awk') and authoring_redirection(segment, words):
            return True
        if name == 'tee':
            return True
        if name == 'sed' and any(arg == '-i' or arg.startswith('-i') or arg == '--in-place'
                                 or arg.startswith('--in-place=') for arg in args):
            return True
        if name == 'perl' and any(arg == '-i' or arg.startswith('-i')
                                  or (arg.startswith('-') and 'i' in arg[1:]) for arg in args):
            return True
        if name == 'dd' and any(arg.startswith('of=') for arg in args):
            return True
        if name in ('truncate', 'install'):
            return True
    return False


def claude_writer(payload):
    """Claude exposes helper identity; do not invent it for other harnesses."""
    agent_type = payload.get('agent_type') if isinstance(payload, dict) else None
    agent_id = payload.get('agent_id') if isinstance(payload, dict) else None
    return isinstance(agent_id, str) and bool(agent_id) and normalized_name(agent_type) == 'implementer'


def is_write_request(payload):
    name = tool_name(payload)
    if name in NATIVE_WRITES:
        return bool(tool_args(payload))
    if name in ('bash', 'exec_command', 'shell_command', 'run_command'):
        return shell_writes(command_from(payload))
    return False


def denied(harness):
    runner = ROOT / 'tools/nova-write'
    reason = (
        'Nova write routing: delegate this whole implementation task to the existing implementer, '
        'with owned paths and acceptance checks. The parent keeps design, review, integration, and publication. '
        f'An identity-ambiguous helper must run python3 {shlex.quote(str(runner))} -- COMMAND [ARGS...] for its assigned writes; '
        'an already-assigned helper must not recursively delegate. That runner executes argv directly (no implicit shell). '
        'Set NOVA_WRITE_ROUTING=off only for an explicit '
        'user override. This is routing guidance, not a security boundary.'
    )
    if harness == 'agy':
        return {'decision': 'deny', 'reason': reason}
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny', 'permissionDecisionReason': reason}}


def route(payload, harness, env=None):
    if harness not in HARNESSES or not isinstance(payload, dict):
        return {}
    env = os.environ if env is None else env
    if env.get('NOVA_WRITE_ROUTING', '').lower() in ('0', 'off', 'false'):
        return {}
    if payload.get('hook_event_name', 'PreToolUse') != 'PreToolUse':
        return {}
    command = command_from(payload)
    if command is not None and runner_invocation(command):
        return {}
    if not is_write_request(payload):
        return {}
    if harness == 'claude' and claude_writer(payload):
        return {}
    return denied(harness)


def hook_main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--harness', choices=HARNESSES, required=True)
    args = parser.parse_args()
    try:
        result = route(json.load(sys.stdin), args.harness)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        print(f'Nova write routing skipped: {error}', file=sys.stderr)
        result = {}
    print(json.dumps(result))


def runner_main():
    parser = argparse.ArgumentParser(description='Execute an assigned write command without shell evaluation.')
    parser.add_argument('command', nargs=argparse.REMAINDER,
                        help='Command after --; argv is executed directly')
    args = parser.parse_args()
    command = args.command
    if command[:1] == ['--']:
        command = command[1:]
    if not command:
        parser.error('provide COMMAND [ARGS...] after --')
    try:
        os.execvp(command[0], command)
    except FileNotFoundError:
        parser.exit(127, f'nova-write: command not found: {command[0]}\n')
    except OSError as error:
        parser.exit(126, f'nova-write: {error}\n')
