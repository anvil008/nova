#!/usr/bin/env python3
"""Non-blocking Claude/Agy lifecycle adapters. Never persist prompt or tool contents."""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys

loader=importlib.machinery.SourceFileLoader('dagr_native',str(Path(__file__).resolve().parents[1]/'tools/nova-flow'))
spec=importlib.util.spec_from_loader(loader.name,loader)
dagr=importlib.util.module_from_spec(spec);loader.exec_module(dagr)


def handle(harness,event,payload):
    if harness=='agy':
        session=payload.get('conversationId');paths=payload.get('workspacePaths',[])
        if not isinstance(paths,list) or not paths:return {}
        stores={dagr.project_store(p) for p in paths if isinstance(p,str) and Path(p).is_dir()}
        if len(stores)!=1:raise ValueError('Agy workspaces must identify one repository; refusing ambiguous routing')
        project=stores.pop();cwd=paths[0];model=payload.get('modelName');effort=None
    else:
        session=payload.get('session_id');cwd=payload.get('cwd')
        if not isinstance(cwd,str):return {}
        project=dagr.project_store(cwd);model=payload.get('model');effort=payload.get('effort')
        if isinstance(effort,dict):effort=effort.get('level')
    if not isinstance(session,str) or not session:return {}
    parent=None;join=os.environ.get('NOVA_RUN_ID')
    if harness=='claude' and payload.get('agent_id'):
        with dagr.locked(project):
            parent_store=dagr.session_store(project,harness,session,join,True,cwd)
            parent_data=dagr.read(parent_store/'run.json');join=parent_data['run']['id']
        parent=harness+'-'+hashlib.sha256(session.encode()).hexdigest()[:20]
        session=payload['agent_id']
    with dagr.locked(project):
        destination=dagr.session_store(project,harness,session,join)
        if not destination:
            # Delayed hooks must not resurrect archived runs.
            archives=list((project/'archive').glob('*/run.json'))+list((project/'runs').glob('*/archive/*/run.json'))
            if any(any(a.get('session_id')==session and a['harness']==harness for a in dagr.read(p)['agents']) for p in archives):return {}
            if event in ('SessionEnd','SubagentStop'):return {}
    if not destination or not any(a.get('session_id')==session and a['harness']==harness for a in dagr.read(destination/'run.json')['agents']):
        destination=dagr.lifecycle(project,harness,session,'start',join,cwd)
    ident=harness+'-'+hashlib.sha256(session.encode()).hexdigest()[:20]
    with dagr.locked(destination):
        data=dagr.read(destination/'run.json')
        if data['run']['state']!='active':return {}
        agent=dagr.find(data['agents'],ident)
        if not agent:return {}
        if parent and dagr.find(data['agents'],parent):agent['parent']=parent;agent['role']='subagent'
        agent.update(state='idle' if event in ('Stop','SessionEnd','SubagentStop') else 'working',activity=event,workspace=str(Path(cwd).resolve()),updated_at=dagr.now())
        if isinstance(model,str) and not parent:agent['model']=model
        if isinstance(effort,str):agent['effort']=effort
        if os.environ.get('NOVA_SESSION_ID'):agent['launcher_session']=os.environ['NOVA_SESSION_ID']
        dagr.report_activity(data,agent,event,payload)
        dagr.event(data,'session_observed',event,agent=ident);dagr.atomic(destination/'run.json',data)
    if event in ('SessionEnd','SubagentStop'):dagr.lifecycle(project,harness,session,'end',workspace=cwd)
    context=f'Nova tracks this session in {destination}. Use nova-flow --dir {destination} for task updates. Bind session {session} before task work. Report evidence and observed usage; never invent token counts.'
    if harness=='claude' and event in ('SessionStart','SubagentStart'):
        return {'hookSpecificOutput':{'hookEventName':event,'additionalContext':context}}
    if harness=='agy' and event=='PreInvocation' and (payload.get('invocationNum')==0 or agent.get('tracking_notice')):
        return {'injectSteps':[{'ephemeralMessage':context+' '+agent.get('tracking_notice','')}]}
    return {}


def main():
    p=argparse.ArgumentParser();p.add_argument('--harness',choices=['claude','agy'],required=True);p.add_argument('--event');args=p.parse_args()
    try:
        payload=json.load(sys.stdin);result=handle(args.harness,args.event or payload.get('hook_event_name'),payload)
    except (ValueError,TypeError,KeyError,OSError) as error:
        print('nova tracking: '+str(error),file=sys.stderr);result={}
    print(json.dumps(result))

if __name__=='__main__':main()
