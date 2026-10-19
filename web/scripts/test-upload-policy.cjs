const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const ts=require('../node_modules/typescript');
function load(file,mocks={}){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{exports,require:id=>mocks[id]||require(id),process,console,File,Uint8Array,setTimeout,clearTimeout});return exports;}
(async()=>{
 const p=load('lib/uploadPolicy.ts');assert.equal(p.safeUploadLimit(null),48000000);assert.equal(p.safeUploadLimit(10000000),9600000);assert.equal(p.safeUploadLimit(100000000),48000000);assert.equal(p.uploadTarget(48000000),43200000);assert.equal(p.audioBitrate(720,43200000),192);assert.throws(()=>p.audioBitrate(0,1));assert.throws(()=>p.audioBitrate(100000,1000));
 const server=load('lib/uploadPolicyServer.ts',{'./uploadPolicy':p});const admin={storage:{getBucket:async()=>({data:{file_size_limit:10000000}})}};assert.equal(await server.assertStorageUploadSize(admin,9600000),9600000);await assert.rejects(()=>server.assertStorageUploadSize(admin,9600001));await assert.rejects(()=>server.assertStorageUploadSize(admin,NaN));await assert.rejects(()=>server.storageUploadLimit({storage:{getBucket:async()=>({error:true})}}));
 let terminated=0,execs=0;class FFmpeg{handlers={};on(k,v){this.handlers[k]=v;}async load(){}async writeFile(){}async exec(args){execs++;if(args[0]==='-i'){this.handlers.log({message:'Duration: 00:01:10.00'});return 1;}return 0;}async readFile(){return new Uint8Array(1000);}terminate(){terminated++;}}
 const prepare=load('lib/prepareMediaUpload.ts',{'./authenticatedFetch':{authenticatedFetch:async()=>({ok:true,json:async()=>({maxBytes:48000000})})},'./uploadPolicy':p,'@ffmpeg/ffmpeg':{FFmpeg}}).prepareMediaUpload;
 const small=new File(['abc'],'small.mp3',{type:'audio/mpeg'});assert.equal(await prepare(small,'narration'),small);assert.equal(terminated,0);
 const large=new File([new Uint8Array(50000001)],'large.wav',{type:'audio/wav'});const result=await prepare(large,'narration');assert.equal(result.name,'large-上传版.mp3');assert.equal(result.size,1000);assert.equal(large.size,50000001);assert.equal(terminated,1);assert.equal(execs,3);
 await assert.rejects(()=>prepare(new File([],'empty.wav'),'manual'));await assert.rejects(()=>prepare({size:201*1024*1024,name:'large.wav',type:'audio/wav'},'manual'));
 FFmpeg.prototype.exec=async()=>2;await assert.rejects(()=>prepare(large,'manual'));assert.equal(terminated,2);
 console.log('Upload policy: 20 checks passed');
})().catch(e=>{console.error(e);process.exit(1);});
