"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Stage } from "@/lib/types";
import { DetailShell, TextBtn, DetailCommon } from "./_shell";

interface RewriteData { candidates: string[]; chosen: number | null; }

export function RewriteDetail({ stage, taskId, onRerun, onApprove }: DetailCommon) {
  const [data, setData]       = useState<RewriteData | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busy, setBusy]       = useState(false);
  const [err, setErr]         = useState<string | null>(null);

  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json()).then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json())
      .then((d: RewriteData) => {
        setData(d);
        if (d.chosen != null) setSelected(d.chosen);
      })
      .catch(() => {});
  }, [stage?.output_ref]);

  const confirm = async () => {
    if (selected == null || !stage) return;
    setBusy(true); setErr(null);
    const { error } = await supabase.from("stages").update({
      status: "pending", error: null,
      params: { ...(stage.params || {}), chosen_index: selected },
    }).eq("id", stage.id);
    setBusy(false);
    if (error) setErr(error.message);
  };

  const isReview = stage?.status === "needs_review";
  const isDone   = stage?.status === "done";

  const actions = isReview ? (
    <TextBtn variant="primary" onClick={confirm} disabled={busy || selected == null}>
      {busy ? "提交中…" : "确认继续 →"}
    </TextBtn>
  ) : undefined;

  return (
    <DetailShell title="改写" stage={stage} onRerun={onRerun} actions={actions}>
      {(isReview || isDone) && data && (
        <>
          {isReview && (
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
              选择一个改写候选后点确认继续
            </p>
          )}

          {data.candidates.map((text, i) => {
            const isSelected = selected === i;
            const isOpen     = expanded === i;
            const lines      = text.split("\n");
            const preview    = lines.slice(0, 4).join("\n");
            const hasMore    = lines.length > 4;

            return (
              <div
                key={i}
                onClick={() => isReview && setSelected(i)}
                style={{
                  marginBottom: 10, borderRadius: "var(--radius-lg)",
                  border: `1px solid ${isSelected ? "var(--border-focus)" : "var(--border)"}`,
                  borderLeft: isSelected ? "3px solid var(--border-focus)" : `1px solid var(--border)`,
                  background: isSelected ? "#f0f5ff" : "var(--bg-page)",
                  cursor: isReview ? "pointer" : "default",
                  transition: "border-color 0.15s ease, background 0.15s ease",
                  overflow: "hidden",
                }}
              >
                <div style={{ padding: "10px 14px 6px", display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: "1px 7px",
                    borderRadius: 10, background: isSelected ? "var(--border-focus)" : "var(--bg-hover)",
                    color: isSelected ? "#fff" : "var(--text-secondary)",
                    transition: "background 0.15s ease",
                  }}>
                    候选 {["A", "B", "C"][i] ?? i + 1}
                  </span>
                  {isSelected && (
                    <span style={{ fontSize: 11, color: "var(--border-focus)" }}>已选中</span>
                  )}
                </div>

                <pre style={{
                  margin: "0 14px 6px", fontSize: 13, lineHeight: 1.75,
                  whiteSpace: "pre-wrap", fontFamily: "var(--font)",
                  color: "var(--text-primary)", userSelect: "none", pointerEvents: "none",
                }}>
                  {isOpen ? text : preview}
                </pre>

                {hasMore && (
                  <button
                    onClick={e => { e.stopPropagation(); setExpanded(isOpen ? null : i); }}
                    style={{
                      display: "block", width: "100%", padding: "4px 14px 10px",
                      border: "none", background: "none", textAlign: "left",
                      fontSize: 12, color: "var(--text-secondary)", cursor: "pointer",
                    }}
                  >
                    {isOpen ? "▲ 收起" : "▼ 展开全文"}
                  </button>
                )}
              </div>
            );
          })}

          {err && (
            <p style={{ fontSize: 12, color: "var(--status-failed)", marginTop: 8 }}>{err}</p>
          )}
        </>
      )}
    </DetailShell>
  );
}
