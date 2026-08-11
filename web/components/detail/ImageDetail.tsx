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
  source_grid?: string;
}

export function ImageDetail({ stage, taskId, onRerun }: DetailCommon) {
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [urls,    setUrls]    = useState<Record<number, string>>({});
  const [big,     setBig]     = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const providerParams = (stage?.params || {}) as Record<string, unknown>;
  const providerName = String(providerParams.image_provider || providerParams.provider || "主生图通道");
  const imageModel = String(providerParams.image_model || providerParams.model || "任务配置模型");

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
          <section className="media-workbench-heading">
            <div><p className="eyebrow">IMAGE GENERATION</p><h2>AI 场景图生成</h2><p>九宫格批量生成后切分为分镜图片，按最终文案时间轴排列。</p></div>
            <div className="media-workbench-actions"><span className="status-badge status-done">{stage?.status === "done" ? "图片已就绪" : "处理中"}</span>{stage && stage.status === "failed" && <button className="secondary-action" onClick={() => onRerun(stage.id)}>重跑失败批次</button>}</div>
          </section>
          <section className="image-workbench-summary" aria-label="图片生成摘要">
            <div><span>分镜图片</span><strong>{entries.length}</strong><small>按文案时间轴排列</small></div>
            <div><span>九宫格批次</span><strong>{new Set(entries.map(entry => entry.source_grid).filter(Boolean)).size || Math.ceil(entries.length / 9)}</strong><small>每批最多 9 个镜头</small></div>
            <div><span>预计画面时长</span><strong>{Math.round(entries.reduce((sum, entry) => sum + (entry.estimated_duration || 0), 0))}s</strong><small>跟随配音时间轴</small></div>
            <div><span>画面动效</span><strong>Zoom In</strong><small>缓慢放大与叠化</small></div>
          </section>
          <section className="image-config-strip" aria-label="当前生图配置">
            <div><span>生成模式</span><strong>3×3 九宫格切分</strong><small>每批最多 9 个分镜</small></div>
            <div><span>单图比例</span><strong>4:3</strong><small>与成片画面一致</small></div>
            <div><span>Provider</span><strong>{providerName}</strong><small>{imageModel}</small></div>
            <div><span>安全规则</span><strong>无可见文字</strong><small>违规语义转生活化类比</small></div>
          </section>
          <div className="image-workbench-toolbar">
            <div><strong>镜头与文案对应</strong><span>点击图片放大检查，卡片下方显示该镜头实际对应的字幕内容。</span></div>
            <span className="image-ready-badge">{Object.keys(urls).length}/{entries.length} 已加载</span>
          </div>
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
                    <div style={{ fontSize: 10, color: "var(--text-disabled)" }}>{e.motion === "zoom_in" || !e.motion ? "缓慢放大" : e.motion} · 叠化</div>
                    <div className="image-sentence">{e.sentence}</div>
                  </div>
                </button>
              );
            })}
          </div>
          <p className="capability-note">共 {entries.length} 张 · 当前版本按完整九宫格批次生成并切分。<span>后续能力：镜头级提示词编辑、单图重生成和违规替换记录，需要 Worker 镜头级任务接口后开放。</span></p>
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
