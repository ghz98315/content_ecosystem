"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { DetailShell, DetailCommon, TextBtn } from "./_shell";

interface BookData {
  book_name?: string;
  author?: string;
  nationality?: string;
  confidence?: string;
  video_title?: string;
  cta_text?: string;
}

export function BookDetail({ stage, onRerun }: DetailCommon) {
  const [data, setData] = useState<BookData | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<BookData>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(response => response.json())
      .then(({ signedUrl }) => fetch(signedUrl))
      .then(response => response.json())
      .then(setData)
      .catch(() => setError("书籍信息加载失败，请刷新后重试"));
  }, [stage?.output_ref, stage?.updated_at]);

  const isReview = stage?.status === "needs_review";
  const isDone = stage?.status === "done";

  const beginEditing = () => {
    setDraft({
      book_name: data?.book_name || "",
      author: data?.author || "",
      nationality: data?.nationality || "",
      cta_text: data?.cta_text || "",
    });
    setEditing(true);
    setError(null);
  };

  const confirm = async () => {
    if (!stage) return;
    setBusy(true);
    setError(null);
    const params = { ...(stage.params || {}) } as Record<string, unknown>;
    if (editing) {
      const bookName = draft.book_name?.trim();
      const author = draft.author?.trim();
      const nationality = draft.nationality?.trim();
      if (bookName) params.manual_book_name = bookName;
      if (author) params.manual_book_author = author;
      if (nationality) params.manual_book_nationality = nationality;
      const ctaText = draft.cta_text?.trim();
      if (ctaText) params.manual_cta_text = ctaText;
    }
    params.book_confirmed = true;
    const { error: updateError } = await supabase
      .from("stages")
      .update({ status: "pending", error: null, params })
      .eq("id", stage.id)
      .eq("status", "needs_review");
    setBusy(false);
    if (updateError) {
      setError(updateError.message || "书籍信息保存失败，请重试");
      return;
    }
    const { error: taskError } = await supabase
      .from("tasks")
      .update({ status: "processing" })
      .eq("id", stage.task_id);
    if (taskError) {
      setError(taskError.message || "任务状态恢复失败，请刷新后重试");
      return;
    }
    setEditing(false);
  };

  const confidenceColor =
    data?.confidence === "high" ? "var(--status-done)" :
    data?.confidence === "low" ? "var(--status-review)" : "var(--text-disabled)";

  const actions = isReview ? (
    <TextBtn variant="primary" onClick={confirm} disabled={busy}>
      {busy ? "提交中..." : editing ? "保存并继续" : "确认继续"}
    </TextBtn>
  ) : undefined;

  return (
    <DetailShell title="书籍信息" stage={stage} onRerun={onRerun} actions={actions}>
      {(isReview || isDone) && data && (
        <>
          <section style={{ marginBottom: 20 }}>
            <EditableField
              label="书名"
              value={data.book_name}
              editing={editing}
              draftValue={draft.book_name || ""}
              autoFocus
              onEdit={beginEditing}
              onChange={value => setDraft(current => ({ ...current, book_name: value }))}
            />
            <EditableField
              label="作者"
              value={data.author}
              editing={editing}
              draftValue={draft.author || ""}
              onEdit={beginEditing}
              onChange={value => setDraft(current => ({ ...current, author: value }))}
            />
            <EditableField
              label="国籍"
              value={data.nationality}
              editing={editing}
              draftValue={draft.nationality || ""}
              onEdit={beginEditing}
              onChange={value => setDraft(current => ({ ...current, nationality: value }))}
            />
            <Field label="置信度">
              <span style={{ color: confidenceColor, fontWeight: 500 }}>
                {data.confidence === "high" ? "高" : data.confidence === "low" ? "低，请确认书籍信息" : "-"}
              </span>
            </Field>
            {editing && (
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                <TextBtn onClick={() => { setEditing(false); setDraft({}); }}>取消</TextBtn>
              </div>
            )}
            {data.video_title && <Field label="视频标题">{data.video_title}</Field>}
          </section>

          {data.cta_text && (
            <section>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-disabled)", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 8 }}>
                CTA 文案
              </div>
              {editing ? (
                <textarea
                  value={draft.cta_text || ""}
                  onChange={event => setDraft(current => ({ ...current, cta_text: event.target.value }))}
                  aria-label="CTA文案"
                  rows={4}
                  style={{ width: "100%", padding: "10px 12px", boxSizing: "border-box", resize: "vertical", border: "1px solid var(--border-focus)", borderRadius: "var(--radius-md)", font: "inherit", fontSize: 13, lineHeight: 1.8, outline: "none" }}
                />
              ) : (
                <div style={{ padding: "12px 16px", background: "var(--bg-hover)", borderRadius: "var(--radius-lg)", fontSize: 13, lineHeight: 1.8, color: "var(--text-primary)", borderLeft: "3px solid var(--border-focus)", display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <span style={{ flex: 1 }}>{data.cta_text}</span>
                  {isReview && <button type="button" onClick={beginEditing} style={{ fontSize: 11, color: "var(--text-secondary)", background: "none", border: "none", cursor: "pointer", padding: "1px 6px", borderRadius: "var(--radius-sm)" }}>编辑</button>}
                </div>
              )}
            </section>
          )}
          {error && <p style={{ fontSize: 12, color: "var(--status-failed)", marginTop: 8 }}>{error}</p>}
        </>
      )}
    </DetailShell>
  );
}

function EditableField({
  label,
  value,
  editing,
  draftValue,
  autoFocus,
  onEdit,
  onChange,
}: {
  label: string;
  value?: string;
  editing: boolean;
  draftValue: string;
  autoFocus?: boolean;
  onEdit: () => void;
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      {editing ? (
        <input
          autoFocus={autoFocus}
          value={draftValue}
          onChange={event => onChange(event.target.value)}
          style={{ width: "100%", padding: "4px 10px", borderRadius: "var(--radius-md)", border: "1px solid var(--border-focus)", fontSize: 13, outline: "none", fontFamily: "var(--font)", boxSizing: "border-box" }}
        />
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
          <span>{value || "-"}</span>
          <button
            type="button"
            onClick={onEdit}
            style={{ fontSize: 11, color: "var(--text-secondary)", background: "none", border: "none", cursor: "pointer", padding: "1px 6px", borderRadius: "var(--radius-sm)" }}
          >
            编辑
          </button>
        </div>
      )}
    </Field>
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
