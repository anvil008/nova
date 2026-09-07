#!/usr/bin/env python3
"""Codex lifecycle adapter. Keeps prompts and tool contents out of Workcell state."""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys

loader = importlib.machinery.SourceFileLoader('workcell_dagr', str(Path(__file__).resolve().parents[1] / 'tools/workcell-flow'))
spec = importlib.util.spec_from_loader(loader.name, loader)
dagr = importlib.util.module_from_spec(spec); loader.exec_module(dagr)
FIELDS = {'input_tokens': 'input_tokens', 'output_tokens': 'output_tokens',
          'cached_input_tokens': 'cache_read_tokens', 'cache_write_input_tokens': 'cache_write_tokens',
          'reasoning_output_tokens': 'reasoning_tokens'}


def key(session):
    return 'codex-' + hashlib.sha256(session.encode()).hexdigest()[:20]


def root(cwd):
    path = Path(cwd).resolve(strict=True)
    for parent in (path, *path.parents):
        if (parent / '.git').exists() or (parent / '.jj').exists():
            return parent
    return path


def register(data, session, parent=None):
    ident = key(session)
    agent = dagr.find(data['agents'], ident)
    if not agent:
        agent = dict(id=ident, session_id=session, parent=parent, role='subagent' if parent else 'main',
                     harness='codex', model='', effort='', phase=data['run']['phase'], state='idle',
                     task=None, activity='', updated_at=dagr.now())
        data['agents'].append(agent)
    if parent:
        agent['parent'] = parent
    return agent


def transcript(agent, path, data):
    """Read only newly appended JSONL. Unknown/partial records never fabricate counts."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return
    state = agent.setdefault('telemetry', {})
    stat = path.stat()
    identity = f'{stat.st_dev}:{stat.st_ino}'
    if state.get('file') != identity or stat.st_size < state.get('offset', 0):
        # Preserve recorded usage; replay uses deterministic byte-offset record IDs.
        state.update(file=identity, offset=0, context={})
    with path.open('rb') as stream:
        try:
            first = json.loads(stream.readline())
        except (ValueError, TypeError):
            state['warning'] = 'Transcript identity unavailable; skipped.'
            return
        if first.get('type') != 'session_meta' or first.get('payload', {}).get('id') != agent['session_id']:
            state['warning'] = 'Transcript session identity mismatch; skipped.'
            return
        stream.seek(state['offset'])
        while True:
            offset = stream.tell(); line = stream.readline()
            if not line or not line.endswith(b'\n'):
                break
            state['offset'] = stream.tell()
            try:
                row = json.loads(line); payload = row.get('payload', {})
                if row.get('type') == 'turn_context':
                    state['context'] = {k: payload[k] for k in ('model', 'effort', 'turn_id') if isinstance(payload.get(k), str)}
                    state['context']['at'] = row.get('timestamp', '')
                    for k in ('model', 'effort'):
                        if state['context'].get(k): agent[k] = state['context'][k]
                if row.get('type') != 'event_msg' or payload.get('type') != 'token_count':
                    continue
                counts = (payload.get('info') or {}).get('total_token_usage')
                if not isinstance(counts, dict): continue
                totals = {dest: counts[src] for src, dest in FIELDS.items() if type(counts.get(src)) is int and counts[src] >= 0}
                if not totals: continue
                previous = state.get('totals', {})
                # Cumulative counters may repeat; lower counters indicate reset. Never subtract or guess.
                if any(v < previous.get(k, 0) for k, v in totals.items()):
                    state['warning'] = 'Cumulative counters decreased; usage after reset is unattributed.'
                    continue
                delta = {k: v - previous.get(k, 0) for k, v in totals.items()}
                state['totals'] = {**previous, **totals}
                if not any(delta.values()): continue
                context = state.get('context', {})
                record = dict(id='codex-' + hashlib.sha256(f'{agent["session_id"]}:{identity}:{offset}'.encode()).hexdigest()[:32],
                              source=f'Codex token_count at byte {offset}', updated_at=dagr.now(),
                              agent=agent['id'], harness='codex', model=context.get('model', ''), effort=context.get('effort', ''), **delta)
                binding = agent.get('binding', {})
                task = dagr.find(data['tasks'], binding.get('task'))
                # A whole provider interval must begin after binding. Mid-turn work stays session-only.
                eligible = (previous and all(k in previous for k in totals) and task and context.get('at') and binding.get('at') and
                            dagr.timestamp(context['at']) >= dagr.timestamp(binding['at']) and
                            task['attempts'] and task['attempts'][-1]['number'] == binding.get('attempt') and
                            task['state'] in ('working', 'blocked'))
                if eligible:
                    records = task['attempts'][-1].setdefault('usage', [])
                    task['attempts'][-1].setdefault('workers', {})[agent['id']] = {k: record[k] for k in ('harness', 'model', 'effort')}
                else:
                    records = agent.setdefault('usage', [])
                if not dagr.find(records, record['id']): records.append(record)
            except (ValueError, TypeError, KeyError):
                state['warning'] = 'Unrecognized transcript telemetry record skipped.'


def handle(payload):
    kind = payload.get('hook_event_name')
    if kind not in ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'SubagentStart', 'SubagentStop', 'Stop', 'Interrupt', 'TranscriptPoll'):
        return {}
    session = payload.get('session_id'); cwd = payload.get('cwd')
    if not isinstance(session, str) or not session or not isinstance(cwd, str):
        raise ValueError('Codex hook needs session_id and cwd')
    directory = dagr.project_store(cwd)
    project = directory
    with dagr.locked(project):
        existing = dagr.session_store(project,'codex',session,os.environ.get('WORKCELL_RUN_ID'))
        if existing:
            directory = existing
        elif dagr.run_paths(project):
            if kind not in ('SessionStart','UserPromptSubmit','SubagentStart'): return {}
            directory = dagr.session_store(project,'codex',session,os.environ.get('WORKCELL_RUN_ID'),True,cwd)
        elif kind in ('SessionStart','UserPromptSubmit','SubagentStart') and not (project/'archive').exists():
            data=dagr.create(root(cwd).name+' · codex')
            data['run']['owner']='codex:'+session
            dagr.atomic(project/'run.json',data)
    if directory.is_symlink(): raise ValueError('Refusing .workcell symlink')
    with dagr.locked(directory):
        path = directory / 'run.json'
        if not path.exists() and kind not in ('SessionStart', 'UserPromptSubmit', 'SubagentStart'):
            return {}
        incoming = payload.get('agent_id') if kind.startswith('Subagent') else session
        # Archived session facts must never be replayed into a new run by delayed hooks.
        current = dagr.read(path) if path.exists() else None
        attached = current and any(a.get('session_id') == incoming for a in current['agents'])
        for saved in (() if attached else (directory / 'archive').glob('*/run.json')):
            old = dagr.read(saved)
            if any(a.get('session_id') == incoming for a in old['agents']):
                return {}
        data = current if current else dagr.create(root(cwd).name + ' · agent work')
        # Final runs remain immutable. Explicit archive starts the next lifecycle.
        if data['run']['state'] != 'active': return {}
        before = json.dumps(data, sort_keys=True)
        parent = None
        if kind.startswith('Subagent'):
            parent = register(data, session)['id']
            session = payload.get('agent_id')
            if not isinstance(session, str) or not session: raise ValueError('Subagent event needs agent_id')
        agent = register(data, session, parent)
        agent['workspace'] = str(root(cwd))
        if os.environ.get('WORKCELL_SESSION_ID'):agent['launcher_session']=os.environ['WORKCELL_SESSION_ID']
        if kind=='SubagentStop':agent['session_closed']=True
        data['run'].setdefault('owner','codex:'+session)
        if kind != 'TranscriptPoll':
            agent['state'] = 'idle' if kind in ('Stop', 'SubagentStop', 'Interrupt') else 'working'
            agent['activity'] = 'Execution stopped; task outcome unchanged' if agent['state'] == 'idle' else 'Session active'
        # Parent event model is not evidence of a child's model.
        if not parent and isinstance(payload.get('model'), str): agent['model'] = payload['model']
        dagr.report_activity(data,agent,kind,payload)
        source = payload.get('agent_transcript_path') if parent else payload.get('transcript_path')
        if isinstance(source, str): transcript(agent, source, data)
        if json.dumps(data, sort_keys=True) != before:
            agent['updated_at'] = dagr.now()
            dagr.event(data, 'session_observed', kind, agent=agent['id'])
            dagr.atomic(path, data)
    if kind in ('SessionStart', 'SubagentStart'):
        return {'hookSpecificOutput': {'hookEventName': kind, 'additionalContext':
            f'Workcell session registered as {agent["id"]}. Run store: {directory}. Use --dir {directory} on Workcell commands in this session. Create meaningful tasks as scope becomes known. Bind this session before task work with workcell-flow session bind {session} --task TASK_ID. Stop hooks do not complete tasks.'}}
    if agent.get('tracking_notice') and kind=='PostToolUse':
        return {'hookSpecificOutput':{'hookEventName':kind,'additionalContext':agent['tracking_notice']}}
    return {}


def main():
    try:
        result = handle(json.load(sys.stdin))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'workcell tracking: {error}', file=sys.stderr)
        result = {}
    print(json.dumps(result))


if __name__ == '__main__': main()
