import fs from 'node:fs';
import assert from 'node:assert/strict';
import ts from 'typescript';
function load(file,requireImpl) { const module={exports:{}};new Function('module','exports','require',ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(module,module.exports,requireImpl);return module.exports; }
const {productionTemplate,configureProductionTasks}=load('lib/productionTemplates.ts');
const {workflowTiming,unionMilliseconds}=load('lib/workflowTiming.ts');
assert.equal(productionTemplate('guoxue-v1').aspect,'4:3');
assert.equal(productionTemplate('health-v1').aspect,'9:16');
assert.throws(()=>productionTemplate('unknown'));
function client(fail=false){const calls=[];return {calls,from(table){let payload;return {update(value){payload=value;return this;},in(){return this;},eq(){return this;},select(){calls.push({table,payload});return Promise.resolve(fail?{error:{message:'denied'}}:{data:[{id:'x'}]});}};}};}
let db=client();await configureProductionTasks(db,['x'],'guoxue-v1');
assert.equal(db.calls.length,3);assert.equal(db.calls[0].payload.params.image_aspect_ratio,'4:3');assert.equal(db.calls[1].payload.params.production_template,'guoxue-v1');assert.equal(db.calls[2].payload.status,'pending');
db=client(true);await assert.rejects(configureProductionTasks(db,['x'],'health-v1'));assert.equal(db.calls.length,1);
assert.equal(unionMilliseconds([[0,100],[50,200],[300,400]]),300);
const stages=[{id:'s',kind:'render',status:'done',updated_at:'2026-10-16T00:01:00Z',params:{}}];
const records=[{type:'stage_timing',stage_kind:'render',meta:{stage_id:'s',started_at:'2026-10-16T00:00:10Z',ended_at:'2026-10-16T00:00:40Z',state:'finished'}},{type:'final',created_at:'2026-10-16T00:01:00Z',meta:{}}];
const timing=workflowTiming('2026-10-16T00:00:00Z','done',records,stages,Date.parse('2026-10-16T01:00:00Z'));
assert.equal(timing.total,60000);assert.equal(timing.processing,30000);assert.equal(timing.waiting,30000);
assert.equal(workflowTiming('2026-10-16T00:00:00Z','done',[records[1]],stages).waiting,null);
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
