"use client";
import { useState } from "react";
import { supabase } from "@/lib/supabase";
import { Stage } from "@/lib/types";

const BUCKET = "artifacts";

/** 采集失败时的手动上传兜底：上传视频/音频 + 手填元数据 → 推 ingest 回 pending。 */
export function ManualUpload({
  taskId,
  stage,
}: {
  taskId: string;
  stage: Stage;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!file) {
      setErr("请先选择文件");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session?.access_token) throw new Error("登录会话已失效，请刷新页面后重试");
      const headers = { Authorization: `Bearer ${sessionData.session.access_token}`, "Content-Type": "application/json" };
      const requestUpload = await fetch("/api/manual-upload", { method: "POST", headers, body: JSON.stringify({ taskId, stageId: stage.id, name: file.name, size: file.size, mime: file.type }) });
      const uploadInfo = await readResponse(requestUpload);
      if (!requestUpload.ok) throw new Error(uploadInfo.error || "创建上传授权失败");
      if (!uploadInfo.path || !uploadInfo.token) throw new Error("上传授权响应不完整");
      const uploadPath = uploadInfo.path;
      const { error: uploadError } = await supabase.storage.from(BUCKET).uploadToSignedUrl(uploadPath, uploadInfo.token, file, { contentType: file.type });
      if (uploadError) throw uploadError;
      const confirm = await fetch("/api/manual-upload", { method: "PATCH", headers, body: JSON.stringify({ taskId, stageId: stage.id, path: uploadPath, mime: file.type, title, author }) });
      const confirmed = await readResponse(confirm);
      if (!confirm.ok) throw new Error(confirmed.error || "上传后确认失败");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={S.box}>
      <div style={{ fontSize: 13, color: "#92400e", marginBottom: 6 }}>
        自动采集失败，可手动上传视频/音频兜底：
      </div>
      <input
        type="file"
        accept="video/*,audio/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        style={{ fontSize: 13 }}
      />
      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
        <input
          style={S.input}
          placeholder="标题（选填）"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <input
          style={S.input}
          placeholder="博主（选填）"
          value={author}
          onChange={(e) => setAuthor(e.target.value)}
        />
      </div>
      <button style={S.btn} onClick={submit} disabled={busy}>
        {busy ? "上传中…" : "上传并继续"}
      </button>
      {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 4 }}>{err}</div>}
    </div>
  );
}

async function readResponse(response: Response): Promise<{ error?: string; path?: string; token?: string }> {
  const text = await response.text();
  try { return JSON.parse(text); } catch { return { error: text.slice(0, 300) || `请求失败 (${response.status})` }; }
}

const S: Record<string, React.CSSProperties> = {
  box: { background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: 12, marginTop: 8 },
  input: { flex: 1, padding: "6px 10px", border: "1px solid #d1d5db", borderRadius: 5, fontSize: 13 },
  btn: { marginTop: 6, padding: "6px 14px", background: "#d97706", color: "#fff", border: "none", borderRadius: 5, cursor: "pointer", fontSize: 13 },
};
