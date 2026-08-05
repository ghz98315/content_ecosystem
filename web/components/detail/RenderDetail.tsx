"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { DetailShell, TextBtn, DetailCommon } from "./_shell";

export function RenderDetail({ stage, taskId, task, onRerun }: DetailCommon) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);
  const [creatingRepost, setCreatingRepost] = useState(false);
  const [repostError, setRepostError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (!stage?.output_ref || stage.status !== "done") return;
    setLoading(true);
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json())
      .then(({ signedUrl }) => setVideoUrl(signedUrl))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [stage?.output_ref, stage?.status]);

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

  return (
    <DetailShell
      title="成片"
      stage={stage}
      onRerun={onRerun}
      actions={
        <>
          {videoUrl && <TextBtn variant="primary" onClick={download}>下载视频</TextBtn>}
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
      {loading && <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>加载中…</p>}

      {videoUrl && (
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
      )}
    </DetailShell>
  );
}
