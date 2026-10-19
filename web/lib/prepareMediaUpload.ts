"use client";
import { authenticatedFetch } from './authenticatedFetch';
import { audioBitrate, MAX_PREPROCESS_INPUT, uploadTarget } from './uploadPolicy';
type Purpose='narration'|'manual'|'bgm'|'voice';
let processing=false;

export async function prepareMediaUpload(file:File,purpose:Purpose,onStatus:(message:string)=>void=()=>{}):Promise<File>{
 onStatus('正在检查上传容量…');
 const response=await authenticatedFetch('/api/upload-policy');const policy=await response.json();
 if(!response.ok)throw new Error(policy.error||'读取上传限制失败');
 let limit=Number(policy.maxBytes);
 if(!Number.isSafeInteger(limit)||limit<=0)throw new Error('上传容量设置无效');
 if(purpose==='bgm')limit=Math.min(limit,25*1024*1024);
 if(purpose==='voice')limit=Math.min(limit,3_500_000); // Vercel form requests also have a body cap.
 if(!file.size)throw new Error('文件为空');
 if(file.size<=limit)return file;
 if(file.size>MAX_PREPROCESS_INPUT)throw new Error('文件超过200MB本地处理范围，请先导出较小文件或仅上传音轨');
 if(!file.type.startsWith('audio/')&&!file.type.startsWith('video/')&&!/\.(wav|mp3|m4a|mp4|mov|webm|mkv|aac|flac|ogg)$/i.test(file.name))throw new Error('该文件超过存储限制，请先压缩文件');
 if(processing)throw new Error('另一份文件正在本地处理，请完成后再试');
 processing=true;
 let engine:InstanceType<typeof import('@ffmpeg/ffmpeg').FFmpeg>|undefined;
 try{
  onStatus('文件较大，正在加载本地处理工具（首次约32MB）；原文件保留在电脑上…');
  const { FFmpeg }=await import('@ffmpeg/ffmpeg');engine=new FFmpeg();
  let inputDuration=0,probeDuration=0,probing=true;
  engine.on('log',({message})=>{const match=/Duration:\s*(\d+):(\d+):([\d.]+)/.exec(message);if(match)probeDuration=Number(match[1])*3600+Number(match[2])*60+Number(match[3]);});
  engine.on('progress',({progress})=>{if(!probing)onStatus(`正在本地${file.type.startsWith('video/')?'提取音轨':'压缩音频'} ${Math.min(99,Math.max(0,Math.round(progress*100)))}%…`);});
  let loadTimer:ReturnType<typeof setTimeout>|undefined;
  try{await Promise.race([engine.load({coreURL:'/media-runtime/v0.12.10/ffmpeg-core.js',wasmURL:'/media-runtime/v0.12.10/ffmpeg-core.wasm'}),new Promise<never>((_,reject)=>{loadTimer=setTimeout(()=>reject(new Error('本地处理工具加载超时，请检查网络后重试')),120_000);})]);}finally{clearTimeout(loadTimer);}
  await engine.writeFile('input.media',new Uint8Array(await file.arrayBuffer()));
  await engine.exec(['-i','input.media'],30_000);inputDuration=probeDuration;
  if(!Number.isFinite(inputDuration)||inputDuration<=0)throw new Error('无法识别媒体时长，请换用有效的音视频文件');
  const bitrate=audioBitrate(inputDuration,uploadTarget(limit));probing=false;
  const code=await engine.exec(['-y','-i','input.media','-map','0:a:0','-vn','-c:a','libmp3lame','-b:a',`${bitrate}k`,'-ar','44100','-ac',purpose==='bgm'?'2':'1','output.mp3'],300_000);
  if(code!==0)throw new Error('本地音频处理未完成；原文件未上传，请重试或导出较小MP3');
  probing=true;probeDuration=0;await engine.exec(['-i','output.mp3'],30_000);
  if(!probeDuration||Math.abs(probeDuration-inputDuration)>Math.max(.2,inputDuration*.001))throw new Error('处理后的音频时长不一致，已停止上传');
  const bytes=await engine.readFile('output.mp3');if(typeof bytes==='string'||!bytes.byteLength||bytes.byteLength>limit)throw new Error('处理后仍超过容量限制，请分段上传音频');
  const result=new File([new Uint8Array(bytes).buffer],file.name.replace(/\.[^.]+$/,'')+'-上传版.mp3',{type:'audio/mpeg',lastModified:file.lastModified});
  onStatus(`已本地处理：${(file.size/1_000_000).toFixed(1)} → ${(result.size/1_000_000).toFixed(1)} MB，准备上传…`);
  return result;
 }catch(error){throw new Error(error instanceof Error?error.message:'本地处理失败，文件未上传，请使用较小MP3重试');}
 finally{engine?.terminate();processing=false;}
}
