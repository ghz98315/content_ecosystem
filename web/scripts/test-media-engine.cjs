// Standalone WebAssembly engine regression; no browser automation or cloud media.
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),cp=require('node:child_process'),assert=require('node:assert/strict');
(async()=>{
 const ff=process.env.FFMPEG_BINARY||process.argv[2];if(!ff)throw new Error('Pass a native FFmpeg binary as argument or FFMPEG_BINARY');
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'upload-wasm-test-'));
 try{
  const src=path.join(tmp,'synthetic.wav'),outPath=path.join(tmp,'result.mp3');
  cp.execFileSync(ff,['-y','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=192000','-t','70','-ac','2',src]);
  const create=require('@ffmpeg/core');global.self={location:{href:'http://localhost/ffmpeg-core.js'}};
  const core=await create({wasmBinary:fs.readFileSync(require.resolve('@ffmpeg/core/wasm')),mainScriptUrlOrBlob:'http://localhost/ffmpeg-core.js#'+btoa(JSON.stringify({wasmURL:'http://localhost/ffmpeg-core.wasm'}))});
  let logs=[];core.setLogger(item=>logs.push(item.message));core.FS.writeFile('input.wav',fs.readFileSync(src));
  const started=Date.now();core.setTimeout(300000);core.exec('-y','-i','input.wav','-map','0:a:0','-vn','-c:a','libmp3lame','-b:a','192k','-ar','44100','-ac','1','output.mp3');assert.equal(core.ret,0,logs.slice(-5).join('\n'));core.reset();
  const out=core.FS.readFile('output.mp3');assert(fs.statSync(src).size>50000000);assert(out.length<48000000);fs.writeFileSync(outPath,out);
  const probe=cp.spawnSync(ff,['-i',outPath],{encoding:'utf8'});assert(/Duration: 00:01:10\./.test(probe.stderr));
  console.log(JSON.stringify({sourceBytes:fs.statSync(src).size,resultBytes:out.length,elapsedSeconds:(Date.now()-started)/1000,duration:'70 seconds'}));
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exit(1)});
