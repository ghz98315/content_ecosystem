"use client";
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

const QUALITY_LABEL = { passed: "通过", warning: "需复核", failed: "未通过" } as const;
const QUALITY_COLOR = { passed: "#15803d", warning: "#b45309", failed: "#b91c1c" } as const;

export function RenderDetail({ stage, taskId, task, onRerun, onApprove }: DetailCommon) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [isPreviousVideo, setIsPreviousVideo] = useState(false);
  const [loading, setLoading]   = useState(false);
  const [creatingRepost, setCreatingRepost] = useState(false);
  const [repostError, setRepostError] = useState<string | null>(null);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityUnavailable, setQualityUnavailable] = useState(false);
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

  const download = () => {
    if (!videoUrl) return;
    const a = document.createElement("a");
    a.href = videoUrl;
    a.download = "output.mp4";
    a.click();
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
          {videoUrl && <TextBtn variant="primary" onClick={download}>下载视频</TextBtn>}
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
      {loading && (
        <div aria-busy="true" aria-label="正在加载成片">
          <div className="skeleton" style={{ height: 24, width: "42%", marginBottom: 10 }} />
          <div className="skeleton" style={{ height: 320, width: "100%", marginBottom: 16 }} />
        </div>
      )}

      {(qualityLoading || quality || qualityUnavailable) && (
        <section style={{ marginBottom: 24 }}>
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

      {videoUrl && (
        <section>
          {isPreviousVideo && (
            <p style={{ color: "var(--text-secondary)", fontSize: 12, marginBottom: 8 }}>
              当前重跑未成功，以下为上一次成功生成的成片
            </p>
          )}
          <div style={{ display: "flex", justifyContent: "center" }}>
            <video
              controls src={videoUrl}
              style={{
                maxWidth: 320, width: "100%",
                borderRadius: "var(--radius-lg)",
                border: "1px solid var(--border)",
                background: "#000",
              }}
            />
          </div>
        </section>
      )}
    </DetailShell>
  );
}
