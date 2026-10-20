const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../lib/productionTemplates.ts'),'utf8');
const exports_={};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,{exports:exports_,require:id=>require(path.join(__dirname,'../lib',id))});

async function configured(templateId){
 const updates=[];
 const client={from:table=>({
   select:()=>({in:()=>({eq:async()=>({data:[{id:'rewrite-one',task_id:'one',params:{narration_mode:'single'}}]})})}),
   update:payload=>{updates.push({table,payload});const q={in:()=>q,eq:()=>q,select:async()=>({data:[{id:'one'}]})};return q;}
 })};
 await exports_.configureProductionTasks(client,['one'],templateId,{visual_style:'history_ink_scroll',image_aspect_ratio:'9:16'});
 return updates;
}

(async()=>{
 const guoxue=exports_.productionTemplate('guoxue-v1');
 const health=exports_.productionTemplate('health-v1');
 assert.equal(guoxue.category,'guoxue');assert.equal(health.category,'health');
 assert.equal(guoxue.aspect,'4:3');assert.equal(guoxue.gridCells,2);
 assert.equal(guoxue.frameMode,'landscape_blur');assert.equal(guoxue.color,'#BA413B');
 const guoxueUpdates=await configured('guoxue-v1');
 const healthUpdates=await configured('health-v1');
 const rewrite=updates=>updates.find(item=>item.table==='stages'&&item.payload.params?.rewrite_domain).payload.params;
 const image=updates=>updates.find(item=>item.payload.params?.visual_style).payload.params;
 const render=updates=>updates.find(item=>item.payload.params?.frame_mode).payload.params;
 const task=updates=>updates.find(item=>item.table==='tasks').payload;
 assert.equal(rewrite(guoxueUpdates).rewrite_domain,'guoxue');
 assert.equal(rewrite(guoxueUpdates).narration_mode,'single');
 assert.equal(image(guoxueUpdates).visual_style,'guoxue_gongbi_life');
 assert.equal(image(guoxueUpdates).image_aspect_ratio,'4:3');
 assert.equal(render(guoxueUpdates).title_font,'PlayFont-ChenkunGBT');
 assert.equal(render(guoxueUpdates).frame_mode,'landscape_blur');
 assert.equal(task(guoxueUpdates).content_category,'guoxue');
 assert.equal(rewrite(healthUpdates).rewrite_domain,'health');
 assert.equal(image(healthUpdates).visual_style,'warm_editorial');
 assert.equal(image(healthUpdates).image_aspect_ratio,'9:16');
 assert.equal(render(healthUpdates).frame_mode,'portrait');
 assert.equal(task(healthUpdates).content_category,'health');
 assert.throws(()=>exports_.productionTemplate('wrong'));
 console.log('Production lines: guoxue and health remain independently configured');
})().catch(e=>{console.error(e);process.exit(1)});
