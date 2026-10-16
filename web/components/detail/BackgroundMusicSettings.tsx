"use client";
import { authenticatedFetch } from "@/lib/authenticatedFetch";

import { useEffect,useState } from 'react';
import { supabase } from '@/lib/supabase';
import { MUSIC_PRESETS, musicPresetByPath, type MusicCategory } from '@/lib/musicPresets';

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
  const [category,setCategory]=useState<MusicCategory>('health');
  const selectedPreset=musicPresetByPath(path);
  useEffect(() => {
    let active=true;
    Promise.all([
      supabase.from('tasks').select('bgm_path,bgm_volume,narration_volume,bgm_authorization_confirmed').eq('id',taskId).single(),
      supabase.from('stages').select('params').eq('task_id',taskId).eq('kind','image').single(),
    ]).then(([{data,error},imageStage]) => {
      if (!active) return;
      if (error) {setError('背景音乐配置读取失败，请刷新重试');return;}
      setPath(data.bgm_path || '');setVolume(Number(data.bgm_volume));setNarration(Number(data.narration_volume));setAuthorized(data.bgm_authorization_confirmed);setReady(true);
      const current=musicPresetByPath(data.bgm_path || '');
      setCategory(current?.category || (imageStage.data?.params?.production_template === 'guoxue-v1' ? 'guoxue' : 'health'));
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
    <h3>背景音乐（可选）</h3><p>可选预设音乐或上传自己的音乐。短音乐自动循环，开头和结尾淡入淡出。</p>
    <div className="bgm-controls">
      <label>音乐类别<select value={category} disabled={!ready || busy} onChange={event=>setCategory(event.target.value as MusicCategory)}><option value="guoxue">国学类</option><option value="health">健康类</option></select></label>
      <label>预设音乐<select value={selectedPreset?.category === category ? selectedPreset.id : ''} disabled={!ready || busy} onChange={event=>{const preset=MUSIC_PRESETS.find(item=>item.id===event.target.value);if(!preset)return;setPath(preset.path);setVolume(preset.defaultVolume);setAuthorized(true);setMessage('预设已选择，请试听并保存音乐设置。');}}><option value="">选择一首试听</option>{MUSIC_PRESETS.filter(item=>item.category===category).map(item=><option value={item.id} key={item.id}>{item.label} · {item.mood}</option>)}</select></label>
      {selectedPreset && <div className="bgm-preset-credit"><span>这首音乐采用 CC BY 4.0，发布视频时请在简介中署名。</span><button type="button" className="secondary-action" onClick={()=>void navigator.clipboard.writeText(selectedPreset.credit).then(()=>setMessage('署名信息已复制，可粘贴到发布简介。')).catch(()=>setError('复制失败，请手动复制下方文字'))}>复制署名</button><small>{selectedPreset.credit}</small></div>}
      <label>音乐文件<input type="file" accept=".mp3,.wav,.m4a,audio/*" disabled={!ready || busy} onChange={event=>{void upload(event.target.files?.[0]);event.currentTarget.value='';}} /></label>
      {url && <audio controls src={url} />}
      <label>背景音乐音量 {Math.round(volume*100)}%<input type="range" min="0.02" max="0.30" step="0.01" value={volume} disabled={!ready || busy} onChange={event=>{setVolume(Number(event.target.value));setMessage('有未保存修改');}} /></label>
      <label>配音音量 {narration.toFixed(2)}<input type="range" min="0.50" max="1.50" step="0.05" value={narration} disabled={!ready || busy} onChange={event=>{setNarration(Number(event.target.value));setMessage('有未保存修改');}} /></label>
      <label><input type="checkbox" checked={authorized} disabled={!path || busy || !!selectedPreset} onChange={event=>setAuthorized(event.target.checked)} />{selectedPreset ? '预设音乐已按 CC BY 4.0 授权，请按上方提示署名' : '我确认已取得该音乐的使用授权'}</label>
      <button type="button" disabled={!ready || busy} onClick={()=>void save()}>保存音乐设置</button>
      {path && <button type="button" disabled={busy} onClick={()=>void save(true)}>移除背景音乐</button>}
    </div>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
