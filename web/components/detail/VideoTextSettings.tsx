"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { authenticatedFetch } from '@/lib/authenticatedFetch';
import { resolveVideoText, validateVideoText, VideoText } from '@/lib/videoText';

export type VideoTextSettingsHandle = {saveForRewrite:(requireHistoryCover:boolean)=>Promise<VideoText|null>};
const fields = [
  { key: "title", label: "画面主标题", max: 32, hint: "建议6至12字，显示在图片上方" },
  { key: "subtitle", label: "画面副标题", max: 48, hint: "与图片上边缘留一行间距" },
  { key: "footnote", label: "右下脚注", max: 60, hint: "显示在图片下方右侧，留一行间距" },
] as const;

export const VideoTextSettings = forwardRef<VideoTextSettingsHandle,{taskId:string;showRerender?:boolean;renderStatus?:string;disabled?:boolean;historyCover?:boolean;legacyTitle?:string;legacySubtitle?:string}>(function VideoTextSettings({ taskId, showRerender = false, renderStatus, disabled=false, historyCover=false,legacyTitle,legacySubtitle },ref) {
  const [value, setValue] = useState<VideoText>({ title: "", subtitle: "", footnote: "读书分享", account_name: "" });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [scene, setScene] = useState(false);
  const [health,setHealth]=useState(false);
  const [options, setOptions] = useState<Array<{title:string;subtitle:string}>>([]);
  const dirty = useRef(false);
  const loadedText = useRef('null');
  const loadedTask = useRef(taskId);

  useEffect(() => {
    const changed = (event: Event) => {
      if ((event as CustomEvent).detail?.taskId !== taskId) return;
      if (!dirty.current) setReload(value => value + 1);
      else setError('其他节点已更新画面文字，请重新读取后再编辑，避免覆盖新设置。');
    };
    window.addEventListener('video-text-saved', changed);
    return () => window.removeEventListener('video-text-saved', changed);
  }, [taskId]);

  useEffect(() => {
    if(loadedTask.current===taskId&&dirty.current)return;
    loadedTask.current=taskId;
    let active = true;
    setReady(false); setError(""); setMessage("");
    (async () => {
      const { data, error: loadError } = await supabase.from("stages").select("params").eq("task_id", taskId).eq("kind", "render").single();
      if (!active) return;
      if (loadError) { setError("画面文字读取失败，请刷新后重试"); return; }
      const params = data.params || {};
      const isScene = params.production_template === 'scene-v1';
      setHealth(params.production_template==='health-v1'||(!params.production_template&&params.content_line==='health'));
      setScene(isScene); setOptions([]);
      const saved = params.video_text;
      loadedText.current = JSON.stringify(saved ?? null);
      dirty.current = false;
      if (saved) {
        setValue(resolveVideoText(params));
      } else {
        const { data: rewrite } = await supabase.from("stages").select("params").eq("task_id", taskId).eq("kind", "rewrite").single();
        if (!active) return;
        if (rewrite == null) { setError('兼容标题读取失败，请重新读取后再确认'); return; }
        let bookInfo:Record<string,unknown>={};
        if (params.production_template==='health-v1') {
          const {data:bookStage}=await supabase.from('stages').select('output_ref').eq('task_id',taskId).eq('kind','book').single();
          if(bookStage?.output_ref){
            try {
              const link=await authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(bookStage.output_ref)}`);
              if(link.ok){const {signedUrl}=await link.json();const result=await fetch(signedUrl);if(result.ok)bookInfo=await result.json();}
            } catch { /* The preset still works without book metadata. */ }
          }
        }
        if (!active) return;
        setValue(resolveVideoText(params,{cover_title:legacyTitle,cover_subtitle:legacySubtitle,...(rewrite.params || {}),...bookInfo}));
      }
      if (isScene) {
        const {data: records} = await supabase.from('artifacts').select('meta').eq('task_id',taskId).in('type',['rewrite','scene_visual_plan']).order('created_at',{ascending:false}).limit(8);
        if (!active) return;
        const candidates = records?.map(record=>record.meta?.cover_options).find(items=>Array.isArray(items)&&items.length===3) || [];
        setOptions(candidates);
        if (!saved && candidates.length && !dirty.current) {
          setValue(previous=>({...previous,title:candidates[0].title,subtitle:candidates[0].subtitle}));
          dirty.current = true;
        }
      }
      setReady(true);
    })().catch(() => { if (active) setError("画面文字读取失败，请刷新后重试"); });
    return () => { active = false; };
  }, [taskId, reload,legacyTitle,legacySubtitle]);

  useImperativeHandle(ref,()=>({saveForRewrite:(required)=>save(false,required,true)}));

  async function save(rerender = false, requireHistoryCover = false, skipUnchanged = false):Promise<VideoText|null> {
    setBusy(true); setError(""); setMessage("");
    try {
      if (!ready) throw new Error('画面文字尚未读取完成，请稍后重试');
      const text = validateVideoText(value,requireHistoryCover,health);
      if(skipUnchanged&&!dirty.current&&!requireHistoryCover)return text;
      const { data: current, error: readError } = await supabase.from("stages").select("id,params,status,updated_at").eq("task_id", taskId).eq("kind", "render").single();
      if (readError || !current) throw new Error("读取成片设置失败，请重试");
      if (current.status === "processing") throw new Error("正在合成视频，请等本次合成完成后再保存");
      if (JSON.stringify(current.params?.video_text ?? null) !== loadedText.current) throw new Error('画面文字已在其他节点更新，请重新读取后再编辑。');
      const { data: updated, error: saveError } = await supabase.from("stages").update({ params: { ...current.params, video_text: text } }).eq("id", current.id).eq("updated_at", current.updated_at).neq("status", "processing").select("id");
      if (saveError) throw new Error(saveError.message);
      if (!updated?.length) throw new Error("任务状态刚刚发生变化，请重新保存");
      setValue(text);
      loadedText.current = JSON.stringify(text);
      dirty.current = false;
      window.dispatchEvent(new CustomEvent('video-text-saved', { detail: { taskId } }));
      if (rerender) {
        const { error: rerunError } = await supabase.rpc('rerun_stage', { p_stage_id: current.id });
        if (rerunError) throw new Error(`文字已保存，但重新成片未启动：${rerunError.message}。可稍后再次点击。`);
        setMessage('文字已保存，已排队重新成片；复用现有图片、配音与字幕，不重新生图。');
      } else {
        setMessage(current.status === "done" ? "文字已保存，但当前视频尚未更新；重新成片后生效。" : "已保存，将用于后续成片。" );
      }
      return text;
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败，请重试"); return null; }
    finally { setBusy(false); }
  }

  return <section className="book-info-panel" aria-label="成片画面文字" style={{ margin: "16px 0", padding: 16 }}>
    <h3>{scene ? '封面文字与全片脚注' : '成片画面文字'}</h3>
    <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>成片后仍可修改。改写、信息设置与成片页共用同一份设置；留空并保存可隐藏对应文字。保存设置不会直接改变已有视频，重新成片后生效。</p>
    {ref && <p style={{fontSize:13,color:'var(--text-secondary)'}}>确认改写稿时会一并保存此处文字，无需重复填写。{historyCover?'历史类主标题和副标题也用于开头封面，确认正文时必填，分别不超过24字和36字。':''}</p>}
    {scene && <p>主副标题仅在开头0.5秒封面显示；脚注从第一帧持续到最后。封面底图独立生成，发布时可下载静态封面。</p>}
    {scene && options.length > 0 && <div className="external-actions">{options.map((item,index)=><button key={index} type="button" className="secondary-action" disabled={disabled||busy||!ready||renderStatus==='processing'} onClick={()=>{dirty.current=true;setValue(previous=>({...previous,...item}));setMessage('已选方案，请保存文字');}}>方案{index+1}：{item.title} / {item.subtitle}</button>)}</div>}
    {fields.map(field => <label key={field.key} style={{ display: "block", margin: "12px 0", fontSize: 13 }}>
      {health&&field.key==='footnote'?'居中脚注':scene ? field.key==='title'?'封面主标题':field.key==='subtitle'?'封面副标题':'全片脚注' : field.label}
      {health&&field.key==='footnote'?<textarea aria-label="居中脚注" rows={3} disabled={disabled||!ready||busy||renderStatus==='processing'} value={value.footnote} maxLength={80} onChange={event=>{dirty.current=true;setValue(previous=>({...previous,footnote:event.target.value}));setMessage('有未保存修改，请保存');}} placeholder="图片下方居中，按回车分行" style={{display:'block',width:'100%',boxSizing:'border-box',padding:'8px 10px',marginTop:6}}/>:<input aria-label={field.label} disabled={disabled || !ready || busy || renderStatus === 'processing'} value={value[field.key]} maxLength={field.max} onChange={event => { dirty.current = true; setValue(previous => ({ ...previous, [field.key]: event.target.value })); setMessage("有未保存修改，请保存，或在确认改写稿时一并保存。"); }} placeholder={scene ? field.key==='footnote'?'图片由AI生成':'仅显示在0.5秒封面上' : field.hint} style={{ display: "block", width: "100%", boxSizing: "border-box", padding: "8px 10px",marginTop: 6 }} />}
      <small style={{ color: "var(--text-secondary)" }}>{health&&field.key==='footnote'?'图片下方居中，留一行间距；回车换行，最多4行、共80字':scene ? field.key==='footnote'?'底部安全区域，全片持续显示':field.key==='title'?'封面中央，黄色字、红色描边':'封面主标题下方，白字、黑色描边' : field.hint}</small>
    </label>)}
    <label style={{ display: "block", margin: "12px 0", fontSize: 13 }}>画面右下角账号标签
      <input aria-label="画面右下角账号标签" disabled={disabled || !ready || busy || renderStatus === 'processing'} value={value.account_name} maxLength={25} onChange={event => { dirty.current = true; setValue(previous => ({ ...previous, account_name: event.target.value })); setMessage('有未保存修改，请保存'); }} placeholder="@账号名称，留空则隐藏" style={{ display: 'block', width: '100%', boxSizing: 'border-box', padding: '8px 10px', marginTop: 6 }} />
      <small style={{ color: 'var(--text-secondary)' }}>显示在视频画面内部右下角，全片持续；国学和健康类已预设，可修改或清空。</small>
    </label>
    <div className="external-actions">
      <button type="button" className="secondary-action" disabled={disabled || !ready || busy || renderStatus === 'processing'} onClick={() => void save(false)}>{busy ? "提交中…" : "仅保存文字"}</button>
      <button type="button" className="secondary-action" disabled={disabled || busy} onClick={() => { dirty.current = false; setReload(value => value + 1); }}>重新读取已保存文字</button>
      {showRerender && <button type="button" className="primary-action" disabled={disabled || !ready || busy || renderStatus === 'processing'} onClick={() => void save(true)}>{busy ? '提交中…' : '保存并重新成片'}</button>}
    </div>
    {showRerender && <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{renderStatus === 'processing' ? '本次成片正在处理，请完成后再修改文字。' : '只重跑成片节点，复用图片、配音、字幕及背景音乐；字体、颜色和布局沿用当前模板。'}</p>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" style={{ color: "var(--status-failed)" }}>{error}</p>}
  </section>;
});
