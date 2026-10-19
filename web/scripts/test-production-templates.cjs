const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../lib/productionTemplates.ts'),'utf8');
const exports_={};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText,{exports:exports_,require:id=>require(path.join(__dirname,'../lib',id))});
(async()=>{
 const template=exports_.productionTemplate('guoxue-v1');assert.equal(template.aspect,'4:3');assert.equal(template.gridCells,2);assert.equal(template.frameMode,'landscape_blur');assert.equal(template.color,'#BA413B');
 const updates=[];const client={from:table=>({update:payload=>{updates.push({table,...payload});const q={in:()=>q,eq:()=>q,select:async()=>({data:[{id:'one'}]})};return q;}})};
 await exports_.configureProductionTasks(client,['one'],'guoxue-v1',{visual_style:'history_ink_scroll',image_aspect_ratio:'9:16'});
 assert.equal(updates[0].params.visual_style,'guoxue_gongbi_life');assert.equal(updates[0].params.image_aspect_ratio,'4:3');assert.equal(updates[1].params.title_font,'PlayFont-ChenkunGBT');assert.equal(updates[1].params.frame_mode,'landscape_blur');assert.equal(updates[1].params.title_color,'#BA413B');
 assert.throws(()=>exports_.productionTemplate('wrong'));console.log('10 production template contract checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
