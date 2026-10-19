const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
const root=path.resolve(__dirname,'..');let checks=0;
function load(file,imports={}){const code=ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;const context={exports:{},window:{addEventListener(){},removeEventListener(){},dispatchEvent(){}},CustomEvent:class{constructor(type,value){this.type=type;this.detail=value?.detail;}},require:name=>imports[name]||require(name)};vm.runInNewContext(code,context);return context.exports;}
const helpers=load('lib/videoText.ts');
function check(fn){fn();checks++;}
check(()=>assert.equal(helpers.resolveVideoText({video_text:{title:'新',subtitle:'',footnote:''}},{cover_title:'旧',cover_subtitle:'旧副'}).subtitle,''));
check(()=>assert.equal(helpers.resolveVideoText({},{cover_title:'旧',cover_subtitle:'旧副'}).title,'旧'));
check(()=>assert.equal(helpers.resolveVideoText({main_title:'原画面'},{cover_title:'旧封面'}).title,'原画面'));
check(()=>assert.throws(()=>helpers.validateVideoText({title:'',subtitle:'副',footnote:''},true),/填写主标题/));
check(()=>assert.throws(()=>helpers.validateVideoText({title:'主',subtitle:'',footnote:''},true),/填写主标题/));
check(()=>assert.equal(helpers.validateVideoText({title:'主'.repeat(24),subtitle:'副'.repeat(36),footnote:''},true).title.length,24));
check(()=>assert.throws(()=>helpers.validateVideoText({title:'主'.repeat(25),subtitle:'副',footnote:''},true),/24字/));
check(()=>assert.throws(()=>helpers.validateVideoText({title:'主',subtitle:'副'.repeat(37),footnote:''},true),/36字/));
check(()=>assert.equal(helpers.validateVideoText({title:'',subtitle:'',footnote:''}).title,''));
check(()=>assert.throws(()=>helpers.validateVideoText({title:'主\n题',subtitle:'副',footnote:''}),/单行/));
check(()=>assert.throws(()=>helpers.validateVideoText({title:'主',subtitle:'副',footnote:'脚'.repeat(61)}),/60字/));

function harness(params){
 const state=[],effects=[];let cursor=0,writes=0;const ref={current:null};const row={id:'render',status:'pending',updated_at:'first',params:structuredClone(params)};
 const react={forwardRef:fn=>fn,useState(initial){const i=cursor++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return [state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v;}];},useRef(initial){const i=cursor++;return state[i]??(state[i]={current:initial});},useEffect(fn,deps){const i=cursor++;if(!state[i]||deps.some((v,n)=>v!==state[i].deps[n])){state[i]?.cleanup?.();state[i]={deps};effects.push(()=>{state[i].cleanup=fn();});}},useImperativeHandle(target,fn){target.current=fn();}};
 const client={from(){let update=null;const filters=[];const q={select(){return q;},eq(k,v){filters.push([k,v]);return q;},neq(){return q;},single(){return Promise.resolve({data:structuredClone(row),error:null});},update(value){update=value;return q;},then(resolve){let data=[];if(update&&filters.every(([k,v])=>k!=='updated_at'||row.updated_at===v)){row.params=structuredClone(update.params);row.updated_at+='x';writes++;data=[{id:row.id}];}return Promise.resolve({data,error:null}).then(resolve);}};return q;}};
 const jsx=(type,props)=>({type,props});const {VideoTextSettings}=load('components/detail/VideoTextSettings.tsx',{'react':react,'react/jsx-runtime':{jsx,jsxs:jsx},'@/lib/supabase':{supabase:client},'@/lib/videoText':helpers});
 function render(props={}){cursor=0;const tree=VideoTextSettings({taskId:'task',...props},ref);effects.splice(0).forEach(fn=>fn());return tree;}
 return {row,ref,render,get writes(){return writes;}};
}
function find(tree,label){if(!tree||typeof tree!=='object')return null;if(tree.props?.['aria-label']===label)return tree;for(const child of [tree.props?.children].flat(Infinity)){const found=find(child,label);if(found)return found;}return null;}
async function ready(h,props={}){h.render(props);for(let i=0;i<10;i++)await Promise.resolve();return h.render(props);}
(async()=>{
 let h=harness({video_text:{title:'初始',subtitle:'副标题',footnote:'脚注'}});let tree=await ready(h);
 find(tree,'画面主标题').props.onChange({target:{value:'未点保存的新标题'}});h.render();
 let text=await h.ref.current.saveForRewrite(true);check(()=>assert.equal(text.title,'未点保存的新标题'));check(()=>assert.equal(h.row.params.video_text.title,text.title));check(()=>assert.equal(h.writes,1));
 h=harness({video_text:{title:'原始',subtitle:'副标题',footnote:'脚注'}});tree=await ready(h);
 find(tree,'画面主标题').props.onChange({target:{value:'本地改动'}});h.render();h.row.params.video_text.title='别处的新标题';
 text=await h.ref.current.saveForRewrite(true);check(()=>assert.equal(text,null));check(()=>assert.equal(h.writes,0));check(()=>assert.equal(h.row.params.video_text.title,'别处的新标题'));
 h=harness({video_text:{title:'',subtitle:'',footnote:''}});await ready(h);text=await h.ref.current.saveForRewrite(true);check(()=>assert.equal(text,null));check(()=>assert.equal(h.writes,0));
 h=harness({});await ready(h);text=await h.ref.current.saveForRewrite(false);check(()=>assert.equal(h.writes,0));check(()=>assert.ok(text));
 h=harness({});await ready(h,{legacyTitle:'旧封面主标题',legacySubtitle:'旧封面副标题'});text=await h.ref.current.saveForRewrite(true);check(()=>assert.equal(text.title,'旧封面主标题'));check(()=>assert.equal(h.row.params.video_text.subtitle,'旧封面副标题'));
 h=harness({video_text:{title:'原始',subtitle:'副标题',footnote:''}});tree=await ready(h);find(tree,'画面主标题').props.onChange({target:{value:'正在编辑'}});h.render({legacyTitle:'稍后加载的旧封面'});for(let i=0;i<10;i++)await Promise.resolve();h.render({legacyTitle:'稍后加载的旧封面'});text=await h.ref.current.saveForRewrite(true);check(()=>assert.equal(text.title,'正在编辑'));
 const source=fs.readFileSync(path.join(root,'components/detail/RewriteDetail.tsx'),'utf8');
 check(()=>assert.ok(!source.includes('封面标题确认')&&!source.includes('setCoverTitle')));
 check(()=>assert.ok(source.indexOf('saveForRewrite(isHistory)')<source.indexOf('supabase.rpc("confirm_rewrite"')));
 console.log(`${checks} unified video title checks passed`);
})().catch(error=>{console.error(error);process.exitCode=1;});
