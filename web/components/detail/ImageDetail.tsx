"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";

interface IndexEntry {
  index: number;
  path: string;
  sentence: string;
  char_count?: number;
  estimated_duration?: number;
  motion?: string;
}

export function ImageDetail({ stage, taskId, onRerun }: DetailCommon) {
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [urls,    setUrls]    = useState<Record<number, string>>({});
  const [big,     setBig]     = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // 1. 下载索引 JSON
  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json())
      .then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json())
      .then((d: IndexEntry[]) => Array.isArray(d) && setEntries(d))
      .catch(() => setLoadError("图片索引加载失败，请刷新后重试"));
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
          <div className="image-review-grid" style={{ marginBottom: 10 }}>
            {entries.map(e => {
              const url = urls[e.index];
              return (
                <button
                  type="button"
                  key={e.index}
                  onClick={() => url && setBig(url)}
                  disabled={!url}
                  title={e.sentence}
                  className="image-review-card"
                >
                  <div style={{ aspectRatio: "4 / 3", overflow: "hidden" }}>
                    {url
                      ? <img src={url} alt={`图片${e.index + 1}`}
                          style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                      : <div className="skeleton" style={{ width: "100%", height: "100%", borderRadius: 0 }} aria-label="图片加载中" />
                    }
                  </div>
                  <div className="image-caption">
                    <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 3 }}>
                      分镜 {String(e.index + 1).padStart(2, "0")} · {e.char_count ?? "—"} 字 · 约 {e.estimated_duration?.toFixed(1) ?? "—"} 秒
                    </div>
                    <div style={{ fontSize: 10, color: "var(--text-disabled)" }}>缓慢放大 · 叠化</div>
                    <div className="image-sentence">{e.sentence}</div>
                  </div>
                </button>
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

      {loadError && <p role="alert" style={{ color: "var(--status-failed)", fontSize: 12, marginTop: 8 }}>{loadError}</p>}

      {big && (
        <div
          onClick={() => setBig(null)}
          className="media-dialog"
          role="dialog"
          aria-modal="true"
          aria-label="图片放大预览"
        >
          <button type="button" className="media-dialog-close" aria-label="关闭图片预览" onClick={() => setBig(null)}>×</button>
          <img src={big} alt="放大" style={{ maxWidth: "90vw", maxHeight: "90vh", borderRadius: 8 }} />
        </div>
      )}
    </DetailShell>
  );
}
