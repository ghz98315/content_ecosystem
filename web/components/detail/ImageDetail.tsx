"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";

export function ImageDetail({ stage, taskId, onRerun, onApprove }: DetailCommon) {
  const [urls, setUrls] = useState<string[]>([]);
  const [big, setBig]   = useState<string | null>(null);

  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json()).then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json())
      .then((d: { images?: string[] }) => {
        if (d.images) setUrls(d.images);
      })
      .catch(() => {});
  }, [stage?.output_ref]);

  return (
    <DetailShell title="生图" stage={stage} onRerun={onRerun}>
      {urls.length > 0 ? (
        <>
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
            gap: 8, marginBottom: 12,
          }}>
            {urls.map((u, i) => (
              <img
                key={i} src={u} alt={`图片${i + 1}`}
                onClick={() => setBig(u)}
                style={{
                  width: "100%", aspectRatio: "1", objectFit: "cover",
                  borderRadius: "var(--radius-md)", cursor: "zoom-in",
                  border: "1px solid var(--border)",
                  transition: "opacity 0.12s ease",
                }}
              />
            ))}
          </div>
          <p style={{ fontSize: 12, color: "var(--text-disabled)" }}>点击图片放大</p>
        </>
      ) : (
        stage?.status === "done" && (
          <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>图片加载中…</p>
        )
      )}

      {/* 放大灯箱 */}
      {big && (
        <div
          onClick={() => setBig(null)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 100, cursor: "zoom-out",
          }}
        >
          <img src={big} style={{ maxWidth: "90vw", maxHeight: "90vh", borderRadius: 8 }} />
        </div>
      )}
    </DetailShell>
  );
}
