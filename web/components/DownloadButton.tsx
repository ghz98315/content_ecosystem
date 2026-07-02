"use client";
import { useState } from "react";
import { supabase } from "@/lib/supabase";

const BUCKET = "artifacts";

/** 成片下载按钮：从 Storage 生成签名链接触发下载。 */
export function DownloadButton({
  storagePath,
  label = "下载成片",
}: {
  storagePath: string;
  label?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const download = async () => {
    setBusy(true);
    setErr(null);
    try {
      const { data, error } = await supabase.storage
        .from(BUCKET)
        .createSignedUrl(storagePath, 600); // 10 分钟有效
      if (error || !data?.signedUrl) throw error ?? new Error("获取下载链接失败");
      const a = document.createElement("a");
      a.href = data.signedUrl;
      a.download = "final.mp4";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 16 }}>
      <button style={S.btn} onClick={download} disabled={busy}>
        {busy ? "生成链接中…" : `⬇ ${label}`}
      </button>
      {err && <p style={{ color: "#dc2626", fontSize: 12, marginTop: 4 }}>{err}</p>}
    </div>
  );
}

const S: React.CSSProperties & { btn: React.CSSProperties } = {
  btn: {
    padding: "10px 28px",
    background: "#16a34a",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    cursor: "pointer",
    fontSize: 15,
    fontWeight: 600,
  },
} as { btn: React.CSSProperties };
