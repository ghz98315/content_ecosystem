"use client";

import { FormEvent, useState } from "react";

export default function VoiceCloningPage() {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
    <main style={{ minHeight: "100vh", background: "#f6f7f9", padding: "48px 20px", color: "#18202a" }}>
      <section style={{ maxWidth: 680, margin: "0 auto", background: "#fff", border: "1px solid #e2e6eb", borderRadius: 8, padding: 32 }}>
        <p style={{ margin: "0 0 8px", color: "#667085", fontSize: 14 }}>VOICE ENROLLMENT</p>
        <h1 style={{ margin: "0 0 12px", fontSize: 28 }}>声音复刻音频上传</h1>
        <p style={{ margin: "0 0 24px", color: "#667085", lineHeight: 1.7 }}>上传完成后生成临时公网下载地址，用于百炼创建复刻音色。文件不会直接暴露 Supabase 密钥。</p>
        <form onSubmit={submit}>
          <label style={{ display: "block", border: "1px dashed #b9c1cc", borderRadius: 6, padding: 24, cursor: "pointer" }}>
            <input type="file" accept="audio/mpeg,audio/wav,audio/mp4,audio/m4a" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <span style={{ display: "block", marginTop: 12, color: "#667085" }}>{file ? file.name : "选择 MP3、WAV 或 M4A（不超过 10 MB）"}</span>
          </label>
          <button type="submit" disabled={busy} style={{ marginTop: 20, width: "100%", border: 0, borderRadius: 6, padding: "12px 16px", background: busy ? "#98a2b3" : "#1769e0", color: "#fff", cursor: busy ? "wait" : "pointer" }}>
            {busy ? "正在上传" : "生成音频访问地址"}
          </button>
        </form>
        {error && <p style={{ marginTop: 16, color: "#b42318" }}>{error}</p>}
        {url && <div style={{ marginTop: 24 }}><p style={{ margin: "0 0 8px", fontWeight: 600 }}>可提交给百炼的音频 URL</p><textarea readOnly value={url} style={{ width: "100%", minHeight: 96, padding: 10, border: "1px solid #d0d5dd", borderRadius: 6, fontSize: 12 }} /></div>}
      </section>
    </main>
  );
}
