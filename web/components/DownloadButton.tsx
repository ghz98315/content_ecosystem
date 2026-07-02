"use client";
import { useState } from "react";

/** 成片下载按钮：通过 API route（service_role）生成签名链接触发下载。 */
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
      const res = await fetch(`/api/signed-url?path=${encodeURIComponent(storagePath)}`);
      if (!res.ok) throw new Error("获取下载链接失败");
      const { signedUrl } = await res.json();
      const a = document.createElement("a");
      a.href = signedUrl;
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

const S = {
  btn: {
    padding: "10px 28px",
    background: "#16a34a",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    cursor: "pointer",
    fontSize: 15,
    fontWeight: 600,
  } as React.CSSProperties,
};
