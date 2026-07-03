"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Stage } from "@/lib/types";
import { DetailShell, TextBtn, DetailCommon } from "./_shell";

interface BookData {
  book_name?: string;
  author?: string;
  nationality?: string;
  confidence?: string;
  video_title?: string;
  cta_text?: string;
}

export function BookDetail({ stage, taskId, onRerun, onApprove }: DetailCommon) {
  const [data, setData]       = useState<BookData | null>(null);
  const [editing, setEditing] = useState(false);
  const [manual, setManual]   = useState("");
  const [busy, setBusy]       = useState(false);

  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json()).then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json()).then(setData).catch(() => {});
  }, [stage?.output_ref]);

  const isReview = stage?.status === "needs_review";
  const isDone   = stage?.status === "done";

  const confirm = async (bookName?: string) => {
    if (!stage) return;
    setBusy(true);
    const params = { ...(stage.params || {}) };
    if (bookName) params.manual_book_name = bookName;
    await supabase.from("stages").update({ status: "done", params }).eq("id", stage.id);
    setBusy(false);
    setEditing(false);
  };

  const confidenceColor =
    data?.confidence === "high" ? "var(--status-done)" :
    data?.confidence === "low"  ? "var(--status-review)" : "var(--text-disabled)";

  const actions = isReview ? (
    <TextBtn variant="primary" onClick={() => confirm()} disabled={busy}>
      {busy ? "提交中…" : "确认继续 →"}
    </TextBtn>
  ) : undefined;

  return (
    <DetailShell title="书籍信息" stage={stage} onRerun={onRerun} actions={actions}>
      {(isReview || isDone) && data && (
        <>
          <section style={{ marginBottom: 20 }}>
            <Field label="书名">
              {editing ? (
                <div style={{ display: "flex", gap: 8, flex: 1 }}>
                  <input
                    autoFocus value={manual}
                    onChange={e => setManual(e.target.value)}
                    placeholder={data.book_name}
                    style={{
                      flex: 1, padding: "4px 10px", borderRadius: "var(--radius-md)",
                      border: "1px solid var(--border-focus)", fontSize: 13,
                      outline: "none", fontFamily: "var(--font)",
                    }}
                  />
                  <TextBtn variant="primary" disabled={!manual.trim() || busy} onClick={() => confirm(manual.trim())}>
                    {busy ? "…" : "保存"}
                  </TextBtn>
                  <TextBtn onClick={() => { setEditing(false); setManual(""); }}>取消</TextBtn>
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
                  <span>{data.book_name || "—"}</span>
                  {isReview && (
                    <button
                      onClick={() => { setEditing(true); setManual(data.book_name || ""); }}
                      style={{
                        fontSize: 11, color: "var(--text-secondary)", background: "none",
                        border: "none", cursor: "pointer", padding: "1px 6px",
                        borderRadius: "var(--radius-sm)", transition: "background 0.1s",
                      }}
                      className="hoverable"
                    >
                      修改
                    </button>
                  )}
                </div>
              )}
            </Field>
            <Field label="作者">{data.author || "—"}</Field>
            <Field label="国籍">{data.nationality || "—"}</Field>
            <Field label="置信度">
              <span style={{ color: confidenceColor, fontWeight: 500 }}>
                {data.confidence === "high" ? "高" : data.confidence === "low" ? "低（请确认书名）" : "—"}
              </span>
            </Field>
            {data.video_title && (
              <Field label="视频标题">{data.video_title}</Field>
            )}
          </section>

          {data.cta_text && (
            <section>
              <div style={{
                fontSize: 11, fontWeight: 600, color: "var(--text-disabled)",
                letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 8,
              }}>
                CTA 文案
              </div>
              <div style={{
                padding: "12px 16px", background: "var(--bg-hover)",
                borderRadius: "var(--radius-lg)", fontSize: 13,
                lineHeight: 1.8, color: "var(--text-primary)",
                borderLeft: "3px solid var(--border-focus)",
              }}>
                {data.cta_text}
              </div>
            </section>
          )}
        </>
      )}
    </DetailShell>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 12, padding: "6px 0", borderBottom: "1px solid var(--border)", alignItems: "center" }}>
      <span style={{ width: 72, flexShrink: 0, color: "var(--text-secondary)", fontSize: 13 }}>{label}</span>
      <span style={{ fontSize: 13, color: "var(--text-primary)", flex: 1 }}>{children}</span>
    </div>
  );
}
