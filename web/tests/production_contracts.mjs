import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import ts from 'typescript';
function load(file,requireImpl) { const module={exports:{}};const localRequire=requireImpl||((name)=>{if(name.endsWith('.json'))return {default:JSON.parse(fs.readFileSync(path.resolve(path.dirname(file),name),'utf8'))};throw new Error(`Unsupported import: ${name}`);});new Function('module','exports','require',ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(module,module.exports,localRequire);return module.exports; }
const {productionTemplate,configureProductionTasks}=load('lib/productionTemplates.ts');
const {workflowTiming,unionMilliseconds,nodeClock,clockLabel}=load('lib/workflowTiming.ts');
assert.equal(productionTemplate('guoxue-v1').aspect,'1:1');
assert.equal(productionTemplate('health-v1').aspect,'4:3');
assert.throws(()=>productionTemplate('unknown'));
function client(fail=false){const calls=[];return {calls,from(table){let payload;return {update(value){payload=value;return this;},in(){return this;},eq(){return this;},select(){if(payload===undefined)return this;calls.push({table,payload});return Promise.resolve(fail?{error:{message:'denied'}}:{data:[{id:'x',task_id:'x',params:{}}]});},then(resolve,reject){return Promise.resolve(fail?{error:{message:'denied'}}:{data:[{id:'x',task_id:'x',params:{}}]}).then(resolve,reject);}};}};}
let db=client();await configureProductionTasks(db,['x'],'guoxue-v1');
assert.equal(db.calls.length,4);assert.equal(db.calls[1].payload.params.image_aspect_ratio,'1:1');assert.equal(db.calls[1].payload.params.template_version,2);assert.equal(db.calls[2].payload.params.production_template,'guoxue-v1');assert.equal(db.calls[3].payload.status,'pending');
db=client(true);await assert.rejects(configureProductionTasks(db,['x'],'health-v1'));assert.equal(db.calls.length,0);
assert.equal(unionMilliseconds([[0,100],[50,200],[300,400]]),300);
const stages=[{id:'s',kind:'render',status:'done',updated_at:'2026-10-16T00:01:00Z',params:{}}];
const records=[{type:'stage_timing',stage_kind:'render',meta:{stage_id:'s',started_at:'2026-10-16T00:00:10Z',ended_at:'2026-10-16T00:00:40Z',state:'finished'}},{type:'final',created_at:'2026-10-16T00:01:00Z',meta:{}}];
const timing=workflowTiming('2026-10-16T00:00:00Z','done',records,stages,Date.parse('2026-10-16T01:00:00Z'));
assert.equal(timing.total,60000);assert.equal(timing.processing,30000);assert.equal(timing.waiting,30000);
assert.equal(workflowTiming('2026-10-16T00:00:00Z','done',[records[1]],stages).waiting,null);
assert.equal(clockLabel(3_661_000),'1:01:01');
const activeStage={id:'clock',status:'processing',updated_at:'2026-10-16T00:01:00Z',params:{}};
const clockRecords=[{type:'stage_timing',stage_kind:'image',meta:{stage_id:'clock',started_at:'2026-10-16T00:00:00Z',state:'running'}}];
assert.equal(nodeClock(activeStage,clockRecords,Date.parse('2026-10-16T00:01:15Z')).label,'01:15');
assert.equal(nodeClock(activeStage,[{...clockRecords[0],meta:{...clockRecords[0].meta,state:'finished',ended_at:'2026-10-16T00:00:30Z'}}],Date.now()).label,'计时同步中');
assert.equal(nodeClock({...activeStage,status:'needs_review'},clockRecords,Date.parse('2026-10-16T00:02:00Z')).label,'待确认 01:00');
assert.equal(nodeClock({...activeStage,status:'done',params:{skipped:true}},[],Date.now()).label,'已复用');
const {authenticatedFetch}=load('lib/authenticatedFetch.ts',()=>({supabase:{auth:{getSession:async()=>({data:{session:{access_token:'unit-test-token'}}})}}}));
const originalFetch=globalThis.fetch;let captured;
try {
  globalThis.fetch=async(path,options)=>{captured={path,headers:options.headers};return new Response('{}');};
  await authenticatedFetch('/api/signed-url?path=owned');
  assert.equal(captured.headers.get('Authorization'),'Bearer unit-test-token');
  await assert.rejects(authenticatedFetch('https://example.invalid/signed-media'));
  await assert.rejects(authenticatedFetch('/api/\\external'));
} finally {globalThis.fetch=originalFetch;}
console.log('PASS: template isolation, queue activation order, failure fencing, timing union and historical gaps');

db=client();await configureProductionTasks(db,['x'],'health-v1',{visual_mode:'stock_video'});
assert.equal(db.calls[1].payload.params.template_version,2);
assert.equal(db.calls[1].payload.params.image_aspect_ratio,'4:3');
assert.equal(db.calls[1].payload.params.stock_visual_policy.content_line,'health');
assert.equal(db.calls[1].payload.params.stock_visual_policy.allow_images,true);
assert.equal(db.calls[2].payload.params.frame_mode,'landscape_blur');
