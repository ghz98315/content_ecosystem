"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";

interface IndexEntry { index: number; path: string; sentence: string; }

export function ImageDetail({ stage, taskId, onRerun }: DetailCommon) {
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [urls,    setUrls]    = useState<Record<number, string>>({});
  const [big,     setBig]     = useState<string | null>(null);

  // 1. 下载索引 JSON
  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json())
      .then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json())
      .then((d: IndexEntry[]) => Array.isArray(d) && setEntries(d))
      .catch(() => {});
  }, [stage?.output_ref]);

  // 2. 批量获取各图片的 signed URL
  useEffect(() => {
    if (!entries.length) return;
    entries.forEach(e => {
      fetch(`/api/signed-url?path=${encodeURIComponent(e.path)}`)
        .then(r => r.json())
        .then(({ signedUrl }) => setUrls(prev => ({ ...prev, [e.index]: signedUrl })))
        .catch(() => {});
    });
  }, [entries]);

  return (
    <DetailShell title="生图" stage={stage} onRerun={onRerun}>
      {entries.length > 0 ? (
        <>
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
            gap: 8, marginBottom: 8,
          }}>
            {entries.map(e => {
              const url = urls[e.index];
              return (
                <div
                  key={e.index}
                  onClick={() => url && setBig(url)}
                  title={e.sentence}
                  style={{
                    aspectRatio: "1", borderRadius: "var(--radius-md)",
                    border: "1px solid var(--border)",
                    background: "var(--bg-hover)",
                    overflow: "hidden", cursor: url ? "zoom-in" : "default",
                    transition: "opacity 0.12s ease",
                  }}
                >
                  {url
                    ? <img src={url} alt={`图片${e.index + 1}`}
                        style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                    : <div style={{
                        width: "100%", height: "100%",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 11, color: "var(--text-disabled)",
                      }}>加载中…</div>
                  }
                </div>
              );
            })}
          </div>
          <p style={{ fontSize: 12, color: "var(--text-disabled)" }}>
            共 {entries.length} 张 · 点击放大 · 悬停查看对应文案
          </p>
        </>
      ) : (
        stage?.status === "done" && (
          <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>图片加载中…</p>
        )
      )}

      {big && (
        <div
          onClick={() => setBig(null)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.72)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 100, cursor: "zoom-out",
          }}
        >
          <img src={big} alt="放大" style={{ maxWidth: "90vw", maxHeight: "90vh", borderRadius: 8 }} />
        </div>
      )}
    </DetailShell>
  );
}
