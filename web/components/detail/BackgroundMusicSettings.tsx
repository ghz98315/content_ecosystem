"use client";
import { authenticatedFetch } from "@/lib/authenticatedFetch";

import { useEffect,useState } from 'react';
import { supabase } from '@/lib/supabase';

export function BackgroundMusicSettings({ taskId }: { taskId: string }) {
  const [path,setPath]=useState('');
  const [url,setUrl]=useState('');
  const [volume,setVolume]=useState(0.08);
  const [narration,setNarration]=useState(1);
  const [authorized,setAuthorized]=useState(false);
  const [ready,setReady]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  useEffect(() => {
    let active=true;
    supabase.from('tasks').select('bgm_path,bgm_volume,narration_volume,bgm_authorization_confirmed').eq('id',taskId).single().then(({data,error}) => {
      if (!active) return;
      if (error) {setError('背景音乐配置读取失败，请刷新重试');return;}
      setPath(data.bgm_path || '');setVolume(Number(data.bgm_volume));setNarration(Number(data.narration_volume));setAuthorized(data.bgm_authorization_confirmed);setReady(true);
    });
    return () => {active=false;};
  },[taskId]);
  useEffect(() => {
    let active=true;setUrl('');
    if (path) authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(path)}`).then(r=>r.json()).then(data=>{if(active)setUrl(data.signedUrl || '');}).catch(()=>{if(active)setError('音乐试听地址读取失败');});
    return () => {active=false;};
  },[path]);
  async function upload(file: File | undefined) {
    if (!file) return;
    const extension=file.name.split('.').pop()?.toLowerCase();
    if (!['mp3','wav','m4a'].includes(extension || '') || file.size<=0 || file.size>25*1024*1024) {setError('请选择25MB以内的MP3、WAV或M4A音乐');return;}
    setBusy(true);setError('');setMessage('');
    try {
      const response=await authenticatedFetch('/api/background-music',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({taskId,name:file.name,size:file.size})});
      const prepared=await response.json();
      if(!response.ok)throw new Error(prepared.error || '准备音乐上传失败');
      const next=prepared.path;
      const {error}=await supabase.storage.from('artifacts').uploadToSignedUrl(next,prepared.token,file,{contentType:file.type || 'audio/mpeg'});
      if(error)throw error;
      setPath(next);setAuthorized(false);setMessage('音乐已上传，请试听并保存设置后再确认配音。');
    } catch(err) {setError(err instanceof Error?err.message:'音乐上传失败');}
    finally {setBusy(false);}
  }
  async function save(remove=false) {
    setBusy(true);setError('');setMessage('');
    try {
      if(!remove && path && !authorized)throw new Error('请确认音乐使用授权后保存');
      const {data:render,error:readError}=await supabase.from('stages').select('status').eq('task_id',taskId).eq('kind','render').single();
      if(readError)throw readError;
      if(render.status==='processing')throw new Error('视频正在合成，请完成后再修改音乐');
      const {error}=await supabase.from('tasks').update({bgm_path:remove?null:path || null,bgm_volume:volume,narration_volume:narration,bgm_authorization_confirmed:remove?false:authorized}).eq('id',taskId);
      if(error)throw error;
      if(remove){setPath('');setAuthorized(false);}
      setMessage(render.status==='done'?'已保存，重新执行成片节点后应用音乐设置。':'已保存，将在成片时加入音乐；也可不添加音乐继续。');
    } catch(err) {setError(err instanceof Error?err.message:'音乐设置保存失败');}
    finally {setBusy(false);}
  }
  return <section className="bgm-settings" aria-label="背景音乐设置">
    <h3>背景音乐（可选）</h3><p>请在确认配音前上传并保存音乐；不添加也可继续。短音乐自动循环，收尾淡出。</p>
    <div className="bgm-controls">
      <label>音乐文件<input type="file" accept=".mp3,.wav,.m4a,audio/*" disabled={!ready || busy} onChange={event=>{void upload(event.target.files?.[0]);event.currentTarget.value='';}} /></label>
      {url && <audio controls src={url} />}
      <label>背景音乐音量 {Math.round(volume*100)}%<input type="range" min="0.02" max="0.30" step="0.01" value={volume} disabled={!ready || busy} onChange={event=>{setVolume(Number(event.target.value));setMessage('有未保存修改');}} /></label>
      <label>配音音量 {narration.toFixed(2)}<input type="range" min="0.50" max="1.50" step="0.05" value={narration} disabled={!ready || busy} onChange={event=>{setNarration(Number(event.target.value));setMessage('有未保存修改');}} /></label>
      <label><input type="checkbox" checked={authorized} disabled={!path || busy} onChange={event=>setAuthorized(event.target.checked)} />我确认已取得该音乐的使用授权</label>
      <button type="button" disabled={!ready || busy} onClick={()=>void save()}>保存音乐设置</button>
      {path && <button type="button" disabled={busy} onClick={()=>void save(true)}>移除背景音乐</button>}
    </div>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
