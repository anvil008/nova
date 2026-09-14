#!/usr/bin/env python3
"""Bounded parent integration reminder; never merges or removes files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

REMINDER = ('The parent owns this task’s integration. As each child result becomes ready, '
            'collect its immutable commit and evidence, verify the combined candidate, and '
            'integrate promptly into local main; synchronize the primary checkout when safe. '
            'Keep intermediate JJ work local: children do not push bookmarks or open PRs. '
            'When publication is authorized, publish the accumulated verified result through '
            'one integration bookmark and one PR to remote main; never push main directly. '
            'After merge, reconcile squash/rebase mappings, preserve newer local work, and '
            'verify remote branch deletion. Before closing superseded PRs, prove their work '
            'reached main, then delete only their unused head branches. Confirm each remaining '
            'remote branch belongs to active work before reporting completion. '
            'Do not wait for the user to repeat existing authorization. Child exit or a hook '
            'marker is not verification: never merge unreviewed work or unrelated workspaces. '
            'Read-only results need no merge. Report any remaining verification or synchronization blocker.')
READ_ONLY_AGENTS = {'scout', 'reviewer', 'explore', 'plan', 'claude_code_guide', 'statusline_setup'}


def read_only_agent(agent_type):
    # Mirrors tools/write_routing.normalized_name; unknown or missing types still arm.
    if not isinstance(agent_type, str):
        return False
    return re.split(r'(?:__|[:./]+)', agent_type.lower())[-1].replace('-', '_') in READ_ONLY_AGENTS


def _text(value):
    return value if isinstance(value, str) and value else ''


def _write(marker, state):
    """Atomic replace so a concurrent hook cannot read a half-written marker."""
    temporary = marker.with_name(f'{marker.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    os.replace(temporary, marker)


def _state(marker):
    """Marker state; an unreadable or pre-JSON marker falls back to arm-on-stop."""
    try:
        state = json.loads(marker.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {'legacy': True}
    return state if isinstance(state, dict) else {'legacy': True}


def _delivery(entry, pending, newest):
    """Record each pending agent whose result reached the parent in this transcript entry."""
    if not isinstance(entry, dict) or entry.get('type') != 'user':
        return
    stamp = _text(entry.get('timestamp'))
    if not stamp:
        return
    result = entry.get('toolUseResult')
    if isinstance(result, dict):  # Foreground Agent tool result; a launch ack is not a delivery.
        agent_id = result.get('agentId')
        if agent_id in pending and result.get('status') != 'async_launched':
            newest[agent_id] = max(newest.get(agent_id, ''), stamp)
        return
    message = entry.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    if isinstance(content, list):
        content = ' '.join(_text(part.get('text')) for part in content if isinstance(part, dict))
    if not isinstance(content, str) or '<task-notification>' not in content:
        return
    for agent_id in pending:  # Any notified status counts as delivered to the parent.
        if f'<task-id>{agent_id}</task-id>' in content:
            newest[agent_id] = max(newest.get(agent_id, ''), stamp)


def _deliveries(transcript, pending, consumed):
    """Newest unconsumed delivery timestamp per pending agent id; OSError when unreadable."""
    newest = {}
    with open(transcript, encoding='utf-8', errors='replace') as lines:
        for line in lines:
            if any(agent_id in line for agent_id in pending):
                try:
                    _delivery(json.loads(line), pending, newest)
                except ValueError:
                    continue  # Truncated or partially written line.
    return {agent: stamp for agent, stamp in newest.items() if stamp > _text(consumed.get(agent))}


def handle(payload, cache, harness='codex'):
    session = payload.get('session_id')
    if not isinstance(session, str) or not session:
        return {}
    key = hashlib.sha256(session.encode()).hexdigest()
    marker = cache / key
    event = payload.get('hook_event_name')
    if event == 'SubagentStop':
        if read_only_agent(payload.get('agent_type')):
            return {}
        state = _state(marker)
        pending = state.get('pending')
        state['pending'] = pending if isinstance(pending, dict) else {}
        consumed = state.get('consumed')
        state['consumed'] = consumed if isinstance(consumed, dict) else {}
        agent_id = _text(payload.get('agent_id'))
        if harness == 'claude' and agent_id and _text(payload.get('transcript_path')):
            state['pending'][agent_id] = True
        else:  # Only Claude's transcript records child results; others arm on stop as before.
            state['legacy'] = True
        cache.mkdir(parents=True, exist_ok=True)
        _write(marker, state)
        return {}  # Parent Stop owns continuation; never make a child merge trunk.
    if event == 'Stop':
        state = _state(marker)
        if not state:
            return {}
        pending = state.get('pending') if isinstance(state.get('pending'), dict) else {}
        consumed = state.get('consumed') if isinstance(state.get('consumed'), dict) else {}
        legacy = bool(state.get('legacy'))
        delivered = {}
        if not legacy:
            if not pending:
                return {}
            transcript = _text(payload.get('transcript_path'))
            if not transcript:
                legacy = True  # No parent transcript to read: fail open.
            else:
                try:
                    delivered = _deliveries(transcript, pending, consumed)
                except OSError:
                    legacy = True  # Unreadable transcript: fail open.
        if legacy:
            marker.unlink(missing_ok=True)
            if not payload.get('stop_hook_active'):
                return {'decision': 'block', 'reason': REMINDER}
            return {}
        if not delivered:
            return {}  # Children are still running: no result has reached the parent yet.
        for agent_id, stamp in delivered.items():
            pending.pop(agent_id, None)
            consumed[agent_id] = stamp  # Remember it so a later re-arm alone cannot remind again.
        _write(marker, {'pending': pending, 'consumed': consumed})
        if not payload.get('stop_hook_active'):
            return {'decision': 'block', 'reason': REMINDER}
    if event == 'SessionEnd':
        marker.unlink(missing_ok=True)
    return {}


def handle_agy(payload, cache, event):
    """Agy has delegation tool events, not a documented SubagentStop event."""
    session = payload.get('conversationId')
    if not isinstance(session, str) or not session:
        return {}
    cache = cache / 'agy'
    marker = cache / hashlib.sha256(session.encode()).hexdigest()
    if event == 'PostToolUse':
        call = payload.get('toolCall')
        if isinstance(call, dict) and call.get('name') == 'invoke_subagent' and not payload.get('error'):
            cache.mkdir(parents=True, exist_ok=True)
            marker.touch()
    elif (event == 'Stop' and payload.get('fullyIdle') is True
          and payload.get('terminationReason') == 'model_stop' and not payload.get('error')):
        if marker.exists():
            marker.unlink(missing_ok=True)
            return {'decision': 'continue', 'reason': REMINDER}
    return {}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness', choices=('codex', 'claude', 'agy'), default='codex')
    parser.add_argument('--event', choices=('PostToolUse', 'Stop'))
    args = parser.parse_args()
    try:
        cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'nova/integration'
        payload = json.load(sys.stdin)
        result = {}
        if isinstance(payload, dict):
            result = (handle_agy(payload, cache, args.event) if args.harness == 'agy'
                      else handle(payload, cache, args.harness))
        print(json.dumps(result))
    except (ValueError, OSError, TypeError) as error:
        print(f'Nova integration reminder unavailable: {error}', file=sys.stderr)
        print('{}')
