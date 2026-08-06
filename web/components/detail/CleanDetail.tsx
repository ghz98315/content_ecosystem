"use client";
import { useEffect, useState } from "react";
import { DetailShell, DetailCommon } from "./_shell";

interface ChangeSegment { kind: "delete" | "replace"; before: string; after: string; }
interface CleanData {
  cleaned?: string;
  raw?: string;
  change_summary?: {
    raw_chars?: number;
    clean_chars?: number;
    removed_chars?: number;
    removed_ratio?: number;
    segments?: ChangeSegment[];
    segments_truncated?: boolean;
  };
}

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
          {data.change_summary && (
            <div style={{
              marginBottom: 12, padding: "10px 12px",
              border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
              background: "var(--bg-hover)", fontSize: 12,
            }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>
                清洗概览：原文 {data.change_summary.raw_chars ?? 0} 字 → 清洗后 {data.change_summary.clean_chars ?? 0} 字，
                减少 {Math.max(0, (data.change_summary.raw_chars ?? 0) - (data.change_summary.clean_chars ?? 0))} 字
                （{Math.round((data.change_summary.removed_ratio ?? 0) * 100)}%）
              </div>
              {(data.change_summary.segments ?? []).length > 0 && (
                <div style={{ display: "grid", gap: 5, maxHeight: 180, overflowY: "auto" }}>
                  {(data.change_summary.segments ?? []).map((segment, index) => (
                    <div key={index} style={{ lineHeight: 1.5 }}>
                      <span style={{ color: "var(--status-failed)" }}>
                        {segment.kind === "delete" ? "删减" : "替换"}：{segment.before}
                      </span>
                      {segment.kind === "replace" && segment.after && (
                        <span style={{ color: "var(--status-done)" }}> → {segment.after}</span>
                      )}
                    </div>
                  ))}
                  {data.change_summary.segments_truncated && (
                    <span style={{ color: "var(--text-disabled)" }}>其余片段请切换原文和清洗后对照查看。</span>
                  )}
                </div>
              )}
            </div>
          )}
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
