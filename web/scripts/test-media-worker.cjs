const {Worker}=require('node:worker_threads'),{pathToFileURL}=require('node:url'),path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 if(!process.argv[2])throw new Error('Pass a synthetic WAV fixture path as argument');
 const root=path.resolve(__dirname,'../public/media-runtime');
 const worker=new Worker(`const {parentPort,workerData}=require('node:worker_threads');const fs=require('node:fs');global.self=global;self.location={href:workerData.wrapper};self.postMessage=(data)=>parentPort.postMessage(data);global.fetch=async(url)=>new Response(fs.readFileSync(new URL(url)),{headers:{'Content-Type':'application/wasm'}});(async()=>{await import(workerData.wrapper);parentPort.on('message',data=>self.onmessage({data}));parentPort.postMessage({ready:true});})();`,{eval:true,workerData:{wrapper:pathToFileURL(path.join(root,'wrapper-v0.12.15/worker.js')).href}});
 let id=0,pending=new Map();worker.on('message',msg=>{if(msg.ready)return;const done=pending.get(msg.id);if(done&&msg.type!=='LOG'&&msg.type!=='PROGRESS'){pending.delete(msg.id);msg.type==='ERROR'?done.reject(new Error(msg.data)):done.resolve(msg.data);}});
 worker.on('error',e=>{for(const item of pending.values())item.reject(e);});
 await new Promise((resolve,reject)=>{worker.once('message',resolve);worker.once('error',reject);});
 function send(type,data){const key=++id;return new Promise((resolve,reject)=>{pending.set(key,{resolve,reject});worker.postMessage({id:key,type,data});});}
 try{
  await send('LOAD',{coreURL:pathToFileURL(path.join(root,'v0.12.10/ffmpeg-core.js')).href,wasmURL:pathToFileURL(path.join(root,'v0.12.10/ffmpeg-core.wasm')).href});
  await send('WRITE_FILE',{path:'input.wav',data:fs.readFileSync(process.argv[2])});
  const result=await send('EXEC',{args:['-y','-i','input.wav','-vn','-c:a','libmp3lame','-b:a','192k','output.mp3'],timeout:300000});assert.equal(result,0);
  const output=await send('READ_FILE',{path:'output.mp3'});assert(output.length<48000000);console.log('Unbundled worker protocol + wasm 53MB compression passed:',output.length);
 }finally{await worker.terminate();}
})().catch(e=>{console.error(e);process.exit(1)});
