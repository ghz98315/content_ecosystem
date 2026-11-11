"use client";
import { authenticatedFetch } from "@/lib/authenticatedFetch";
import { prepareMediaUpload } from '@/lib/prepareMediaUpload';

import { useEffect,useState } from 'react';
import { supabase } from '@/lib/supabase';
import { DEFAULT_BGM_VOLUME, MUSIC_PRESETS, musicPresetByPath, type MusicCategory } from '@/lib/musicPresets';
import { userMusicPresetMatch } from '@/lib/userMusicPresets';

export function BackgroundMusicSettings({ taskId }: { taskId: string }) {
  const [path,setPath]=useState('');
  const [url,setUrl]=useState('');
  const [volume,setVolume]=useState(DEFAULT_BGM_VOLUME);
  const [narration,setNarration]=useState(1);
  const [authorized,setAuthorized]=useState(false);
  const [ready,setReady]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [category,setCategory]=useState<MusicCategory>('health');
  const [personal, setPersonal] = useState<Array<{path:string;label:string}>>([]);
  const [saveAsPreset, setSaveAsPreset] = useState(false);
  const [presetName, setPresetName] = useState('');
  const [presetRevision, setPresetRevision] = useState(0);
  const selectedPreset=musicPresetByPath(path);
  useEffect(() => {
    let active=true;
    Promise.all([
      supabase.from('tasks').select('bgm_path,bgm_volume,narration_volume,bgm_authorization_confirmed').eq('id',taskId).single(),
      supabase.from('stages').select('params').eq('task_id',taskId).eq('kind','image').single(),
    ]).then(([{data,error},imageStage]) => {
      if (!active) return;
      if (error) {setError('背景音乐配置读取失败，请刷新重试');return;}
      setPath(data.bgm_path || '');setVolume(Number(data.bgm_volume ?? DEFAULT_BGM_VOLUME));setNarration(Number(data.narration_volume));setAuthorized(data.bgm_authorization_confirmed);setReady(true);
      const current=musicPresetByPath(data.bgm_path || '');
      const personalCategory = userMusicPresetMatch(data.bgm_path || '')?.[2] as MusicCategory | undefined;
      setCategory(current?.category || personalCategory || (imageStage.data?.params?.production_template === 'guoxue-v1' ? 'guoxue' : 'health'));
    });
    return () => {active=false;};
  },[taskId]);
  useEffect(() => {
    if (!ready) return;
    let active = true;
    setPersonal([]);
    void authenticatedFetch(`/api/background-music?category=${category}`, {cache:'no-store'})
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '个人预设读取失败');
        if (active) setPersonal(data.presets || []);
      }).catch(err => { if (active) setError(err instanceof Error ? err.message : '个人预设读取失败'); });
    return () => { active = false; };
  }, [ready, category, presetRevision]);
  useEffect(() => {
    let active=true;setUrl('');
    if (path) authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(path)}`).then(r=>r.json()).then(data=>{if(active)setUrl(data.signedUrl || '');}).catch(()=>{if(active)setError('音乐试听地址读取失败');});
    return () => {active=false;};
  },[path]);
  async function upload(file: File | undefined) {
    if (!file) return;
    const extension=file.name.split('.').pop()?.toLowerCase();
    if (!['mp3','wav','m4a'].includes(extension || '') || file.size<=0) {setError('请选择有效的MP3、WAV或M4A音乐');return;}
    setBusy(true);setError('');setMessage('');
    try {
      const uploadFile=await prepareMediaUpload(file,'bgm',setMessage);
      const label = presetName.trim() || file.name.replace(/\.[^.]+$/, '');
      const response=await authenticatedFetch('/api/background-music',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({taskId,name:uploadFile.name,size:uploadFile.size,preset:saveAsPreset,category,label})});
      const prepared=await response.json();
      if(!response.ok)throw new Error(prepared.error || '准备音乐上传失败');
      const next=prepared.path;
      const {error}=await supabase.storage.from('artifacts').uploadToSignedUrl(next,prepared.token,uploadFile,{contentType:uploadFile.type || 'audio/mpeg'});
      if(error)throw error;
      setPath(next);setVolume(DEFAULT_BGM_VOLUME);setAuthorized(false);
      if (saveAsPreset) setPresetRevision(value => value + 1);
      setMessage(saveAsPreset ? '已上传到个人预设库。确认授权并保存，即可用于当前任务。' : '音乐已上传，请试听并保存音乐设置。');
    } catch(err) {setError(err instanceof Error?err.message:'音乐上传失败');}
    finally {setBusy(false);}
  }
  async function save(remove=false, rerender=false) {
    setBusy(true);setError('');setMessage('');
    try {
      if(!remove && path && !authorized)throw new Error('请确认音乐使用授权后保存');
      const {data:render,error:readError}=await supabase.from('stages').select('id,status').eq('task_id',taskId).eq('kind','render').single();
      if(readError)throw readError;
      if(render.status==='processing')throw new Error('视频正在合成，请完成后再修改音乐');
      const {error}=await supabase.from('tasks').update({bgm_path:remove?null:path || null,bgm_volume:volume,narration_volume:narration,bgm_authorization_confirmed:remove?false:authorized}).eq('id',taskId);
      if(error)throw error;
      if(remove){setPath('');setAuthorized(false);}
      if(rerender && ['done','failed','needs_review'].includes(render.status)) {
        const {error:rerunError}=await supabase.rpc('rerun_stage',{p_stage_id:render.id});
        if(rerunError)throw new Error(`配乐已保存，但重新成片未启动：${rerunError.message}`);
        setMessage('配乐已保存并重新排队成片；沿用现有素材、配音与字幕。');
      } else setMessage(render.status==='done'?'已保存，重新成片后应用音乐设置。':'已保存，将在成片时加入音乐。');
    } catch(err) {setError(err instanceof Error?err.message:'音乐设置保存失败');}
    finally {setBusy(false);}
  }
  return <section className="bgm-settings" aria-label="背景音乐设置">
    <h3>背景音乐（可选）</h3><p>这里选择的是配音后面的音乐，不会替换或修改已上传的人声。短音乐会自动循环，片头和片尾淡入淡出。</p>
    <div className="bgm-controls">
      <div className="bgm-section-heading"><strong>选择背景音乐</strong><small>内置曲目由工作台提供；个人预设是你上传并保存在本账号的曲目。两种音乐选中后都用于当前任务。</small></div>
      <label>音乐类别<select value={category} disabled={!ready || busy} onChange={event=>setCategory(event.target.value as MusicCategory)}><option value="guoxue">国学类</option><option value="health">健康类</option></select></label>
      <label>选择音乐<select value={(selectedPreset?.category === category || personal.some(item => item.path === path)) ? path : ''} disabled={!ready || busy} onChange={event => {
        const next=event.target.value;
        if (!next) return;
        const preset=musicPresetByPath(next);
        setPath(next);setVolume(DEFAULT_BGM_VOLUME);setAuthorized(Boolean(preset && !preset.userProvided));
        setMessage(preset ? '内置音乐已选择，请试听并保存。' : '个人预设已选择，请确认授权后保存。');
      }}><option value="">选择一首试听</option><optgroup label="工作台内置音乐">{MUSIC_PRESETS.filter(item=>item.category===category).map(item=><option value={item.path} key={item.id}>{item.label} · {item.mood}</option>)}</optgroup>{personal.length > 0 && <optgroup label="我的预设音乐">{personal.map(item => <option key={item.path} value={item.path}>{item.label}</option>)}</optgroup>}</select></label>
      {selectedPreset && <div className="bgm-preset-credit"><span>{selectedPreset.userProvided ? '用户提供音乐，请按实际授权范围使用。' : '这首音乐采用 CC BY 4.0，发布视频时请在简介中署名。'}</span><button type="button" className="secondary-action" onClick={()=>void navigator.clipboard.writeText(selectedPreset.credit).then(()=>setMessage('音乐信息已复制。')).catch(()=>setError('复制失败，请手动复制下方文字'))}>复制音乐信息</button><small>{selectedPreset.credit}</small></div>}
      <label>上传自己的背景音乐<input type="file" accept=".mp3,.wav,.m4a,audio/*" disabled={!ready || busy} onChange={event=>{void upload(event.target.files?.[0]);event.currentTarget.value='';}} /></label>
      <label><input type="checkbox" checked={saveAsPreset} disabled={!ready || busy} onChange={event => setSaveAsPreset(event.target.checked)} />上传到个人预设库，供其他任务使用</label>
      {saveAsPreset && <label>预设名称 <input value={presetName} maxLength={36} disabled={busy} placeholder="默认使用文件名" onChange={event => setPresetName(event.target.value)} /></label>}
      {url && <audio controls src={url} />}
      <div className="bgm-section-heading"><strong>调节混音音量</strong><small>背景音乐是陪衬；配音是人声。两项音量只在合成视频时生效，不会改动原始音频文件。</small></div>
      <label>背景音乐音量 {Math.round(volume*100)}%<input type="range" min="0.02" max="0.30" step="0.01" value={volume} disabled={!ready || busy} onChange={event=>{setVolume(Number(event.target.value));setMessage('有未保存修改');}} /></label>
      <label>人声配音音量 {Math.round(narration*100)}%<input type="range" min="0.50" max="1.50" step="0.05" value={narration} disabled={!ready || busy} onChange={event=>{setNarration(Number(event.target.value));setMessage('有未保存修改');}} /></label>
      <label><input type="checkbox" checked={authorized} disabled={!path || busy || Boolean(selectedPreset && !selectedPreset.userProvided)} onChange={event=>setAuthorized(event.target.checked)} />{selectedPreset && !selectedPreset.userProvided ? '预设音乐已按 CC BY 4.0 授权，请按上方提示署名' : '我确认已取得该音乐的使用授权'}</label>
      <button type="button" disabled={!ready || busy} onClick={()=>void save()}>保存音乐设置</button>
      <button type="button" disabled={!ready || busy} onClick={()=>void save(false,true)}>保存配乐并重新成片</button>
      {path && <button type="button" disabled={busy} onClick={()=>void save(true)}>移除背景音乐</button>}
    </div>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
