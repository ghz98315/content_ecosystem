"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";

interface CleanData { cleaned?: string; raw?: string; }

export function CleanDetail({ stage, taskId, onRerun, onApprove }: DetailCommon) {
  const [data, setData] = useState<CleanData | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json()).then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json()).then(setData).catch(() => {});
  }, [stage?.output_ref]);

  const text = showRaw ? data?.raw : data?.cleaned;

  return (
    <DetailShell title="清洗" stage={stage} onRerun={onRerun}>
      {data && (
        <>
          <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
            {(["cleaned", "raw"] as const).map(k => (
              <button
                key={k}
                onClick={() => setShowRaw(k === "raw")}
                style={{
                  padding: "3px 12px", borderRadius: "var(--radius-md)", border: "none",
                  fontSize: 12, cursor: "pointer",
                  background: (k === "raw") === showRaw ? "#111827" : "var(--bg-hover)",
                  color: (k === "raw") === showRaw ? "#fff" : "var(--text-secondary)",
                  transition: "background 0.12s ease",
                }}
              >
                {k === "cleaned" ? "清洗后" : "原文"}
              </button>
            ))}
          </div>
          <pre style={{
            whiteSpace: "pre-wrap", lineHeight: 1.8, fontSize: 13,
            color: "var(--text-primary)", fontFamily: "var(--font)",
            background: "var(--bg-hover)", padding: 16,
            borderRadius: "var(--radius-lg)", maxHeight: 480, overflowY: "auto",
          }}>
            {text || "—"}
          </pre>
        </>
      )}
    </DetailShell>
  );
}
