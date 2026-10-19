"use client";

import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

type VideoText = { title: string; subtitle: string; footnote: string };
const fields = [
  { key: "title", label: "画面主标题", max: 32, hint: "建议6至12字，显示在图片上方" },
  { key: "subtitle", label: "画面副标题", max: 48, hint: "与图片上边缘留一行间距" },
  { key: "footnote", label: "右下脚注", max: 60, hint: "显示在图片下方右侧，留一行间距" },
] as const;

export function VideoTextSettings({ taskId, showRerender = false, renderStatus }: { taskId: string; showRerender?: boolean; renderStatus?: string }) {
  const [value, setValue] = useState<VideoText>({ title: "", subtitle: "", footnote: "读书分享" });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const dirty = useRef(false);
  const loadedText = useRef('null');

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
    let active = true;
    setReady(false); setError(""); setMessage("");
    (async () => {
      const { data, error: loadError } = await supabase.from("stages").select("params").eq("task_id", taskId).eq("kind", "render").single();
      if (!active) return;
      if (loadError) { setError("画面文字读取失败，请刷新后重试"); return; }
      const params = data.params || {};
      const saved = params.video_text;
      loadedText.current = JSON.stringify(saved ?? null);
      dirty.current = false;
      if (saved) {
        setValue({ title: String(saved.title ?? ""), subtitle: String(saved.subtitle ?? ""), footnote: String(saved.footnote ?? "") });
      } else {
        const { data: rewrite } = await supabase.from("stages").select("params").eq("task_id", taskId).eq("kind", "rewrite").single();
        if (!active) return;
        setValue({ title: String(params.main_title ?? rewrite?.params?.cover_title ?? ""), subtitle: String(params.subtitle ?? rewrite?.params?.cover_subtitle ?? ""), footnote: String(params.footnote ?? "读书分享") });
      }
      setReady(true);
    })().catch(() => { if (active) setError("画面文字读取失败，请刷新后重试"); });
    return () => { active = false; };
  }, [taskId, reload]);

  async function save(rerender = false) {
    setBusy(true); setError(""); setMessage("");
    try {
      const text = Object.fromEntries(fields.map(field => [field.key, value[field.key].trim()])) as VideoText;
      for (const field of fields) if (text[field.key].length > field.max || /[\r\n]/.test(text[field.key])) throw new Error(`${field.label}请填写不超过${field.max}字的单行文字`);
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
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败，请重试"); }
    finally { setBusy(false); }
  }

  return <section className="book-info-panel" aria-label="成片画面文字" style={{ margin: "16px 0", padding: 16 }}>
    <h3>成片画面文字</h3>
    <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>成片后仍可修改。改写、书籍信息与成片页共用同一份设置；留空并保存可隐藏对应文字。保存设置不会直接改变已有视频，重新成片后生效。</p>
    {fields.map(field => <label key={field.key} style={{ display: "block", margin: "12px 0", fontSize: 13 }}>
      {field.label}
      <input aria-label={field.label} disabled={!ready || busy || renderStatus === 'processing'} value={value[field.key]} maxLength={field.max} onChange={event => { dirty.current = true; setValue(previous => ({ ...previous, [field.key]: event.target.value })); setMessage("有未保存修改，请保存后重新成片。"); }} placeholder={field.hint} style={{ display: "block", width: "100%", boxSizing: "border-box", padding: "8px 10px", marginTop: 6 }} />
      <small style={{ color: "var(--text-secondary)" }}>{field.hint}</small>
    </label>)}
    <div className="external-actions">
      <button type="button" className="secondary-action" disabled={!ready || busy || renderStatus === 'processing'} onClick={() => void save(false)}>{busy ? "提交中…" : "仅保存文字"}</button>
      <button type="button" className="secondary-action" disabled={busy} onClick={() => { dirty.current = false; setReload(value => value + 1); }}>重新读取已保存文字</button>
      {showRerender && <button type="button" className="primary-action" disabled={!ready || busy || renderStatus === 'processing'} onClick={() => void save(true)}>{busy ? '提交中…' : '保存并重新成片'}</button>}
    </div>
    {showRerender && <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{renderStatus === 'processing' ? '本次成片正在处理，请完成后再修改文字。' : '只重跑成片节点，复用图片、配音、字幕及背景音乐；字体、颜色和布局沿用当前模板。'}</p>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" style={{ color: "var(--status-failed)" }}>{error}</p>}
  </section>;
}
