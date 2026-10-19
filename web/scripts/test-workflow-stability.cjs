const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
function load(relative) {
 const source=fs.readFileSync(path.join(root,relative),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const context={exports:{}};vm.runInNewContext(code,context);return context.exports;
}
const {resolveStageSelection,workflowNeedsTick}=load('lib/workflowStability.ts');
let checks=0;
function check(condition,message){assert.ok(condition,message);checks++;}
const done=[{kind:'ingest',seq:1,status:'done'},{kind:'rewrite',seq:4,status:'done'},{kind:'render',seq:8,status:'done'}];
check(resolveStageSelection(done,'ingest',false)==='render','Completed task should open final stage');
for(let i=0;i<100;i++) assert.equal(resolveStageSelection(done.map(s=>({...s,updated_at:String(i)})),'rewrite',true),'rewrite');
checks++;
check(resolveStageSelection([...done.slice(0,2),{kind:'render',seq:8,status:'processing'}],'ingest',false)==='render','Follow active stage before user selection');
check(resolveStageSelection([...done.slice(0,2),{kind:'render',seq:8,status:'pending'}],'render',false)==='render','Keep downstream rerun selected');
check(!workflowNeedsTick('done')&&!workflowNeedsTick('failed')&&!workflowNeedsTick('cancelled'),'Terminal tasks stop timers');
check(workflowNeedsTick('processing')&&workflowNeedsTick('needs_review')&&workflowNeedsTick('pending'),'Active tasks retain clocks');
check(resolveStageSelection([{kind:'ingest',seq:1,status:'pending'},{kind:'book',seq:6,status:'done'}],'ingest',false)==='ingest','Preset book must not steal focus before collection');
const collection=fs.readFileSync(path.join(root,'app/video-collection/page.tsx'),'utf8');
check(collection.includes('aria-hidden={!loading}')&&!collection.includes('{loading && <div className="collection-loading"'),'Loader keeps its geometry');
check(collection.includes('if (request !== loadVersion.current) return;'),'Stale requests cannot overwrite filtered results');
const task=fs.readFileSync(path.join(root,'app/task/[id]/page.tsx'),'utf8');
check(task.includes('onSelect={selectStage}')&&task.includes('[statusSignature]'),'Manual navigation survives heartbeat refresh');
const css=fs.readFileSync(path.join(root,'app/workbench.css'),'utf8');
check(css.includes('scrollbar-gutter: stable')&&css.includes('.collection-loading.is-idle { visibility: hidden; }'),'Reserve scrollbar and loader spaces');
check(css.includes('.stage-view .anim-fade-in { animation: none; }'),'Avoid stacked vertical entry animations');
const clock=fs.readFileSync(path.join(root,'lib/useWorkflowClock.ts'),'utf8');
check(clock.includes('if (!ticking) return;')&&clock.includes('const poll = ticking ?'),'Stop periodic terminal-state updates');
console.log(`${checks} workflow stability checks passed`);
