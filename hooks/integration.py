#!/usr/bin/env python3
"""Bounded parent integration reminder; never merges or removes files."""
import hashlib
import json
import os
from pathlib import Path
import sys

REMINDER = ('The parent owns integration of this task’s JJ workspace and Git worktree results. '
            'Collect immutable child commits, review and test the combined candidate, and complete '
            'the authorized delivery path without asking the user to repeat authorization. '
            'Synchronize local main after verified integration, preserving unrelated active work. '
            'If unfinished, state awaiting review or blocked with the concrete reason; do not claim '
            'the overall task is complete. Read-only child results require no merge. Never merge '
            'unreviewed work or unrelated workspaces merely to satisfy this reminder.')


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


if __name__ == '__main__':
    try:
        cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'nova/integration'
        print(json.dumps(handle(json.load(sys.stdin), cache)))
    except (ValueError, OSError, TypeError) as error:
        print(f'Nova integration reminder unavailable: {error}', file=sys.stderr)
        print('{}')
