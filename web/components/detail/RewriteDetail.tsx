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
  content_category?: string;
  compliance?: ComplianceReport;
}

interface ComplianceIssue {
  level: "high" | "medium" | "low";
  category: string;
  text: string;
  reason: string;
  suggestion: string;
}

interface ComplianceReport {
  status: "pass" | "warning" | "blocked";
  issues: ComplianceIssue[];
  semantic_complete?: boolean;
}

const LEGACY_STYLE_NAMES = ["A · 痛点共鸣", "B · 故事叙述", "C · 知识科普"];
const LEGACY_STYLE_HINTS = [
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
        else if (d.candidates?.length === 1) setSelected(0);
      })
      .catch(() => setErr("改写稿加载失败，请刷新后重试"));
  }, [stage?.output_ref, stage?.updated_at]);

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
  const report = data?.compliance;
  const actions = isReview ? (
    <TextBtn variant="primary" onClick={confirm} disabled={busy || selected == null}>
      {busy ? "提交中…" : "确认改写稿 →"}
    </TextBtn>
  ) : undefined;

  return (
    <DetailShell title="改写" stage={stage} onRerun={onRerun} actions={actions}>
      {(isReview || isDone) && data && (
        <>
          <div style={{ display: "flex", gap: 16, marginBottom: 14, fontSize: 12, color: "var(--text-secondary)" }}>
            <span>原文 {data.source_length ?? "—"} 字</span>
            <span>{data.complete ? "改写稿已通过完整性检查" : "历史改写稿，确认前请检查全文"}</span>
          </div>

          {report && (
            <section style={{
              marginBottom: 16,
              padding: "12px 14px",
              border: `1px solid ${report.status === "blocked" ? "#fecaca" : report.status === "warning" ? "#fde68a" : "#bbf7d0"}`,
              borderRadius: "var(--radius-md)",
              background: report.status === "blocked" ? "#fff5f5" : report.status === "warning" ? "#fffbeb" : "#f0fdf4",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: report.issues.length ? 10 : 0 }}>
                <strong style={{ fontSize: 12 }}>
                  {report.status === "blocked" ? "合规检查：需要修改" : report.status === "warning" ? "合规检查：建议复核" : "合规检查：通过"}
                </strong>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  {report.issues.length ? `${report.issues.length} 项` : "未发现风险项"}
                </span>
              </div>
              {report.issues.map((issue, index) => (
                <div
                  key={`${issue.category}-${issue.text}-${index}`}
                  style={{
                    padding: "9px 0",
                    borderTop: index ? "1px solid rgba(0,0,0,0.08)" : "none",
                    fontSize: 12,
                    lineHeight: 1.6,
                  }}
                >
                  <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                    <strong>{issue.level === "high" ? "高风险" : issue.level === "medium" ? "需复核" : "提醒"} · {issue.category}</strong>
                    {issue.text && <span style={{ color: "var(--status-failed)" }}>“{issue.text}”</span>}
                  </div>
                  <div style={{ color: "var(--text-secondary)" }}>{issue.reason}</div>
                  <div>{issue.suggestion}</div>
                </div>
              ))}
            </section>
          )}

          {data.candidates.map((original, i) => {
            const isSelected = selected === i;
            const text = drafts[i] ?? original;
            const length = textLength(text);
            const estimatedSeconds = Math.max(1, Math.round(length / 3.5));
            const isSingleDraft = data.candidates.length === 1;
            const styleName = isSingleDraft ? "轻度改写稿" : (LEGACY_STYLE_NAMES[i] ?? `候选 ${i + 1}`);
            const styleHint = isSingleDraft
              ? "保留原文钩子、主体结构和结尾，仅调整少量措辞"
              : LEGACY_STYLE_HINTS[i];
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
                  <strong style={{ fontSize: 12 }}>{styleName}</strong>
                  <span style={{ fontSize: 11, color: "var(--text-disabled)" }}>{styleHint}</span>
                  <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-secondary)" }}>
                    {length} 字 · 预计 {Math.floor(estimatedSeconds / 60)}:{String(estimatedSeconds % 60).padStart(2, "0")}
                  </span>
                </header>

                {isReview && isSelected ? (
                  <textarea
                    value={text}
                    onClick={e => e.stopPropagation()}
                    onChange={e => setDrafts(prev => prev.map((item, idx) => idx === i ? e.target.value : item))}
                    aria-label={`${styleName}完整文案`}
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
