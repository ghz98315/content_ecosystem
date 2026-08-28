"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";
import { supabase } from "@/lib/supabase";

interface IndexEntry {
  index: number;
  path: string;
  sentence: string;
  char_count?: number;
  estimated_duration?: number;
  motion?: string;
  source_grid?: string;
  prompt?: string;
  prompt_scene?: string;
  image_model?: string;
}
interface ImageReview { image_index: number; decision: "approved" | "replace_requested"; note: string | null; created_at: string }
interface ReplacementRequest { image_index: number; status: "pending" | "processing" | "done" | "failed"; replacement_path: string | null; error: string | null; requested_at: string; invalidated_at?: string | null }

export function ImageDetail({ stage, taskId, onRerun }: DetailCommon) {
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [urls,    setUrls]    = useState<Record<number, string>>({});
  const [selectedEntry, setSelectedEntry] = useState<IndexEntry | null>(null);
  const [filter, setFilter] = useState<"all" | "ready" | "missing">("all");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Record<number, ImageReview>>({});
  const [replacements, setReplacements] = useState<Record<number, ReplacementRequest>>({});
  const [reviewBusy, setReviewBusy] = useState(false);
  const [replacementRequested, setReplacementRequested] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const providerParams = (stage?.params || {}) as Record<string, unknown>;
  const [selectedProvider, setSelectedProvider] = useState<"apimart" | "xcode">(
    String(providerParams.image_provider || "apimart") === "xcode" ? "xcode" : "apimart"
  );
  const [providerBusy, setProviderBusy] = useState(false);
  const providerName = String(providerParams.image_provider || providerParams.provider || "主生图通道");
  const imageModel = String(providerParams.image_model || providerParams.model || "任务配置模型");
  const visibleEntries = entries.filter(entry => filter === "all" || (filter === "ready" ? Boolean(urls[entry.index]) : !urls[entry.index]));

  useEffect(() => {
    setSelectedProvider(String(providerParams.image_provider || "apimart") === "xcode" ? "xcode" : "apimart");
  }, [stage?.id, stage?.params]);

  const saveProviderAndRerun = async () => {
    if (!stage?.id || providerBusy) return;
    setProviderBusy(true);
    const paramsWithoutJobs = { ...providerParams };
    delete paramsWithoutJobs.image_provider_jobs;
    const { error } = await supabase.from("stages").update({
      params: { ...paramsWithoutJobs, image_provider: selectedProvider, image_model: "gpt-image-2" },
    }).eq("id", stage.id);
    if (error) {
      setLoadError(`生图通道保存失败：${error.message}`);
      setProviderBusy(false);
      return;
    }
    await onRerun(stage.id);
    setProviderBusy(false);
  };

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
      const preferredPath = replacements[e.index]?.replacement_path || e.path;
      fetch(`/api/signed-url?path=${encodeURIComponent(preferredPath)}`)
        .then(r => r.json())
        .then(({ signedUrl }) => setUrls(prev => ({ ...prev, [e.index]: signedUrl })))
        .catch(() => {});
    });
  }, [entries, replacements]);

  useEffect(() => {
    if (!taskId) return;
    supabase.from("image_reviews").select("image_index,decision,note,created_at").eq("task_id", taskId).order("created_at", { ascending: false }).then(({ data }) => {
      const next: Record<number, ImageReview> = {};
      (data || []).forEach(row => { if (next[row.image_index] === undefined) next[row.image_index] = row as ImageReview; });
      setReviews(next);
    });
  }, [taskId, stage?.id]);

  useEffect(() => {
    if (!taskId) return;
    supabase.from("image_replacement_requests").select("image_index,status,replacement_path,error,requested_at,invalidated_at").eq("task_id", taskId).is("invalidated_at", null).order("requested_at", { ascending: false }).then(({ data }) => {
      const next: Record<number, ReplacementRequest> = {};
      (data || []).forEach(row => { if (next[row.image_index] === undefined) next[row.image_index] = row as ReplacementRequest; });
      setReplacements(next);
    });
  }, [taskId, stage?.id]);

  const reviewSelected = async (decision: "approved" | "replace_requested") => {
    if (!selectedEntry || !stage?.id || reviewBusy) return;
    setReviewBusy(true);
    const { data, error } = await supabase.rpc("review_image_frame", { p_stage_id: stage.id, p_image_index: selectedEntry.index, p_decision: decision, p_note: reviewNote.trim() || null });
    setReviewBusy(false);
    if (error) { setLoadError(`镜头审核失败：${error.message}`); return; }
    if (data) setReviews(current => ({ ...current, [selectedEntry.index]: data as ImageReview }));
    setReviewNote("");
  };

  const requestReplacement = async () => {
    if (!selectedEntry || !stage?.id || replacementRequested) return;
    setReplacementRequested(true);
    const { error } = await supabase.rpc("request_image_replacement", { p_stage_id: stage.id, p_image_index: selectedEntry.index, p_note: reviewNote.trim() || null });
    setReplacementRequested(false);
    if (error) { setLoadError(`替换请求提交失败：${error.message}`); return; }
    setReplacements(current => ({ ...current, [selectedEntry.index]: { image_index: selectedEntry.index, status: "pending", replacement_path: null, error: null, requested_at: new Date().toISOString() } }));
    setLoadError(null); setReviewNote("");
  };

  const replacementReadyCount = Object.values(replacements).filter(item => item.status === "done" && item.replacement_path).length;
  const rerunDownstreamWithReplacement = async () => {
    if (!stage?.id) return;
    await onRerun(stage.id);
  };

  const regenerateAll = async () => {
    if (!stage?.id || regenerating) return;
    const confirmed = window.confirm("按当前风格全量重新生成图片？这会删除当前图片和最终成片，保留逐字稿、清洗稿、改写稿、配音及审核记录。");
    if (!confirmed) return;
    setRegenerating(true);
    setLoadError(null);
    try {
      const { data: sessionData } = await supabase.auth.getSession();
      const response = await fetch("/api/image-regeneration", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(sessionData.session?.access_token ? { Authorization: `Bearer ${sessionData.session.access_token}` } : {}),
        },
        body: JSON.stringify({ stageId: stage.id }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.stages?.length) {
        setLoadError(result.error || "全量重新生成排队失败，请检查数据库迁移是否已执行。");
        return;
      }
      setEntries([]);
      setUrls({});
      setReplacements({});
      setSelectedEntry(null);
      await new Promise(resolve => window.setTimeout(resolve, 200));
    } catch (error) {
      setLoadError(error instanceof Error ? `全量重新生成请求未送达：${error.message}` : "全量重新生成请求未送达，请检查浏览器网络后重试。");
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <DetailShell title="生图" stage={stage} onRerun={onRerun}>
      <section className="image-config-strip" aria-label="生图 Provider 选择">
        <div><span>当前通道</span><strong>{providerName}</strong><small>{imageModel}</small></div>
        <div><span>切换通道</span><select value={selectedProvider} onChange={event => setSelectedProvider(event.target.value as "apimart" | "xcode")} aria-label="切换生图 Provider"><option value="apimart">APIMart（默认）</option><option value="xcode">xcode.best（备用）</option></select><small>保存后只重跑生图及下游阶段</small></div>
        <div><button type="button" className="secondary-action" disabled={providerBusy} onClick={saveProviderAndRerun}>{providerBusy ? "正在切换…" : "保存通道并重跑"}</button></div>
      </section>
      {entries.length > 0 ? (
        <>
          <section className="media-workbench-heading">
            <div><p className="eyebrow">IMAGE GENERATION</p><h2>AI 场景图生成</h2><p>九宫格批量生成后切分为分镜图片，按最终文案时间轴排列。</p></div>
            <div className="media-workbench-actions"><span className="status-badge status-done">{stage?.status === "done" ? "图片已就绪" : "处理中"}</span>{stage?.status === "done" && <button type="button" className="secondary-action" disabled={regenerating} onClick={regenerateAll}>{regenerating ? "正在重新排队" : "按当前风格全量重新生成"}</button>}{stage && stage.status === "failed" && <button className="secondary-action" onClick={() => onRerun(stage.id)}>重跑失败批次</button>}</div>
          </section>
          <section className="image-workbench-summary" aria-label="图片生成摘要">
            <div><span>分镜图片</span><strong>{entries.length}</strong><small>按文案时间轴排列</small></div>
            <div><span>九宫格批次</span><strong>{new Set(entries.map(entry => entry.source_grid).filter(Boolean)).size || Math.ceil(entries.length / 9)}</strong><small>每批最多 9 个镜头</small></div>
            <div><span>预计画面时长</span><strong>{Math.round(entries.reduce((sum, entry) => sum + (entry.estimated_duration || 0), 0))}s</strong><small>跟随配音时间轴</small></div>
            <div><span>画面动效</span><strong>Zoom In</strong><small>缓慢放大与叠化</small></div>
          </section>
          <section className="image-config-strip" aria-label="当前生图配置">
            <div><span>生成模式</span><strong>3×3 九宫格切分</strong><small>每批最多 9 个分镜</small></div>
            <div><span>单图比例</span><strong>9:16</strong><small>与成片画面一致</small></div>
            <div><span>Provider</span><strong>{providerName}</strong><small>{imageModel}</small></div>
            <div><span>安全规则</span><strong>无可见文字</strong><small>违规语义转生活化类比</small></div>
          </section>
          <div className="image-workbench-toolbar">
            <div><strong>镜头与文案对应</strong><span>点击图片放大检查，卡片下方显示该镜头实际对应的字幕内容。</span></div>
            <div className="image-review-filters" role="tablist" aria-label="图片状态筛选">
              {([["all", "全部"], ["ready", "已加载"], ["missing", "待加载"]] as const).map(([id, label]) => <button key={id} type="button" className={filter === id ? "is-active" : ""} onClick={() => setFilter(id)} role="tab" aria-selected={filter === id}>{label} {id === "all" ? entries.length : id === "ready" ? Object.keys(urls).length : entries.length - Object.keys(urls).length}</button>)}
            </div>
          </div>
          <div className="image-review-grid" style={{ marginBottom: 10 }}>
            {visibleEntries.map(e => {
              const url = urls[e.index];
              return (
                <button
                  type="button"
                  key={e.index}
                  onClick={() => url && setSelectedEntry(e)}
                  disabled={!url}
                  title={e.sentence}
                  className="image-review-card"
                >
                  <div style={{ aspectRatio: "9 / 16", overflow: "hidden" }}>
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
                    {e.prompt && <div className="image-prompt-preview">生成提示词：{e.prompt}</div>}
                  </div>
                </button>
              );
            })}
          </div>
          {visibleEntries.length === 0 && <p className="state-panel compact">当前筛选没有对应图片。</p>}
          <p className="capability-note">共 {entries.length} 张 · 当前版本按完整九宫格批次生成并切分。<span>后续能力：镜头级提示词编辑、单图重生成和违规替换记录，需要 Worker 镜头级任务接口后开放。</span></p>
        </>
      ) : (
        stage?.status === "done" && (
          <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>图片加载中…</p>
        )
      )}

      {loadError && <p role="alert" style={{ color: "var(--status-failed)", fontSize: 12, marginTop: 8 }}>{loadError}</p>}

      {selectedEntry && urls[selectedEntry.index] && <div className="media-dialog" role="dialog" aria-modal="true" aria-label="单图检查" onClick={() => setSelectedEntry(null)}><div className="image-inspect-drawer" onClick={event => event.stopPropagation()}><button type="button" className="media-dialog-close" aria-label="关闭单图检查" onClick={() => setSelectedEntry(null)}>×</button><img src={urls[selectedEntry.index]} alt={`镜头${selectedEntry.index + 1}预览`} /><p className="eyebrow">镜头 {String(selectedEntry.index + 1).padStart(2, "0")}</p><h3>{selectedEntry.sentence}</h3><dl><div><dt>预计时长</dt><dd>{selectedEntry.estimated_duration?.toFixed(1) || "—"} 秒</dd></div><div><dt>字数</dt><dd>{selectedEntry.char_count ?? "—"}</dd></div><div><dt>动效</dt><dd>{selectedEntry.motion || "zoom_in"}</dd></div><div><dt>来源批次</dt><dd>{selectedEntry.source_grid || "—"}</dd></div></dl>{selectedEntry.prompt && <section className="image-prompt-full"><strong>实际生成提示词</strong><pre>{selectedEntry.prompt}</pre></section>}<p className={`image-review-decision ${reviews[selectedEntry.index]?.decision === "approved" ? "is-approved" : reviews[selectedEntry.index] ? "is-replace" : ""}`}>{reviews[selectedEntry.index] ? (reviews[selectedEntry.index].decision === "approved" ? "最近审核：通过" : "最近审核：要求替换") : "尚未审核"}</p>{replacements[selectedEntry.index] && <p className={`image-replacement-state status-${replacements[selectedEntry.index].status}`}>替换请求：{replacements[selectedEntry.index].status === "pending" ? "等待处理" : replacements[selectedEntry.index].status === "processing" ? "处理中" : replacements[selectedEntry.index].status === "done" ? "已生成新版本" : `失败 · ${replacements[selectedEntry.index].error || "请重试"}`}</p>}<textarea className="image-review-note-input" value={reviewNote} onChange={event => setReviewNote(event.target.value)} placeholder="可选：记录画面问题或通过依据" aria-label="镜头审核备注" /><div className="image-review-actions"><button type="button" className="secondary-action" disabled={reviewBusy} onClick={() => reviewSelected("replace_requested")}>记录替换意见</button><button type="button" className="secondary-action" disabled={replacementRequested} onClick={requestReplacement}>{replacementRequested ? "提交中…" : "提交重生成请求"}</button><button type="button" className="primary-action" disabled={reviewBusy} onClick={() => reviewSelected("approved")}>确认通过</button></div><p className="capability-note">提交请求后由 Worker 生成新版本；当前图片和历史成片保持不变。</p></div></div>}
    </DetailShell>
  );
}
