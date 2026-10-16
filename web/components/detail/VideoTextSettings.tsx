"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

type VideoText = { title: string; subtitle: string; footnote: string };
const fields = [
  { key: "title", label: "画面主标题", max: 32, hint: "建议6至12字，显示在图片上方" },
  { key: "subtitle", label: "画面副标题", max: 48, hint: "与图片上边缘留一行间距" },
  { key: "footnote", label: "右下脚注", max: 60, hint: "显示在图片下方右侧，留一行间距" },
] as const;

export function VideoTextSettings({ taskId }: { taskId: string }) {
  const [value, setValue] = useState<VideoText>({ title: "", subtitle: "", footnote: "读书分享" });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setReady(false); setError(""); setMessage("");
    (async () => {
      const { data, error: loadError } = await supabase.from("stages").select("params").eq("task_id", taskId).eq("kind", "render").single();
      if (!active) return;
      if (loadError) { setError("画面文字读取失败，请刷新后重试"); return; }
      const params = data.params || {};
      const saved = params.video_text;
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
  }, [taskId]);

  async function save() {
    setBusy(true); setError(""); setMessage("");
    try {
      const text = Object.fromEntries(fields.map(field => [field.key, value[field.key].trim()])) as VideoText;
      for (const field of fields) if (text[field.key].length > field.max || /[\r\n]/.test(text[field.key])) throw new Error(`${field.label}请填写不超过${field.max}字的单行文字`);
      const { data: current, error: readError } = await supabase.from("stages").select("id,params,status,updated_at").eq("task_id", taskId).eq("kind", "render").single();
      if (readError || !current) throw new Error("读取成片设置失败，请重试");
      if (current.status === "processing") throw new Error("正在合成视频，请等本次合成完成后再保存");
      const { data: updated, error: saveError } = await supabase.from("stages").update({ params: { ...current.params, video_text: text } }).eq("id", current.id).eq("updated_at", current.updated_at).neq("status", "processing").select("id");
      if (saveError) throw new Error(saveError.message);
      if (!updated?.length) throw new Error("任务状态刚刚发生变化，请重新保存");
      setValue(text);
      setMessage(current.status === "done" ? "已保存；重新执行成片节点后应用到视频。" : "已保存，将用于后续成片。" );
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败，请重试"); }
    finally { setBusy(false); }
  }

  return <section className="book-info-panel" aria-label="成片画面文字" style={{ margin: "16px 0", padding: 16 }}>
    <h3>成片画面文字</h3>
    <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>先保存这些文字，再继续流程。改写与书籍信息两个入口共用同一份设置；留空并保存可隐藏对应文字。</p>
    {fields.map(field => <label key={field.key} style={{ display: "block", margin: "12px 0", fontSize: 13 }}>
      {field.label}
      <input aria-label={field.label} disabled={!ready || busy} value={value[field.key]} maxLength={field.max} onChange={event => { setValue(previous => ({ ...previous, [field.key]: event.target.value })); setMessage("有未保存修改，请点击“保存画面文字”。"); }} placeholder={field.hint} style={{ display: "block", width: "100%", boxSizing: "border-box", padding: "8px 10px", marginTop: 6 }} />
      <small style={{ color: "var(--text-secondary)" }}>{field.hint}</small>
    </label>)}
    <button type="button" disabled={!ready || busy} onClick={save}>{busy ? "保存中…" : "保存画面文字"}</button>
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" style={{ color: "var(--status-failed)" }}>{error}</p>}
  </section>;
}
