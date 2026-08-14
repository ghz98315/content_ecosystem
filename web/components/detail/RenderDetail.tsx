"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { DetailShell, TextBtn, DetailCommon } from "./_shell";
import { splitSourceDescription } from "@/lib/sourceMetadata";

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

const BGM_MAX_BYTES = 25 * 1024 * 1024;
const BGM_TYPES = new Set(["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a"]);

const QUALITY_LABEL = { passed: "通过", warning: "需复核", failed: "未通过" } as const;
const QUALITY_COLOR = { passed: "#15803d", warning: "#b45309", failed: "#b91c1c" } as const;

export function RenderDetail({ stage, taskId, task, onRerun, onApprove }: DetailCommon) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [isPreviousVideo, setIsPreviousVideo] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [bookName, setBookName] = useState("");
  const [publication, setPublication] = useState<BookArtifact | null>(null);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);
  const [creatingRepost, setCreatingRepost] = useState(false);
  const [repostError, setRepostError] = useState<string | null>(null);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityUnavailable, setQualityUnavailable] = useState(false);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [review, setReview] = useState<ReviewEntry | null>(null);
  const [bgmPath, setBgmPath] = useState(task.bgm_path || "");
  const [bgmVolume, setBgmVolume] = useState(Number(task.bgm_volume ?? 0.08));
  const [narrationVolume, setNarrationVolume] = useState(Number(task.narration_volume ?? 1));
  const [bgmAuthorized, setBgmAuthorized] = useState(Boolean(task.bgm_authorization_confirmed));
  const [bgmUrl, setBgmUrl] = useState<string | null>(null);
  const [bgmBusy, setBgmBusy] = useState(false);
  const [bgmError, setBgmError] = useState<string | null>(null);
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
      const response = await fetch(`/api/signed-url?path=${encodeURIComponent(path)}`);
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
        const signed = await fetch(`/api/signed-url?path=${encodeURIComponent(path)}`).then(response => response.json());
        if (!signed.signedUrl) return;
        const book = await fetch(signed.signedUrl).then(response => response.json()) as BookArtifact;
        if (active) {
          setBookName(book.book_name?.trim() || "");
          setPublication(book);
        }
      } catch {
        if (active) { setBookName(""); setPublication(null); }
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
      const signedResponse = await fetch(
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
    if (!bgmPath) { setBgmUrl(null); return; }
    fetch(`/api/signed-url?path=${encodeURIComponent(bgmPath)}`)
      .then(response => response.json())
      .then(data => setBgmUrl(data.signedUrl || null))
      .catch(() => setBgmUrl(null));
  }, [bgmPath]);

  const saveBgm = async (next: { path?: string; authorized?: boolean } = {}) => {
    setBgmBusy(true);
    setBgmError(null);
    const { error } = await supabase.from("tasks").update({
      bgm_path: (next.path ?? bgmPath) || null,
      bgm_volume: bgmVolume,
      narration_volume: narrationVolume,
      bgm_authorization_confirmed: next.authorized ?? bgmAuthorized,
    }).eq("id", taskId);
    setBgmBusy(false);
    if (error) setBgmError(error.message);
  };

  const uploadBgm = async (file: File | null) => {
    if (!file) return;
    if (!BGM_TYPES.has(file.type.toLowerCase()) || file.size > BGM_MAX_BYTES) {
      setBgmError("仅支持不超过 25MB 的 MP3、WAV 或 M4A 音频");
      return;
    }
    setBgmBusy(true);
    setBgmError(null);
    const ext = file.name.split(".").pop()?.toLowerCase() || "mp3";
    const path = `${taskId}/background-music/${crypto.randomUUID()}.${ext}`;
    const { error: uploadError } = await supabase.storage.from("artifacts").upload(path, file, { contentType: file.type || "audio/mpeg", upsert: false });
    if (uploadError) { setBgmBusy(false); setBgmError(uploadError.message); return; }
    setBgmPath(path);
    const { error } = await supabase.from("tasks").update({
      bgm_path: path,
      bgm_volume: bgmVolume,
      narration_volume: narrationVolume,
      bgm_authorization_confirmed: bgmAuthorized,
    }).eq("id", taskId);
    setBgmBusy(false);
    if (error) setBgmError(error.message);
  };

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
        const signed = await fetch(`/api/signed-url?path=${encodeURIComponent(path)}`).then(response => response.json());
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

  const copyPublication = async (label: string, value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopyNotice(`已复制${label}`);
      window.setTimeout(() => setCopyNotice(null), 1_500);
    } catch {
      setCopyNotice("复制失败，请检查剪贴板权限");
    }
  };

  const legacySource = splitSourceDescription(task.title);
  const sourceTitle = publication?.source_title?.trim() || legacySource.title;
  const sourceTags = Array.isArray(publication?.source_tags) && publication.source_tags.length
    ? publication.source_tags.filter(Boolean)
    : (task.source_tags?.length ? task.source_tags : legacySource.tags);
  const publishTitle = publication?.publish_title?.trim() || publication?.title_short?.trim() || "";
  const publicationText = [
    `原标题：${sourceTitle}`,
    `标签：${sourceTags.map(tag => `#${tag.replace(/^#/, "")}`).join(" ")}`,
    `建议发布标题：${publishTitle}`,
  ].join("\n");

  const canCreateRepost = stage?.status === "done" && task.rewrite_mode !== "repost_dedup";
  const canApprove = stage?.status === "needs_review";

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
          background: "#fff5f5", border: "1px solid #fecaca",
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
            <div><p className="eyebrow">当前成片方案</p><h3>中老年生活叙事</h3><p>以下为当前 worker 实际使用的固定输出参数，不会在本任务中途改变。</p></div>
            <dl>
              <div><dt>画幅</dt><dd>竖版 9:16</dd></div>
              <div><dt>画面</dt><dd>生活化 · 轻微油画感</dd></div>
              <div><dt>动效</dt><dd>缓慢 Zoom In · 短叠化</dd></div>
              <div><dt>声音</dt><dd>配音与字幕时间轴对齐</dd></div>
              <div><dt>背景音乐</dt><dd>当前未配置</dd></div>
            </dl>
            <p className="render-preset-note">多风格和背景音乐会在 worker 参数化后进入新任务设置，不影响历史成片。</p>
            <div className="render-future-list" aria-label="后续能力">
              <strong>后续能力</strong>
              <span>多风格版本：待接入 render 配置</span>
              <span>背景音乐：待接入音频混音配置</span>
              <span>失败后保留视频：当前已支持人工检查</span>
            </div>
          </aside>
        </section>
      )}

      {(sourceTitle || sourceTags.length > 0 || publishTitle) && (
        <section className="publication-panel" aria-labelledby="publication-title">
          <div className="render-panel-heading"><div><strong id="publication-title">发布内容表</strong><span>成片完成后可直接复制使用；标签保持来源数据，建议标题不超过16字且不含标点。</span></div><TextBtn onClick={() => void copyPublication("发布内容表", publicationText)}>复制整表</TextBtn></div>
          <dl>
            <div><dt>原标题</dt><dd>{sourceTitle || "—"}</dd><button type="button" onClick={() => void copyPublication("原标题", sourceTitle)}>复制</button></div>
            <div><dt>来源标签</dt><dd>{sourceTags.length ? sourceTags.map(tag => `#${tag.replace(/^#/, "")}`).join(" ") : "—"}</dd><button type="button" disabled={!sourceTags.length} onClick={() => void copyPublication("标签", sourceTags.map(tag => `#${tag.replace(/^#/, "")}`).join(" "))}>复制</button></div>
            <div><dt>建议发布标题</dt><dd>{publishTitle || "等待书籍阶段生成"}</dd><button type="button" disabled={!publishTitle} onClick={() => void copyPublication("建议发布标题", publishTitle)}>复制</button></div>
          </dl>
          {copyNotice && <p className="publication-copy-notice" role="status">{copyNotice}</p>}
        </section>
      )}

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

      <section className="bgm-settings" aria-label="背景音乐设置">
        <div className="render-panel-heading"><div><strong>背景音乐</strong><span>任务级设置，配音始终优先；只上传已获授权使用的音乐。</span></div></div>
        <div className="bgm-controls">
          <label className="bgm-file-control"><span>音乐文件</span><input type="file" accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/m4a" disabled={bgmBusy} onChange={event => { void uploadBgm(event.target.files?.[0] || null); event.currentTarget.value = ""; }} /><small>{bgmPath ? "已上传，可替换" : "MP3、WAV、M4A，不超过 25MB"}</small></label>
          <label><span>背景音乐音量 {bgmVolume.toFixed(2)}</span><input type="range" min="0.02" max="0.20" step="0.01" value={bgmVolume} onChange={event => setBgmVolume(Number(event.target.value))} disabled={bgmBusy || !bgmPath} /></label>
          <label><span>配音音量 {narrationVolume.toFixed(2)}</span><input type="range" min="0.50" max="1.50" step="0.05" value={narrationVolume} onChange={event => setNarrationVolume(Number(event.target.value))} disabled={bgmBusy} /></label>
          <label className="bgm-authorization"><input type="checkbox" checked={bgmAuthorized} disabled={bgmBusy || !bgmPath} onChange={event => setBgmAuthorized(event.target.checked)} />我确认已取得该音乐的使用授权</label>
          <div className="bgm-actions">{bgmUrl && <audio controls src={bgmUrl} />}<TextBtn variant="primary" disabled={bgmBusy || !bgmPath || !bgmAuthorized} onClick={() => void saveBgm()}> {bgmBusy ? "保存中…" : "保存成片设置"}</TextBtn></div>
        </div>
        {bgmError && <p role="alert" className="bgm-error">{bgmError}</p>}
      </section>

    </DetailShell>
  );
}
