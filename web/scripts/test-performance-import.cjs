const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
const root=path.resolve(__dirname,'..');
function load(file){const code=ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;const context={exports:{},require:name=>name==='./performanceImport'?load('lib/performanceImport.ts'):require(name)};vm.runInNewContext(code,context);return context.exports;}
const {parseDelimited,prepareImport}=load('lib/performanceImport.ts');
const {validateImportRows,importSnapshots}=load('lib/performanceImportServer.ts');
const id='11111111-1111-4111-8111-111111111111',time='2026-01-01T00:00:00.000Z',posts=[{id,post_url:'https://example.com/a'}];let checks=0;
function check(fn){fn();checks++;}
check(()=>assert.equal(parseDelimited('\uFEFF播放量,备注\r\n123,"一行,两列"')[1][1],'一行,两列'));
check(()=>assert.equal(parseDelimited('播放量\t备注\n123\t"两行\n内容"')[1][1],'两行\n内容'));
check(()=>assert.throws(()=>parseDelimited('播放量,备注\n1,"未结束')));
check(()=>assert.throws(()=>parseDelimited('播放量,备注\n1,错"号')));
const row=prepareImport('作品链接,播放量,点赞数\nhttps://example.com/a,120,4',posts,time).rows[0];
check(()=>assert.equal(row.views,120));check(()=>assert.equal(row.postId,id));check(()=>assert.ok(row.notes.includes('按0占位')));
check(()=>assert.equal(prepareImport('播放量\n1.2万',posts,time,id).errors.length,1));
check(()=>assert.equal(prepareImport('播放量\n-1',posts,time,id).errors.length,1));
check(()=>assert.equal(prepareImport('作品ID,作品链接,播放量\n'+id+',https://example.com/b,1',posts,time).errors.length,1));
check(()=>assert.equal(prepareImport('播放量\n1',posts,time).errors.length,1));
check(()=>assert.throws(()=>prepareImport('播放量,views\n1,2',posts,time,id)));
check(()=>assert.throws(()=>validateImportRows([{...row,views:2147483648}])));
check(()=>assert.throws(()=>validateImportRows([{...row,recordedAt:'2026-01-01'}])));
check(()=>assert.throws(()=>validateImportRows([{...row,postId:'invalid'}])));
function database(owned=true){const saved=[];const db={from(table){let data=[],filters={};const query={select(){return query;},eq(k,v){filters[k]=v;return query;},in(k,v){filters[k]=v;return query;},limit(){return query;},upsert(rows){for(const r of rows)if(!saved.some(old=>old.id===r.id))saved.push(r);data=rows.map(r=>({id:r.id}));return query;},then(resolve){if(table==='published_posts')data=owned?[{id}]:[];else if(!data.length)data=saved.filter(r=>(!filters.post_id||filters.post_id.includes(r.post_id))&&(!filters.recorded_at||filters.recorded_at.includes(r.recorded_at)));return Promise.resolve({data,error:null}).then(resolve);}};return query;}};return {db,saved};}
(async()=>{
 let {db,saved}=database();let result=await importSnapshots(db,'owner',[row,row]);check(()=>assert.equal(result.inserted,1));check(()=>assert.equal(result.duplicates,1));
 result=await importSnapshots(db,'owner',[row]);check(()=>assert.equal(result.inserted,0));check(()=>assert.equal(saved.length,1));
 await assert.rejects(()=>importSnapshots(db,'owner',[{...row,views:900}]),/不同快照/);checks++;
 await assert.rejects(()=>importSnapshots(database(false).db,'owner',[row]),/当前工作区/);checks++;
 await assert.rejects(()=>importSnapshots(db,'owner',[row,{...row,views:1000}]),/文件中/);checks++;
 console.log(`${checks} performance import checks passed`);
})().catch(error=>{console.error(error);process.exitCode=1;});
