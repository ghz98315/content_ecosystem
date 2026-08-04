"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { DetailShell, TextBtn, DetailCommon } from "./_shell";

interface RewriteData {
  candidates: string[];
  candidate_lengths?: number[];
  source_length?: number;
  complete?: boolean;
  chosen: number | null;
  final_text?: string | null;
}

const STYLE_NAMES = ["A · 痛点共鸣", "B · 故事叙述", "C · 知识科普"];
const STYLE_HINTS = [
  "直接切入问题，强化情绪共鸣",
  "通过人物和场景增强代入感",
  "突出观点、方法和信息密度",
];

function textLength(text: string) {
  return text.replace(/\s/g, "").length;
}

export function RewriteDetail({ stage, onRerun }: DetailCommon) {
  const [data, setData] = useState<RewriteData | null>(null);
  const [drafts, setDrafts] = useState<string[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!stage?.output_ref) return;
    fetch(`/api/signed-url?path=${encodeURIComponent(stage.output_ref)}`)
      .then(r => r.json()).then(({ signedUrl }) => fetch(signedUrl))
      .then(r => r.json())
      .then((d: RewriteData) => {
        setData(d);
        setDrafts(d.candidates || []);
        if (d.chosen != null) setSelected(d.chosen);
      })
      .catch(() => setErr("改写稿加载失败，请刷新后重试"));
  }, [stage?.output_ref]);

  const confirm = async () => {
    if (selected == null || !stage) return;
    const finalText = drafts[selected]?.trim();
    if (!finalText) {
      setErr("最终文案不能为空");
      return;
    }
    setBusy(true);
    setErr(null);
    const { error } = await supabase.from("stages").update({
      status: "pending",
      error: null,
      params: { ...(stage.params || {}), chosen_index: selected, final_text: finalText },
    }).eq("id", stage.id);
    setBusy(false);
    if (error) setErr(error.message);
  };

  const isReview = stage?.status === "needs_review";
  const isDone = stage?.status === "done";
  const actions = isReview ? (
    <TextBtn variant="primary" onClick={confirm} disabled={busy || selected == null}>
      {busy ? "提交中…" : "确认完整文案 →"}
    </TextBtn>
  ) : undefined;

  return (
    <DetailShell title="改写" stage={stage} onRerun={onRerun} actions={actions}>
      {(isReview || isDone) && data && (
        <>
          <div style={{ display: "flex", gap: 16, marginBottom: 14, fontSize: 12, color: "var(--text-secondary)" }}>
            <span>原文 {data.source_length ?? "—"} 字</span>
            <span>{data.complete ? "三个候选均已通过完整性检查" : "历史改写稿，确认前请检查全文"}</span>
          </div>

          {data.candidates.map((original, i) => {
            const isSelected = selected === i;
            const text = drafts[i] ?? original;
            const length = textLength(text);
            const estimatedSeconds = Math.max(1, Math.round(length / 3.5));
            return (
              <section
                key={i}
                onClick={() => isReview && setSelected(i)}
                style={{
                  marginBottom: 12,
                  borderRadius: "var(--radius-lg)",
                  border: `1px solid ${isSelected ? "var(--border-focus)" : "var(--border)"}`,
                  borderLeft: isSelected ? "3px solid var(--border-focus)" : "1px solid var(--border)",
                  background: isSelected ? "#f0f5ff" : "var(--bg-page)",
                  cursor: isReview ? "pointer" : "default",
                  overflow: "hidden",
                }}
              >
                <header style={{ padding: "10px 14px 8px", display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                  <strong style={{ fontSize: 12 }}>{STYLE_NAMES[i] ?? `候选 ${i + 1}`}</strong>
                  <span style={{ fontSize: 11, color: "var(--text-disabled)" }}>{STYLE_HINTS[i]}</span>
                  <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-secondary)" }}>
                    {length} 字 · 预计 {Math.floor(estimatedSeconds / 60)}:{String(estimatedSeconds % 60).padStart(2, "0")}
                  </span>
                </header>

                {isReview && isSelected ? (
                  <textarea
                    value={text}
                    onClick={e => e.stopPropagation()}
                    onChange={e => setDrafts(prev => prev.map((item, idx) => idx === i ? e.target.value : item))}
                    aria-label={`${STYLE_NAMES[i]}完整文案`}
                    style={{
                      display: "block", width: "calc(100% - 28px)", minHeight: 240,
                      margin: "0 14px 14px", padding: 12, resize: "vertical",
                      boxSizing: "border-box",
                      border: "1px solid var(--border-focus)", borderRadius: "var(--radius-md)",
                      font: "inherit", fontSize: 13, lineHeight: 1.8,
                      color: "var(--text-primary)", background: "#fff",
                    }}
                  />
                ) : (
                  <pre style={{
                    margin: "0 14px 14px", padding: 12, maxHeight: 300, overflowY: "auto",
                    whiteSpace: "pre-wrap", fontFamily: "var(--font)", fontSize: 13,
                    lineHeight: 1.8, color: "var(--text-primary)", background: "var(--bg-hover)",
                    borderRadius: "var(--radius-md)",
                  }}>
                    {isDone && data.chosen === i && data.final_text ? data.final_text : text}
                  </pre>
                )}
              </section>
            );
          })}

          {err && <p style={{ fontSize: 12, color: "var(--status-failed)", marginTop: 8 }}>{err}</p>}
        </>
      )}
    </DetailShell>
  );
}
