"use client";

import { DragEvent, FormEvent, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { supabase } from "@/lib/supabase";
import { Task } from "@/lib/types";

const MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a"]);

export default function VoiceCloningPage() {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  useEffect(() => { supabase.from("tasks").select("*").order("created_at", { ascending: false }).limit(20).then(({ data }) => data && setTasks(data as Task[])); }, []);

  function chooseFile(next: File | null) {
    setError("");
    setUrl("");
    setCopied(false);
    if (!next) return setFile(null);
    if (!ALLOWED_TYPES.has(next.type.toLowerCase())) return setError("仅支持 MP3、WAV 或 M4A 音频");
    if (next.size > MAX_BYTES) return setError("音频文件不能超过 10 MB");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(next);
    setPreviewUrl(URL.createObjectURL(next));
  }

  function drop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0] || null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setUrl("");
    if (!file) return setError("请选择音频文件");
    setBusy(true);
    try {
      const form = new FormData();
      form.set("audio", file);
      const response = await fetch("/api/voice-sample", { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "上传失败");
      setUrl(result.signedUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell tasks={tasks}>
    <div className="voice-page">
      <div className="voice-workspace">
      <section className="voice-upload-panel">
        <p style={{ margin: "0 0 6px", color: "var(--text-secondary)", fontSize: 12 }}>VOICE ENROLLMENT</p>
        <h1 style={{ margin: "0 0 8px", fontSize: 26 }}>声音样本</h1>
        <p style={{ margin: "0 0 22px", color: "var(--text-secondary)", fontSize: 13 }}>MP3、WAV 或 M4A，建议 10–20 秒，最大 10 MB。</p>
        <form onSubmit={submit}>
          <label
            className={`voice-dropzone ${dragging ? "is-dragging" : ""}`}
            onDragOver={event => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={drop}
          >
            <input hidden type="file" accept="audio/mpeg,audio/wav,audio/mp4,audio/m4a" onChange={(e) => chooseFile(e.target.files?.[0] || null)} />
            <strong style={{ display: "block", fontSize: 14 }}>{file ? file.name : "选择或拖入音频"}</strong>
            <span style={{ display: "block", marginTop: 6, color: "var(--text-secondary)", fontSize: 12 }}>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "单人清晰朗读，无背景音乐"}</span>
          </label>
          {previewUrl && <audio controls src={previewUrl} style={{ width: "100%", marginTop: 16 }} />}
          <button type="submit" disabled={busy || !file} className="primary-action" style={{ marginTop: 18, width: "100%" }}>
            {busy ? "正在上传…" : "生成访问地址"}
          </button>
        </form>
        {error && <p role="alert" style={{ marginTop: 16, color: "var(--status-failed)", fontSize: 13 }}>{error}</p>}
        {url && <div className="voice-result"><p style={{ margin: "0 0 8px", fontWeight: 600 }}>音频访问地址</p><textarea readOnly value={url} style={{ width: "100%", minHeight: 92, padding: 10, border: "1px solid var(--border-strong)", borderRadius: 6, fontSize: 12, resize: "vertical" }} /><button type="button" className="secondary-action" style={{ marginTop: 10 }} onClick={async () => { await navigator.clipboard.writeText(url); setCopied(true); }}>{copied ? "已复制" : "复制地址"}</button></div>}
      </section>
      </div>
    </div>
    </AppShell>
  );
}
