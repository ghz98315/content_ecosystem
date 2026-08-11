"use client";

import { useEffect, useMemo, useState } from "react";
import { Stage, STATUS_LABEL } from "@/lib/types";

interface ChangeSegment {
  kind: "delete" | "replace";
  before: string;
  after: string;
}

interface CleanPayload {
  raw?: string;
  cleaned?: string;
  quality_issue?: string | null;
  change_summary?: {
    raw_chars?: number;
    clean_chars?: number;
    removed_chars?: number;
    removed_ratio?: number;
    segments?: ChangeSegment[];
    segments_truncated?: boolean;
  };
}

async function loadJson(path: string) {
  const signedResponse = await fetch(`/api/signed-url?path=${encodeURIComponent(path)}`);
  if (!signedResponse.ok) throw new Error("产物地址获取失败");
  const { signedUrl } = await signedResponse.json();
  if (!signedUrl) throw new Error("产物地址无效");
  const response = await fetch(signedUrl);
  if (!response.ok) throw new Error("产物读取失败");
  return response.json();
}

function extractTranscript(payload: Record<string, unknown>) {
  const value = payload.transcription ?? payload.text;
  return typeof value === "string" ? value : "";
}

function StageState({ stage }: { stage?: Stage }) {
  const status = stage?.status ?? "pending";
  return <span className={`transcript-stage-state is-${status}`}><span className="status-dot" />{STATUS_LABEL[status]}</span>;
}

export function TranscriptCleanWorkbench({
  stages,
  onRerun,
}: {
  stages: Stage[];
  onRerun: (stageId: string) => void;
}) {
  const transcriptStage = stages.find(stage => stage.kind === "transcribe");
  const cleanStage = stages.find(stage => stage.kind === "clean");
  const [transcript, setTranscript] = useState("");
  const [clean, setClean] = useState<CleanPayload | null>(null);
  const [activePane, setActivePane] = useState<"raw" | "clean">("clean");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([
      transcriptStage?.output_ref ? loadJson(transcriptStage.output_ref) : Promise.resolve(null),
      cleanStage?.output_ref ? loadJson(cleanStage.output_ref) : Promise.resolve(null),
    ]).then(([transcriptPayload, cleanPayload]) => {
      if (!active) return;
      const parsedClean = cleanPayload as CleanPayload | null;
      setTranscript(transcriptPayload ? extractTranscript(transcriptPayload as Record<string, unknown>) : parsedClean?.raw || "");
      setClean(parsedClean);
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : "文本产物加载失败");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [transcriptStage?.output_ref, transcriptStage?.updated_at, cleanStage?.output_ref, cleanStage?.updated_at]);

  const rawText = transcript || clean?.raw || "";
  const cleanText = clean?.cleaned || "";
  const summary = clean?.change_summary;
  const rawChars = summary?.raw_chars ?? rawText.length;
  const cleanChars = summary?.clean_chars ?? cleanText.length;
  const delta = cleanChars - rawChars;
  const deltaRatio = rawChars ? Math.abs(delta) / rawChars : 0;
  const segments = summary?.segments ?? [];
  const failedStages = stages.filter(item => item.status === "failed");
  const stats = useMemo(() => [
    { label: "原稿字数", value: `${rawChars} 字`, hint: "ASR 原始结果" },
    { label: "清洗后", value: cleanText ? `${cleanChars} 字` : "待生成", hint: cleanText ? `${delta > 0 ? "增加" : "减少"} ${Math.abs(delta)} 字` : "等待清洗阶段" },
    { label: "变化比例", value: cleanText ? `${(deltaRatio * 100).toFixed(1)}%` : "—", hint: delta > 0 ? "注意异常扩写" : "删除冗余与修复错字" },
    { label: "修改记录", value: `${segments.length} 项`, hint: summary?.segments_truncated ? "仅展示主要变化" : "可逐项检查" },
  ], [rawChars, cleanChars, cleanText, delta, deltaRatio, segments.length, summary?.segments_truncated]);

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyNotice(`${label}已复制`);
      window.setTimeout(() => setCopyNotice(null), 1800);
    } catch {
      setCopyNotice("复制失败，请手动选择文本");
    }
  };

  return (
    <section className="transcript-workbench anim-fade-in" aria-labelledby="transcript-clean-title">
      <header className="workbench-heading">
        <div>
          <p className="eyebrow">TEXT REVIEW</p>
          <h2 id="transcript-clean-title">逐字稿与清洗稿</h2>
          <p>在同一视图核对原始识别与清洗结果，确认文字没有异常删减或扩写。</p>
        </div>
        <div className="workbench-heading-actions">
          {cleanStage && !["pending", "processing", "cancelled"].includes(cleanStage.status) && <button className="secondary-action" onClick={() => onRerun(cleanStage.id)}>重新清洗</button>}
        </div>
      </header>

      {error && <div className="stage-diagnostic is-error" role="alert">{error}</div>}
      {failedStages.map(failedStage => <div className="stage-diagnostic is-error transcript-stage-error" role="alert" key={failedStage.id}><div><strong>{failedStage.kind === "transcribe" ? "逐字稿" : "清洗稿"}阶段失败</strong><span>{failedStage.error || "阶段未生成可用产物"}</span></div><button className="secondary-action" onClick={() => onRerun(failedStage.id)}>重跑此阶段</button></div>)}
      {clean?.quality_issue && <div className="stage-diagnostic is-warning" role="alert">{clean.quality_issue}</div>}
      {copyNotice && <div className="copy-notice" role="status">{copyNotice}</div>}

      <div className="text-review-summary" aria-label="文本处理摘要">
        {stats.map(item => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>{item.hint}</small></div>)}
      </div>

      <div className="text-pane-switch" role="tablist" aria-label="移动端文本视图">
        <button className={activePane === "raw" ? "is-active" : ""} onClick={() => setActivePane("raw")} role="tab" aria-selected={activePane === "raw"}>原始逐字稿</button>
        <button className={activePane === "clean" ? "is-active" : ""} onClick={() => setActivePane("clean")} role="tab" aria-selected={activePane === "clean"}>清洗后文案</button>
      </div>

      {loading ? <div className="text-review-grid" aria-busy="true"><div className="skeleton text-pane-skeleton" /><div className="skeleton text-pane-skeleton" /></div> : (
        <div className="text-review-grid">
          <article className={`text-review-pane pane-raw${activePane === "raw" ? " is-mobile-active" : ""}`}>
            <header><div><strong>原始逐字稿</strong><StageState stage={transcriptStage} /></div><button onClick={() => copyText(rawText, "逐字稿")} disabled={!rawText}>复制</button></header>
            <pre>{rawText || (transcriptStage?.status === "processing" ? "逐字稿正在生成…" : "暂无逐字稿产物")}</pre>
          </article>
          <article className={`text-review-pane pane-clean${activePane === "clean" ? " is-mobile-active" : ""}`}>
            <header><div><strong>清洗后文案</strong><StageState stage={cleanStage} /></div><button onClick={() => copyText(cleanText, "清洗稿")} disabled={!cleanText}>复制</button></header>
            <pre>{cleanText || (cleanStage?.status === "processing" ? "清洗稿正在生成…" : "等待逐字稿完成后生成清洗稿")}</pre>
          </article>
        </div>
      )}

      <section className="clean-change-panel" aria-labelledby="clean-change-title">
        <div className="panel-heading"><div><strong id="clean-change-title">主要清洗记录</strong><span>删除和替换记录来自当前清洗产物</span></div><span>{segments.length} 项</span></div>
        {segments.length ? <div className="clean-change-list">{segments.map((segment, index) => <div key={`${segment.before}-${index}`}><b>{String(index + 1).padStart(2, "0")}</b><span className="change-before">{segment.kind === "delete" ? "删除" : "替换"}：{segment.before}</span>{segment.kind === "replace" && segment.after && <span className="change-after">改为：{segment.after}</span>}</div>)}</div> : <p className="panel-empty">当前产物没有可展示的逐项变化记录。</p>}
      </section>
    </section>
  );
}
