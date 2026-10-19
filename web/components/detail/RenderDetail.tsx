"use client";
import { authenticatedFetch } from "@/lib/authenticatedFetch";

import { BackgroundMusicSettings } from "./BackgroundMusicSettings";
import { VideoTextSettings } from "./VideoTextSettings";
import { PublicationPanel } from "./PublicationPanel";
import { PRODUCTION_TEMPLATES } from "@/lib/productionTemplates";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { DetailShell, TextBtn, DetailCommon } from "./_shell";

interface QualityCheck {
  id: string;
  label: string;
  status: "passed" | "warning" | "failed";
  detail: string;
}

interface QualityReport {
  version: number;
  status: "passed" | "warning" | "failed";
  generated_at: string;
  summary: { passed: number; warnings: number; failed: number };
  checks: QualityCheck[];
  metrics: {
    image_count: number;
    subtitle_count: number;
    tts_duration: number;
    video_duration: number;
    file_size: number;
  };
}
interface TimelineEntry { index: number; path?: string; sentence?: string; start?: number; end?: number; duration: number }
interface ReviewEntry { decision: string; note: string | null; created_at: string }
interface BookArtifact {
  book_name?: string;
  source_title?: string;
  source_tags?: string[];
  publish_title?: string;
  title_short?: string;
}

const QUALITY_LABEL = { passed: "通过", warning: "需复核", failed: "未通过" } as const;
const QUALITY_COLOR = { passed: "var(--status-done)", warning: "var(--status-review)", failed: "var(--status-failed)" } as const;

export function RenderDetail({ stage, taskId, task, onRerun, onApprove }: DetailCommon) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [isPreviousVideo, setIsPreviousVideo] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [bookName, setBookName] = useState("");
  const [loading, setLoading]   = useState(false);
  const [creatingRepost, setCreatingRepost] = useState(false);
  const [repostError, setRepostError] = useState<string | null>(null);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityUnavailable, setQualityUnavailable] = useState(false);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [review, setReview] = useState<ReviewEntry | null>(null);

  const router = useRouter();

  useEffect(() => {
    let active = true;
    setVideoUrl(null);
    setIsPreviousVideo(false);
    setLoading(true);
    const loadVideo = async () => {
      let path = stage?.output_ref ?? null;
      let previous = false;
      if (!path) {
        const { data } = await supabase
          .from("artifacts")
          .select("storage_path")
          .eq("task_id", taskId)
          .eq("stage_kind", "render")
          .eq("type", "final")
          .order("created_at", { ascending: false })
          .limit(1);
        path = data?.[0]?.storage_path ?? null;
        previous = Boolean(path);
      }
      if (!path) return;
      const response = await authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(path)}`);
      const { signedUrl } = await response.json();
      if (active && signedUrl) {
        setVideoUrl(signedUrl);
        setIsPreviousVideo(previous);
      }
    };
    loadVideo().catch(() => {}).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [stage?.output_ref, stage?.status, taskId]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const { data } = await supabase
          .from("artifacts")
          .select("storage_path")
          .eq("task_id", taskId)
          .eq("stage_kind", "book")
          .eq("type", "book")
          .order("created_at", { ascending: false })
          .limit(1);
        const path = data?.[0]?.storage_path;
        if (!path) return;
        const signed = await authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(path)}`).then(response => response.json());
        if (!signed.signedUrl) return;
        const book = await fetch(signed.signedUrl).then(response => response.json()) as BookArtifact;
        if (active) {
          setBookName(book.book_name?.trim() || "");
        }
      } catch {
        if (active) setBookName("");
      }
    })();
    return () => { active = false; };
  }, [taskId]);

  useEffect(() => {
    if (!stage || !["done", "failed", "needs_review"].includes(stage.status)) {
      setQuality(null);
      setQualityLoading(false);
      setQualityUnavailable(false);
      return;
    }
    let active = true;
    setQualityLoading(true);
    setQualityUnavailable(false);

    const loadQuality = async () => {
      const { data, error } = await supabase
        .from("artifacts")
        .select("storage_path")
        .eq("task_id", taskId)
        .eq("stage_kind", "render")
        .eq("type", "quality_report")
        .order("created_at", { ascending: false })
        .limit(1);
      if (error || !data?.[0]?.storage_path) {
        if (active) setQualityUnavailable(true);
        return;
      }
      const signedResponse = await authenticatedFetch(
        `/api/signed-url?path=${encodeURIComponent(data[0].storage_path)}`
      );
      const { signedUrl } = await signedResponse.json();
      if (!signedUrl) throw new Error("质检报告地址无效");
      const reportResponse = await fetch(signedUrl);
      if (!reportResponse.ok) throw new Error("质检报告读取失败");
      const report = await reportResponse.json() as QualityReport;
      if (active) setQuality(report);
    };

    loadQuality()
      .catch(() => active && setQualityUnavailable(true))
      .finally(() => active && setQualityLoading(false));
    return () => { active = false; };
  }, [stage?.status, taskId]);

  useEffect(() => {
    if (!taskId) return;
    supabase.from("render_reviews").select("decision,note,created_at").eq("task_id", taskId).order("created_at", { ascending: false }).limit(1)
      .then(({ data }) => setReview((data?.[0] || null) as ReviewEntry | null));
  }, [taskId, stage?.status]);

  useEffect(() => {
    if (!stage || !["done", "failed", "needs_review"].includes(stage.status)) { setTimeline([]); return; }
    let active = true;
    (async () => {
      try {
        const result = await supabase.from("artifacts").select("storage_path").eq("task_id", taskId).eq("stage_kind", "render").eq("type", "timeline").order("created_at", { ascending: false }).limit(1);
        const path = result.data?.[0]?.storage_path; if (!path) return;
        const signed = await authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(path)}`).then(response => response.json());
        if (!signed.signedUrl) return;
        const data = await fetch(signed.signedUrl).then(response => response.json());
        if (active && Array.isArray(data)) setTimeline(data as TimelineEntry[]);
      } catch { /* timeline is optional for older render artifacts */ }
    })();
    return () => { active = false; };
  }, [stage?.status, taskId]);

  const download = () => {
    if (!videoUrl) return;
    setDownloadBusy(true);
    setDownloadError(null);
    try {
      const link = document.createElement("a");
      // The signed source URL is already downloadable in the video player.
      // Avoid fetching the complete MP4 into a Blob before starting the download.
      link.href = videoUrl;
      const date = new Date().toISOString().slice(0, 10).replaceAll("-", "");
      const title = (bookName || task.title?.trim() || "成片").replace(/[\\\\/:*?"<>|]/g, "_");
      link.download = `${title}_${date}.mp4`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "视频下载失败，请重试");
    } finally {
      window.setTimeout(() => setDownloadBusy(false), 0);
    }
  };

  const createRepost = async () => {
    if (!window.confirm("请确认当前成片已经验证为爆款，再生成独立的二次发布版本。")) return;
    setCreatingRepost(true);
    setRepostError(null);
    const { data, error } = await supabase.rpc("create_repost_task", {
      p_source_task_id: taskId,
    });
    setCreatingRepost(false);
    if (error || !data) {
      setRepostError(error?.message || "二次发布任务创建失败");
      return;
    }
    router.push(`/task/${data}`);
  };

  const canCreateRepost = stage?.status === "done" && task.rewrite_mode !== "repost_dedup";
  const canApprove = stage?.status === "needs_review";
  const productionTemplate = PRODUCTION_TEMPLATES.find(item => item.id === stage?.params.production_template);
  const isGuoxue = productionTemplate?.id === 'guoxue-v1';

  return (
    <DetailShell
      title="成片"
      stage={stage}
      onRerun={onRerun}
      showChildrenOnPending
      errorPosition="bottom"
      errorTone="warning"
      actions={
        <>
          {videoUrl && <TextBtn variant="primary" onClick={download} disabled={downloadBusy}>{downloadBusy ? "正在下载…" : "下载视频"}</TextBtn>}
          {videoUrl && canApprove && (
            <TextBtn variant="primary" onClick={() => onApprove(stage!.id, "render")}>
              人工审核通过
            </TextBtn>
          )}
          {canCreateRepost && (
            <TextBtn onClick={createRepost} disabled={creatingRepost}>
              {creatingRepost ? "创建中…" : "生成二次发布版本"}
            </TextBtn>
          )}
        </>
      }
    >
      {repostError && (
        <div style={{
          marginBottom: 16, padding: "8px 12px", borderRadius: "var(--radius-md)",
          background: "var(--error-soft)", border: "1px solid #fecaca",
          color: "var(--status-failed)", fontSize: 12,
        }}>
          {repostError}
        </div>
      )}
      {downloadError && <p role="alert" className="bgm-error">{downloadError}</p>}
      {loading && (
        <div aria-busy="true" aria-label="正在加载成片">
          <div className="skeleton" style={{ height: 24, width: "42%", marginBottom: 10 }} />
          <div className="skeleton" style={{ height: 320, width: "100%", marginBottom: 16 }} />
        </div>
      )}

      {videoUrl && (
        <section className="render-workbench">
          <div className="render-video-panel">
            <div className="render-panel-heading"><div><strong>成片预览</strong><span>{isPreviousVideo ? "当前展示上一次成功版本" : "当前任务最新版本"}</span></div><span className="status-badge status-done">可人工检查</span></div>
            <video controls src={videoUrl} />
          </div>
          <aside className="render-preset-panel" aria-label="当前成片方案">
            <div><p className="eyebrow">当前成片方案</p><h3>{productionTemplate?.label || '历史任务方案'}</h3><p>模板随本任务固定保存，文字与背景音乐可在成片前设置。</p></div>
            <dl>
              <div><dt>画幅</dt><dd>竖版 9:16</dd></div>
              <div><dt>画面</dt><dd>{isGuoxue ? '工笔淡墨 · 4:3主体 · 模糊填充' : '独立类别画面'}</dd></div>
              <div><dt>动效</dt><dd>{isGuoxue ? '完整保留主体 · 按配音切换分镜' : '缓慢 Zoom In · 短叠化'}</dd></div>
              <div><dt>声音</dt><dd>配音与字幕时间轴对齐</dd></div>
              <div><dt>背景音乐</dt><dd>{task.bgm_path ? "已配置任务级混音" : "未配置"}</dd></div>
            </dl>
            <p className="render-preset-note">背景音乐已支持任务级配置，不会修改已经生成的历史成片。</p>
            <div className="render-future-list" aria-label="后续能力">
              <strong>后续能力</strong>
              <span>国学、健康、历史社科、经管模板分别保存</span>
              <span>背景音乐：上传后可调节音量并重新生成成片</span>
              <span>失败后保留视频：当前已支持人工检查</span>
            </div>
          </aside>
        </section>
      )}

      <VideoTextSettings taskId={taskId} showRerender renderStatus={stage?.status} />
      <PublicationPanel taskId={taskId} />

      {(qualityLoading || quality || qualityUnavailable) && (
        <section className="quality-panel" style={{ marginBottom: 24 }}>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            paddingBottom: 10, borderBottom: "1px solid var(--border)", marginBottom: 10,
          }}>
            <h3 style={{ fontSize: 14, fontWeight: 650 }}>自动质检</h3>
            {quality && (
              <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: QUALITY_COLOR[quality.status] }}>
                <span className="status-dot" style={{ background: QUALITY_COLOR[quality.status] }} />
                {QUALITY_LABEL[quality.status]}
              </span>
            )}
          </div>

          {qualityLoading && <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>正在读取质检报告…</p>}
          {qualityUnavailable && !qualityLoading && (
            <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
              该成片暂无自动质检报告，重跑成片环节后将自动生成。
            </p>
          )}
          {quality && (
            <div>
              <p style={{ color: "var(--text-secondary)", fontSize: 12, marginBottom: 8 }}>
                {quality.summary.passed} 项通过 · {quality.summary.warnings} 项需复核 · {quality.summary.failed} 项未通过
              </p>
              <div className="render-metrics" aria-label="成片指标">
                <div><strong>{quality.metrics.video_duration.toFixed(1)}s</strong><span>视频时长</span></div>
                <div><strong>{quality.metrics.image_count}</strong><span>画面镜头</span></div>
                <div><strong>{quality.metrics.subtitle_count}</strong><span>字幕条数</span></div>
                <div><strong>{(quality.metrics.file_size / 1024 / 1024).toFixed(1)} MB</strong><span>文件大小</span></div>
              </div>
              {quality.checks.map(check => (
                <div key={check.id} style={{
                  display: "grid", gridTemplateColumns: "100px minmax(0, 1fr) 58px",
                  gap: 10, alignItems: "start", padding: "7px 0",
                  borderTop: "1px solid var(--border)", fontSize: 12,
                }}>
                  <span style={{ fontWeight: 600 }}>{check.label}</span>
                  <span style={{ color: "var(--text-secondary)", overflowWrap: "anywhere" }}>{check.detail}</span>
                  <span style={{ color: QUALITY_COLOR[check.status], textAlign: "right" }}>
                    {QUALITY_LABEL[check.status]}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {timeline.length > 0 && <section className="render-timeline-panel" aria-labelledby="render-timeline-title"><div className="render-panel-heading"><div><strong id="render-timeline-title">画面与字幕时间轴</strong><span>读取本次成片实际使用的 render timeline，历史成片保持只读。</span></div><span>{timeline.length} 个镜头</span></div><div className="render-timeline-list">{timeline.map((item, index) => { const start = Number(item.start || 0); const end = Number(item.end ?? start + Number(item.duration || 0)); return <article key={`${item.index}-${index}`}><span className="render-timeline-index">{String(item.index + 1).padStart(2, "0")}</span><div><strong>{item.sentence || `镜头 ${item.index + 1}`}</strong><small>{start.toFixed(2)}s - {end.toFixed(2)}s · 持续 {Number(item.duration || end - start).toFixed(2)}s</small></div><span className="render-timeline-bar"><i style={{ width: `${Math.max(4, Math.min(100, Number(item.duration || 0) * 12))}%` }} /></span></article>; })}</div></section>}
      {review && <p className="render-review-note" role="status">最近审核：{review.decision === "approved" ? "已通过" : "要求重新生成"} · {new Date(review.created_at).toLocaleString("zh-CN", { hour12: false })}{review.note ? ` · ${review.note}` : ""}</p>}

      <BackgroundMusicSettings taskId={taskId} />

    </DetailShell>
  );
}
