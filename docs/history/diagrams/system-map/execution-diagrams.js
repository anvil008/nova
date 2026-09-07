"use strict";

// Execution diagrams for the current workflow contracts.
const executionDesign = {
  workflows: {
    overview: {title:"Separate workflows. One shared build.", summary:"Planning, review, debugging, profiling, and refactor assessment can pass selected changes into the shared build pipeline. Research is a capability supplied by the harness."},
    research: {title:"Research a question", summary:"Investigate the requested question and return a report. Planning starts only when the user requests it."},
    plan: {title:"Choose an approach", summary:"Choose one plan or multiple plan ideas. Planning uses its own research stage; the orchestrator determines team sizes."},
    build: {title:"Implement and verify", summary:"Reuse the request, selected plan, or findings. The orchestrator sizes the team and schedules ready work with the right verification."},
    review: {title:"Review existing work", summary:"Return verified findings and coverage. Offer implementation for selected, actionable fixes."},
    debug: {title:"Diagnose a reported failure", summary:"Reproduce the symptom, test competing causes, and return a diagnosis. Supported, authorized repairs continue through build."},
    profile: {title:"Measure before optimizing", summary:"Establish a benchmark and supported bottlenecks. Carry that baseline into any optimization."},
    refactor: {title:"Assess how to simplify", summary:"Propose structural improvements and the behavior to preserve. Assessment can finish with a report; authorized changes use shared build."},
    docs: {title:"Run documentation on its own", summary:"Produce and validate documentation, then prepare its own pull request."}
  },
  nodes: {
    coordinator: ["Orchestrator", "human", "Frames the goal, chooses team sizes and assignments, carries user decisions, and reviews evidence. The orchestrator boxes represent the same coordinator at different checkpoints."],
    plan: ["Planning workflow", "human", "Offer one plan or multiple plan ideas once, reusing an explicit or saved choice. Plans default to Markdown; HTML is an explicit companion."],
    research: ["Research workflow", "agent", "Research is an underlying capability. The standalone Workcell command is retired; native research or exploration and the shared evidence handoff remain."],
    build: ["Shared build workflow", "human", "Accept a request, selected plan, or scoped findings. Reuse evidence, resolve missing decisions, and select scheduling and verification independently."],
    review: ["Review workflow", "agent", "Review a diff or codebase scope, verify findings, and return a report. Selected fixes can enter build with existing evidence."],
    profile: ["Profile workflow", "agent", "Capture comparable measurements and supported bottlenecks. A requested optimization preserves the baseline and requires a measurement afterward."],
    refactor: ["Refactor workflow", "agent", "Assess structural friction and return a Markdown proposal with preserved contracts, existing tests, tradeoffs, and validation. HTML is optional when requested. Authorized implementation uses shared build with a protected GREEN baseline."],
    refactorAssessment: ["Refactor assessment", "agent", "Planners own the assessment and proposal, directing researchers into useful independent questions. Reuse accepted evidence; identify demonstrated friction and what must stay unchanged. No new agent role is required."],
    docs: ["Documentation workflow", "agent", "Own a standalone documentation change and its validation. Within build, the documenter performs only its assigned documentation stage."],
    goal: ["Goal and existing evidence", "artifact", "Carry the selected plan, findings, source revision, constraints, decisions, and authorization into the next stage."],
    planner: ["Planner", "agent", "Own a plan or assigned part of an approach. Direct planning research and reuse existing reports; the orchestrator determines team sizes and final authorship."],
    debug: ["Debug workflow", "agent", "Investigate a reported failure and return a Markdown diagnosis, with optional requested HTML. Investigation-only requests finish here; supported and authorized repairs use shared build."],
    debugger: ["Debugger", "agent", "Reproduce the assigned symptom, test competing hypotheses, and return causal evidence. Investigation-only requests end with a diagnosis; requested repairs carry that evidence into shared build."],
    researcher: ["Researcher", "agent", "Investigate the assigned questions read-only. Return sources, coverage, gaps, and uncertainty to the caller. The planner directs this role; standalone questions use native research capabilities."],
    choice: ["Choose one plan or multiple ideas", "human", "Ask whether the user wants one plan or multiple plan ideas unless already specified. This chooses the output, not the number of agents; team sizes are the orchestrator’s decision."],
    compare: ["Compare approaches", "human", "The orchestrator checks feasibility, constraints, evidence, migration risk, and testability. Recommend an approach; resolve material tradeoffs with the user."],
    report: ["Report artifacts", "artifact", "Markdown is the default with no format question. Generate an HTML companion only for an explicit visual request. Full plans also retain structured work items."],
    transition: ["Continue to build?", "human", "For standalone plan, review, or profile, offer build when actionable work is ready. Reuse an existing plan-and-implement or review-and-fix request instead of asking again."],
    ready: ["Check implementation readiness", "human", "A report is not automatically an executable plan. Reuse existing artifacts and source context; ask a planner only for the missing scope, task breakdown, or acceptance criteria."],
    tasks: ["Define executable work items", "agent", "The planner defines tasks, dependencies, ownership, and acceptance criteria. A straightforward change can use a brief without GitHub tracking."],
    issues: ["Optional GitHub tracking", "artifact", "The orchestrator creates or reconciles issues from the reviewed task plan when tracking and the writes are authorized. The specifier does not own issue creation."],
    schedule: ["Schedule ready tasks", "human", "Choose the number of agents for ready work, without a workflow-imposed cap. Separate concurrent writers; schedule dependencies and overlapping ownership in order."],
    specifier: ["Specifier", "agent", "Write runnable acceptance tests for one feature or fix task, prove honest RED, and seal them before its builder begins."],
    baseline: ["Integrator: baseline", "gate", "For behavior-preserving changes, prove existing tests GREEN and protect the baseline before implementation. No invented failing tests are required."],
    builder: ["Builder", "agent", "Implement one assigned task within ownership, preserve sealed tests, and return source-bound test and runtime evidence."],
    reviewer: ["Independent reviewer", "agent", "Check the assigned change and return actionable findings. The orchestrator decides whether to continue repairs, revise assignments, accept the result, or surface an unresolved decision."],
    integrate: ["Combine accepted changes", "artifact", "Prepare the combined source from accepted task results, preserving their commits and evidence. Individually passing branches do not prove the combined result."],
    documenter: ["Documenter", "agent", "Update relevant documentation in assigned files. Parallel authors need disjoint ownership; generated code or changed examples need appropriate checks."],
    verify: ["Integrator: final verification", "gate", "Verify the exact final source, including documentation changes, with the required combined checks and runtime evidence. Refreshed source needs refreshed evidence."],
    measure: ["Profiler: measure again", "gate", "Repeat the benchmark with a comparable workload and environment. Compare the result with the baseline and its spread before accepting a performance claim."],
    docsCheck: ["Documentation checks", "gate", "Validate the docs build, links, examples, and generated output as applicable. Check the final documentation change before its PR and merge."],
    deliver: ["Delivery decision", "human", "The orchestrator accepts actual verification evidence and prepares the PR. Remote checks and merge follow the user's authorization; plan approval alone is not deployment approval."],
    stop: ["Finish with the result", "artifact", "A report with no actionable findings is a valid completion. Preserve unresolved questions and coverage gaps without manufacturing implementation work."]
  }
};
let diagramPlanMode="single", diagramScale="team", diagramKind="behavior", treeFitsWidth=true;
let treeSizingObserver;
const diagramSourceById={refactor:"refactor",refactorAssessment:"refactor",debug:"debug",debugger:"debug",research:"plan",plan:"plan",build:"build",review:"review",profile:"profile",docs:"docs",planner:"plan",researcher:"plan",specifier:"build",baseline:"refactor",measure:"profile",documenter:"docs",docsCheck:"docs"};
function diagramRegisterComponents(){
  for(const [id,[title,type,text]] of Object.entries(executionDesign.nodes)){
    components["diagram-"+id]={title,type,icon:type==="gate"?"shield":type==="human"?"branch":"file",tag:"Workflow stage",sub:text,text,input:"The goal, pinned source, existing artifacts, decisions, and authorized scope.",output:text,rules:["Current workflow contract. Team sizes are chosen by the orchestrator."],sources:[{path:"docs/diagrams/system-map/execution-diagrams.js",line:1},{path:"skills/"+(diagramSourceById[id]||"build")+"/SKILL.md",line:1}]};
  }
}
function diagramNode(id,title,detail,tag){
 const data=executionDesign.nodes[id], type=data[1];
 return `<button class="rev-node ${type}" data-component="diagram-${id}" aria-pressed="${selected==='diagram-'+id}"><span class="rev-role">${esc(tag||({agent:'Agent',human:'Decision / coordinator',artifact:'Artifact',gate:'Verification'}[type]))}</span><strong>${esc(title||data[0])}</strong>${detail?`<span class="rev-detail">${esc(detail)}</span>`:""}</button>`;
}
function diagramTeam(id,title,detail,symbol='N'){
 return diagramNode(id,title+' × '+symbol,detail,'Agents · count chosen by orchestrator');
}
function diagramRepeat(){return '<div class="rev-repeat"><strong aria-label="Repeated work">…</strong><span>Repeat as needed</span><small>No prescribed count</small></div>';}
function diagramArrow(label=""){return `<div class="rev-edge ${label?'rev-edge-labeled':''}" ${label?'':'aria-hidden="true"'}><span>${esc(label)}</span></div>`;}
function diagramStack(items,cls=""){return `<div class="rev-stack ${cls}">${items.join(diagramArrow())}</div>`;}
function diagramFork(branches,label="",join=true){
 return `<div class="rev-fork-wrap">${label?`<p class="rev-branch-caption">${esc(label)}</p>`:""}<div class="rev-fork ${join?'':'rev-terminal-fork'}" style="--branches:${branches.length}">${branches.map(b=>`<div class="rev-branch ${b.terminal?'rev-branch-terminal':''}"><div class="rev-branch-label">${esc(b.label)}</div>${b.html}</div>`).join("")}</div></div>`;
}
function diagramReport(name){return `<div class="rev-artifacts">${diagramNode('report',name+'.md','Default output','Markdown')}${diagramNode('report',name+'.html','Only when a visual version is requested','Optional HTML')}</div>`;}
function diagramModeControl(key,values,current,label){return `<div class="rev-control"><span>${esc(label)}</span><div class="mode-toggle" role="group" aria-label="${esc(label)}">${Object.entries(values).map(([value,title])=>`<button data-diagram-option="${key}" data-value="${value}" class="${current===value?'active':''}" aria-pressed="${current===value}">${esc(title)}</button>`).join("")}</div></div>`;}
function diagramBuildTransition(){
 const buildLink='<a class="rev-route" href="#flow/build">Shared /build pipeline →</a>';
 return diagramStack([diagramNode('coordinator','Orchestrator reviews the result','Check constraints, evidence, and remaining decisions.'),diagramFork([
  {label:'Standalone request · actionable work',html:diagramStack([diagramNode('transition','Ask whether to build','Carry selected work and evidence forward.'),'<span class="rev-branch-condition">If yes</span>'+buildLink])},
  {label:'Implementation already requested',html:diagramStack([diagramNode('transition','Continue within authorization','Reuse the original scope and user decisions.'),buildLink])},
  {label:'Report-only · no actionable work · or user declines',html:diagramNode('stop','Finish with the report','No implementation stage is required.')}
 ],'Continue or finish',false)]);
}



function diagramPlannerBranch(approach){
 return diagramStack([
  diagramTeam('planner',approach?'Planners for approach '+approach:'Planning team','The orchestrator assigns contributors and a plan owner.','P'),
  diagramTeam('researcher','Planning researchers','The planner owns questions and synthesis. Use native delegation or root dispatch when nesting is unavailable; reuse source-backed reports.','R'),
  diagramNode('planner','Plan owner synthesizes',approach?'Produce this approach, tradeoffs, risks, and evidence.':'Produce the executable plan, tasks, and acceptance criteria.','Plan authorship')
 ]);
}

function diagramPlanDiagram(){
 const multi=diagramPlanMode==='multiple';
 const branches=multi?diagramFork([
  {label:'Approach A',html:diagramPlannerBranch('A')},
  {label:'Further ideas',html:diagramRepeat()},
  {label:'Approach N',html:diagramPlannerBranch('N')}
 ],'The orchestrator chooses idea and team counts; repeated approaches are compressed here.'):diagramPlannerBranch('');
 const rows=[diagramNode('plan','/plan'),diagramNode('choice','One plan or multiple plan ideas?','Ask once; reuse an explicit or saved choice. This selects the output, not team size.'),diagramNode('coordinator','Orchestrator frames the planning work','Choose plan ownership, contributors, and distinct directions. Planners scope and direct research.'),branches];
 if(multi)rows.push(diagramNode('compare','Compare and recommend','Resolve material tradeoffs with the user.'),diagramNode('planner','Assigned plan owner produces the final plan','Combine selected ideas and contributions into executable work.'));
 rows.push(diagramNode('coordinator','Review the completed plan','Accept, request revisions, or raise a user decision.'),diagramReport('plan'),diagramBuildTransition());
 return diagramStack(rows);
}

function diagramTaskChain(){
 const behavior=['behavior','fix'].includes(diagramKind);
 const prefix=behavior?diagramTeam('specifier','Specifiers',diagramKind==='fix'?'Prove the defect with failing regression tests.':'Write and seal failing acceptance tests.'):diagramTeam('baseline','Integrators','Verify and protect the existing GREEN baseline.');
 const loop=diagramStack([
  diagramTeam('builder','Builders','Implement assigned work with separate ownership.'),
  diagramTeam('reviewer','Reviewers','Independently check the change; return findings.')
 ]);
 return `<div class="rev-task-chain">${prefix}${diagramArrow()}<div class="rev-repair-loop">${loop}</div><div class="rev-return">↶ Orchestrator directs review and repairs</div></div>`;
}

function diagramBuildDiagram(){
 const detail=diagramScale==='detail';
 const rows=[diagramNode('build','/build','Request, selected plan, or selected findings'),diagramNode('ready','Check scope, source, and readiness','Reuse the plan and completed evidence. Recheck changed source.'),diagramFork([
   {label:'Executable plan already available',html:diagramNode('goal','Reuse the selected plan','No repeat investigation or mandatory new planning round.')},
   {label:'Planning information is missing',html:diagramTeam('tasks','Planning contributors','Prepare the missing brief or task plan, then orchestrator review.')}
  ]),diagramNode('issues','Optional GitHub issues','Created only when requested and authorized. Local plans use task keys without GitHub issues.'),diagramNode('schedule','Orchestrator sizes and schedules the team','Choose as many agents as useful; parallelize separate work and preserve dependencies.')];
 const branches=detail?[{label:'One task shown in detail',html:diagramTaskChain()}]:[
  {label:'Ready task A',html:diagramTaskChain()},
  {label:'Further tasks',html:diagramRepeat()},
  {label:'Ready task N',html:diagramTaskChain()}
 ];
 rows.push(diagramFork(branches,'Role counts vary independently; N does not require equal team sizes.'),diagramNode('coordinator','Collect results and evidence'),diagramNode('integrate','Combine accepted task results','Orchestrator coordinates integration of the accepted work.'),diagramTeam('documenter','Documenters','Update relevant documentation; include it before final verification.'),diagramTeam('verify','Integrators','Verify the final combined source, documentation, tests, and runtime checks.'));
 if(diagramKind==='optimization')rows.push(diagramTeam('measure','Profilers','Repeat the benchmark with a comparable workload and environment.'));
 rows.push(diagramNode('deliver','Orchestrator accepts → PR','Check the final head; merge follows the user’s authorization.'));
 return diagramStack(rows);
}

function diagramAssessmentDiagram(id){
 const profiling=id==='profile';
 const role=profiling?'measure':'reviewer', detail=profiling?'Capture baseline, workload, environment, run count, and spread.':'Inspect the requested source; return findings and coverage.';
 const rows=[diagramNode(id,'/'+id),diagramNode('coordinator','Orchestrator assigns the work','Choose the agents and distinct areas to investigate.'),diagramTeam(role,profiling?'Profilers':'Reviewers',detail)];
 if(!profiling)rows.push(diagramNode('reviewer','Verify the findings','Independently refute uncertain claims where needed; retain reproduction evidence.'));
 rows.push(diagramReport(id),diagramBuildTransition());
 rows.push('<p class="rev-callout">'+(profiling?'An optimization returns to the profiler after implementation. Without a usable benchmark, establishing one is a separate scoped change.':'A reviewer called inside /build returns to that build’s repair cycle. The standalone offer to build does not run inside the cycle.')+'</p>');
 return diagramStack(rows);
}

function diagramDocsDiagram(){
 return diagramStack([diagramNode('docs','/docs'),diagramNode('coordinator','Orchestrator chooses the documentation team','Assign files and schedule dependent edits.'),diagramTeam('documenter','Documenters','The orchestrator chooses the count; parallel authors use separate ownership.'),diagramNode('docsCheck','Validate documentation','Build, links, examples, and generated output as applicable.'),diagramNode('coordinator','Orchestrator reviews the result'),diagramNode('deliver','Documentation PR → authorized merge','A complete standalone workflow.')]);
}



function diagramNativeResearch(){
 return `<div class="rev-native-research"><span class="rev-role">HARNESS CAPABILITY</span><h3>Research stays available</h3><p>Use the host’s available research, search, or exploration tools for standalone questions. There is no separate Workcell research command. Planning still delegates investigators internally and can reuse an existing report.</p><p>Workcell retains a shared handoff: findings, sources, coverage, conflicts, and open questions.</p><p class="rev-native-sources">Native capabilities vary: <a href="https://learn.chatgpt.com/docs/agent-configuration/subagents" target="_blank" rel="noreferrer">Codex exploration</a> · <a href="https://code.claude.com/docs/en/sub-agents" target="_blank" rel="noreferrer">Claude Code Explore / Plan</a> · <a href="https://antigravity.google/docs/subagents" target="_blank" rel="noreferrer">Antigravity research</a></p></div>`;
}
function diagramCoreOverview(){
 const entry=(id,detail)=>`<a class="rev-entry" href="#flow/${id}"><span class="rev-command">/${id}</span><strong>${esc(executionDesign.workflows[id].title)}</strong><span>${esc(detail)}</span></a>`;
 const branch=(id,label,detail,result)=>({label,html:diagramStack([entry(id,detail),`<div class="rev-finish"><strong>${esc(result)}</strong><span>A complete outcome on its own.</span></div>`])});
 return `<div class="rev-overview rev-core-overview"><div class="rev-start"><span class="rev-role">YOUR GOAL</span><h2>Choose the outcome you need</h2><p>The orchestrator chooses the agents and assignments.</p></div>${diagramArrow()}${diagramFork([
  branch('plan','Design a change','One plan or multiple ideas, with internal research when useful.','Executable plan'),
  branch('review','Inspect existing work','Find and verify problems in a diff or codebase.','Review report'),
  branch('debug','Investigate a reported failure','Reproduce the symptom and establish its cause.','Diagnosis report'),
  branch('profile','Investigate performance','Measure a baseline and supported bottlenecks.','Profiling report'),
  branch('refactor','Assess code structure','Identify useful simplifications and the behavior to preserve.','Refactor proposal')
 ],'Peer workflows · choose the result you need')}${diagramArrow('Continue only with supported, scoped, and authorized implementation')}<a class="rev-build-hub" href="#flow/build"><span>/build</span><strong>One shared implementation pipeline</strong><p>Enter directly with a change request, or continue with a plan, selected findings, or a supported diagnosis. The orchestrator sizes every agent team.</p><b>Inspect the build diagram ↗</b></a>${diagramArrow()}<div class="rev-result">Verified changes and authorized delivery</div><div class="rev-standalone">${entry('docs','Independent documentation workflow → its own validated PR')}<p>Documentation can also be an assigned stage inside /build, before its final verification.</p></div>${diagramNativeResearch()}<div class="rev-support"><h3>Prepare & operate</h3><div>${['repo-setup','deploy','wiki'].map(id=>`<a href="#flow/${id}">/${id} ↗</a>`).join('')}</div><p>Auxiliary skills: <a href="#flow/jj">jj</a> · <a href="#flow/use-other-harness">use-other-harness</a></p></div></div>`;
}

function diagramDiagram(id){
 if(id==='plan')return diagramPlanDiagram();
 if(id==='build')return diagramBuildDiagram();
 if(id==='debug')return diagramDebugDiagram();
 if(id==='refactor')return diagramRefactorDiagram();
 if(id==='docs')return diagramDocsDiagram();
 return diagramAssessmentDiagram(id);
}

function diagramControls(id,verification=true){
 let html='';
 if(id==='plan')html+=diagramModeControl('plan',{single:'One plan',multiple:'Multiple plan ideas'},diagramPlanMode,'Planning choice');
 if(id==='build'){
  html+=diagramModeControl('scale',{detail:'Inspect one task',team:'Orchestrator-sized team'},diagramScale,'Diagram detail · not a team-size setting');
  if(verification)html+=diagramModeControl('kind',{behavior:'Feature',fix:'Bug fix',refactor:'Refactor',optimization:'Optimization'},diagramKind,'Verification path');
 }
 return html?'<div class="rev-scenario-controls">'+html+'</div>':'';
}



function diagramDiagramWidth(id){return id==='plan'&&diagramPlanMode==='multiple'?900:['debug','refactor'].includes(id)?780:720;}



function diagramForCurrentWorkflow(){return ({perf:'profile'}[workflowName]||workflowName);}

function diagramExecutionMarkup(){
 const id=diagramForCurrentWorkflow();
 if(id==='research')return `<section class="revision"><div class="rev-disclaimer">RESEARCH CAPABILITY <span>The standalone research skill was removed. Planning keeps the researcher role and evidence helpers.</span></div>${diagramNativeResearch()}</section>`;
 if(!executionDesign.workflows[id])return legacyFlowMarkup();
 const workflow=currentWorkflow(), path=currentPath(), entry=workflowName;
 const paths=workflow.paths.length>1?`<div class="path-controls"><span>Execution path</span><div class="mode-toggle" role="group" aria-label="Execution path">${workflow.paths.map(item=>`<button data-path="${esc(item.id)}" class="${item.id===path.id?'active':''}" aria-pressed="${item.id===path.id}">${esc(item.label)}</button>`).join('')}</div></div>`:'';
 const detail=`<details class="rev-path-detail"><summary>Detailed stages · ${esc(path.label)}</summary><div class="stage-timeline">${expandedStages(path).map(stageMarkup).join('')}</div></details>`;
 return `<section class="revision"><div class="rev-heading"><div><span class="rev-command">/${entry}</span><h2>${esc(executionDesign.workflows[id].title)}</h2><p>${esc(executionDesign.workflows[id].summary)}</p></div></div>${paths}${diagramControls(id)}<div class="rev-diagram" style="--diagram-min:${diagramDiagramWidth(id)}px" tabindex="0" role="region" aria-label="Scrollable workflow diagram">${diagramDiagram(id)}</div>${detail}<div class="workflow-outcome"><span>OUTCOME</span><strong>${esc(path.outcome||workflow.outcome)}</strong></div></section>`;
}

function diagramTreeMarkup(){return `<section class="revision"><div class="rev-tree-controls">${diagramModeControl('fit',{fit:'Fit width',full:'Actual size'},treeFitsWidth?'fit':'full','Diagram scale')}<span>See every branch, or use actual size and scroll for detail.</span></div><div class="rev-diagram" tabindex="0" role="region" aria-label="Scrollable decision tree">${diagramCoreOverview()}</div></section>`;}

function fitTreeDiagram(){
 treeSizingObserver?.disconnect();
 const region=document.querySelector('[aria-label="Scrollable decision tree"]'), tree=region?.firstElementChild;
 if(!tree)return;
 const resize=()=>{
  tree.style.zoom='1';
  if(!treeFitsWidth)return;
  const style=getComputedStyle(region), available=region.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight);
  tree.style.zoom=String(Math.min(1,available/tree.scrollWidth));
 };
 resize();
 if(typeof ResizeObserver!=='undefined'){
  let width=region.clientWidth;
  treeSizingObserver=new ResizeObserver(()=>{if(region.clientWidth!==width){width=region.clientWidth;resize();}});
  treeSizingObserver.observe(region);
 }
}

function diagramDebugDiagram(){
 const path=currentPath(), investigateOnly=path.id==='diagnose';
 const rows=[diagramNode('debug','/debug','Start with a reported symptom, failing job, or flaky test.'),diagramNode('coordinator','Orchestrator scopes the investigation','Choose debugger agents for useful independent hypotheses or areas.'),diagramTeam('debugger','Debuggers','Reproduce the failure, reduce the case, and test competing causes. Record commands, environment, source, and evidence.'),diagramReport('diagnosis'),diagramNode('coordinator','Review the diagnosis','Check causal evidence and remaining gaps; preserve the original repair authorization.')];
 if(investigateOnly){
  rows.push(diagramNode('stop','Finish with the diagnosis report','Investigation is complete. Include any missing reproduction conditions or unsupported hypotheses; no repair is started.'));
 }else{
  const ready=[diagramNode('ready','Reuse the diagnosis and repair brief','Only missing design or executable detail needs a planner.')];
  if(path.id==='dependent')ready.push(diagramNode('schedule','Schedule the dependent repairs','Preserve task ownership and dependency order.'));
  ready.push(diagramNode('build','Shared build owns the repair','Specifier proves RED → builder implements → independent review → final verification.'),'<a class="rev-route" href="#flow/build/detail">Inspect the shared /build pipeline →</a>');
  rows.push(diagramNode('transition','Cause established and repair authorized?','A debug-and-fix request already authorizes the transition. No repeat approval is needed.'),diagramFork([
   {label:'Cause unresolved · or repair not authorized',html:diagramNode('stop','Finish with findings and gaps','Return the report without guessing a repair.')},
   {label:'Supported cause · authorized repair',html:diagramStack(ready)}
  ],'Continue only when both conditions hold',false));
 }
 return diagramStack(rows);
}

function diagramRefactorDiagram(){
 const path=currentPath(), assessmentOnly=path.id==='assess';
 const rows=[
  diagramNode('refactor','/refactor','Assess simplification opportunities, or carry out an explicitly requested refactor.'),
  diagramNode('coordinator','Orchestrator scopes the assessment','Preserve behavior, public contracts, dependencies, and existing tests.'),
  diagramTeam('refactorAssessment','Planners','Assess demonstrated friction and own the proposal. Reuse accepted assessment evidence instead of repeating it.'),
  diagramTeam('researcher','Researchers when useful','The planner directs independent structural questions; return source evidence and gaps.'),
  diagramReport('refactor'),
  diagramNode('coordinator','Review the refactor proposal','Check the benefit, invariants, risk, validation, and existing implementation authorization.')
 ];
 if(assessmentOnly){
  rows.push(diagramFork([
   {label:'Report-only · no worthwhile changes · user declines',html:diagramNode('stop','Finish with the refactor proposal','Assessment is a complete outcome. Keep existing code when simplification is not justified.')},
   {label:'Actionable scope · implementation wanted',html:diagramStack([diagramNode('transition','Offer build or reuse authorization','Assessment alone does not authorize code changes. An explicit refactor request already does.'),'<span class="rev-branch-condition">Once authorized</span><a class="rev-route" href="#flow/refactor/bounded">Inspect the refactor implementation path →</a>'])}
  ],'Report or implement',false));
 }else{
  const ready=[diagramNode('ready','Reuse the selected proposal and brief','Ask a planner only for missing executable detail; do not restart assessment.')];
  if(path.id==='broad')ready.push(diagramNode('schedule','Schedule the dependent refactors','Use disjoint ownership and preserve dependency order.'));
  ready.push(diagramTeam('baseline','Integrators','Prove the existing tests GREEN and seal the unchanged baseline before any builder starts.'),diagramNode('build','Shared build owns the refactor','Builder preserves behavior → independent review → final combined verification. A failing baseline stops implementation.'),'<a class="rev-route" href="#flow/build/refactor">Inspect shared build with refactor verification →</a>');
  rows.push(diagramNode('transition','Selected scope and refactor authorized?','An explicit refactor request already authorizes that scope.'),diagramFork([
   {label:'Scope unresolved · or implementation not authorized',html:diagramNode('stop','Finish with the proposal and gaps','Resolve material decisions before changing code.')},
   {label:'Selected scope · authorized implementation',html:diagramStack(ready)}
  ],'Continue within the requested scope',false));
 }
 rows.push('<p class="rev-callout">Refactor checks simpler structure and preserved behavior. A performance improvement claim also needs comparable measurements through /profile.</p>');
 return diagramStack(rows);
}
