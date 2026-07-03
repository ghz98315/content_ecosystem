"use client";
import { useEffect, useState } from "react";
import { DetailShell, TextBtn, DetailCommon } from "./_shell";

export function RenderDetail({ stage, taskId, onRerun, onApprove }: DetailCommon) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);

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

  return (
    <DetailShell
      title="成片"
      stage={stage}
      onRerun={onRerun}
      actions={videoUrl ? (
        <TextBtn variant="primary" onClick={download}>下载视频</TextBtn>
      ) : undefined}
    >
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
