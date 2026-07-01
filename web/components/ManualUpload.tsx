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
      const isAudio = file.type.startsWith("audio");
      const ext = file.name.split(".").pop() || (isAudio ? "mp3" : "mp4");
      const path = `${taskId}/manual.${ext}`;
      const { error: upErr } = await supabase.storage
        .from(BUCKET)
        .upload(path, file, { upsert: true });
      if (upErr) throw upErr;

      // 写 params + 推回 pending，worker 会走 manual_file 分支
      const { error: dbErr } = await supabase
        .from("stages")
        .update({
          status: "pending",
          error: null,
          params: {
            ...(stage.params || {}),
            manual_file: path,
            manual_is_audio: isAudio,
            manual_title: title || null,
            manual_author: author || null,
          },
        })
        .eq("id", stage.id);
      if (dbErr) throw dbErr;
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

const S: Record<string, React.CSSProperties> = {
  box: { background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: 12, marginTop: 8 },
  input: { flex: 1, padding: "6px 10px", border: "1px solid #d1d5db", borderRadius: 5, fontSize: 13 },
  btn: { marginTop: 6, padding: "6px 14px", background: "#d97706", color: "#fff", border: "none", borderRadius: 5, cursor: "pointer", fontSize: 13 },
};
