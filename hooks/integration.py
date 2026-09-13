#!/usr/bin/env python3
"""Bounded parent integration reminder; never merges or removes files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
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


def handle(payload, cache):
    session = payload.get('session_id')
    if not isinstance(session, str) or not session:
        return {}
    key = hashlib.sha256(session.encode()).hexdigest()
    marker = cache / key
    event = payload.get('hook_event_name')
    if event == 'SubagentStop':
        cache.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return {}  # Parent Stop owns continuation; never make a child merge trunk.
    if event == 'Stop' and marker.exists():
        marker.unlink(missing_ok=True)
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
            result = handle_agy(payload, cache, args.event) if args.harness == 'agy' else handle(payload, cache)
        print(json.dumps(result))
    except (ValueError, OSError, TypeError) as error:
        print(f'Nova integration reminder unavailable: {error}', file=sys.stderr)
        print('{}')
