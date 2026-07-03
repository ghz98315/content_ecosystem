"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";

export function TranscribeDetail({ stage, taskId, onRerun, onApprove }: DetailCommon) {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json())
      .then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json())
      .then(d => setText(d.transcription || d.text || JSON.stringify(d, null, 2)))
      .catch(() => setText(null));
  }, [stage?.output_ref]);

  return (
    <DetailShell title="逐字稿" stage={stage} onRerun={onRerun}>
      {text ? (
        <>
          <div style={{ fontSize: 11, color: "var(--text-disabled)", marginBottom: 8 }}>
            {text.length} 字
          </div>
          <pre style={{
            whiteSpace: "pre-wrap", lineHeight: 1.8, fontSize: 13,
            color: "var(--text-primary)", fontFamily: "var(--font)",
            background: "var(--bg-hover)", padding: 16,
            borderRadius: "var(--radius-lg)", maxHeight: 480, overflowY: "auto",
          }}>
            {text}
          </pre>
        </>
      ) : (
        stage?.status === "done" && (
          <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>加载中…</p>
        )
      )}
    </DetailShell>
  );
}
