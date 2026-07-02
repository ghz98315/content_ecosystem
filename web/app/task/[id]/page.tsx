"use client";
export const dynamic = "force-dynamic";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { Task, Stage, STAGES, StageKind } from "@/lib/types";
import { ManualUpload } from "@/components/ManualUpload";
import { RewriteReview } from "@/components/RewriteReview";
import { DownloadButton } from "@/components/DownloadButton";

// 每阶段做什么的简述（processing 时显示）
const STAGE_DESC: Record<StageKind, string> = {
  ingest:     "下载抖音视频并提取音频",
  transcribe: "Whisper 语音识别生成逐字稿",
  clean:      "AI 清洗文本，纠错 + 去除推广话术",
  rewrite:    "AI 生成 3 种风格改写稿，等待选择",
  tts:        "Edge-TTS 合成普通话配音",
  image:      "AI 生成逐句配图（9 宫格批量省成本）",
  book:       "反推书名、作者、国籍，生成视频标题",
  render:     "ffmpeg 合成 9:16 竖版字幕成片",
};

const STATUS_ICON: Record<string, string> = {
  pending:      "○",
  processing:   "⟳",
  done:         "✓",
  failed:       "✗",
  needs_review: "⏸",
};

const STATUS_COLOR: Record<string, string> = {
  pending:      "#9ca3af",
  processing:   "#2563eb",
  done:         "#16a34a",
  failed:       "#dc2626",
  needs_review: "#d97706",
};

function StageRow({
  def,
  st,
  index,
  onApprove,
  onRerun,
  taskId,
}: {
  def: { kind: StageKind; label: string };
  st: Stage | undefined;
  index: number;
  onApprove: (id: string, kind: string) => void;
  onRerun: (id: string) => void;
  taskId: string;
}) {
  const status = st?.status ?? "pending";
  const color = STATUS_COLOR[status];
  const icon = STATUS_ICON[status];
  const isProcessing = status === "processing";
  const isDone = status === "done";
  const isFailed = status === "failed";
  const isReview = status === "needs_review";
  const isPending = status === "pending";

  return (
    <div style={{ marginBottom: 2 }}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
          padding: "10px 12px",
          borderRadius: 6,
          background: isProcessing ? "#eff6ff" : isFailed ? "#fef2f2" : isReview ? "#fffbeb" : "#fafafa",
          border: `1px solid ${isProcessing ? "#bfdbfe" : isFailed ? "#fecaca" : isReview ? "#fde68a" : "#f3f4f6"}`,
          opacity: isPending ? 0.5 : 1,
        }}
      >
        {/* 序号 + 图标 */}
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: color,
            color: "#fff",
            fontSize: isProcessing ? 16 : 13,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            animation: isProcessing ? "spin 1.2s linear infinite" : "none",
          }}
        >
          {isProcessing ? "⟳" : index + 1}
        </div>

        {/* 内容 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{def.label}</span>
            <span style={{ fontSize: 12, color, fontWeight: 500 }}>
              {icon} {status === "pending" ? "等待中" : status === "processing" ? "处理中…" : status === "done" ? "完成" : status === "failed" ? "失败" : "待确认"}
            </span>
          </div>

          {/* 描述：processing 或 done 时显示 */}
          {(isProcessing || isDone || isFailed || isReview) && (
            <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
              {STAGE_DESC[def.kind]}
            </div>
          )}

          {/* 错误详情 */}
          {isFailed && st?.error && (
            <div
              style={{
                fontSize: 12,
                color: "#dc2626",
                marginTop: 4,
                background: "#fff",
                padding: "4px 8px",
                borderRadius: 4,
                fontFamily: "monospace",
                wordBreak: "break-all",
              }}
            >
              {st.error}
            </div>
          )}

          {/* output_ref（done 时显示缩略） */}
          {isDone && st?.output_ref && !st.output_ref.startsWith("m0-fake") && (
            <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2, fontFamily: "monospace" }}>
              → {st.output_ref}
            </div>
          )}

          {/* 需要人工介入的组件 */}
          {def.kind === "ingest" && isReview && st && (
            <ManualUpload taskId={taskId} stage={st} />
          )}
          {def.kind === "rewrite" && isReview && st && (
            <RewriteReview taskId={taskId} stage={st} />
          )}
        </div>

        {/* 操作按钮 */}
        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
          {isReview && st && def.kind !== "ingest" && def.kind !== "rewrite" && (
            <button style={S.approveBtn} onClick={() => onApprove(st.id, def.kind)}>
              确认继续
            </button>
          )}
          {st && !isPending && !isProcessing && (
            <button style={S.rerunBtn} onClick={() => onRerun(st.id)}>
              重跑
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const { userId } = useAnonAuth();
  const [task, setTask] = useState<Task | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);

  useEffect(() => {
    if (!userId || !id) return;
    let active = true;

    const load = async () => {
      const [{ data: t }, { data: s }] = await Promise.all([
        supabase.from("tasks").select("*").eq("id", id).single(),
        supabase.from("stages").select("*").eq("task_id", id).order("seq"),
      ]);
      if (!active) return;
      if (t) setTask(t as Task);
      if (s) setStages(s as Stage[]);
    };
    load();

    const ch = supabase
      .channel(`task-${id}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "stages", filter: `task_id=eq.${id}` }, () => load())
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks",  filter: `id=eq.${id}` }, () => load())
      .subscribe();

    return () => { active = false; supabase.removeChannel(ch); };
  }, [userId, id]);

  // 评审门确认：rewrite → pending（worker 检测 chosen_index 后 done）
  //             book   → 直接 done（LLM 反复重跑会死循环）
  const approve = async (stageId: string, kind: string) => {
    const next = kind === "book" ? "done" : "pending";
    await supabase.from("stages").update({ status: next }).eq("id", stageId);
  };
  const rerun = async (stageId: string) => {
    await supabase.from("stages").update({ status: "pending", error: null }).eq("id", stageId);
  };
  const cancelTask = async () => {
    await supabase.from("tasks").update({ status: "cancelled" }).eq("id", id);
  };

  if (!task) return <main style={S.main}><p>加载中…</p></main>;

  const renderStage = stages.find((s) => s.kind === "render");
  const taskDone = task.status === "done";

  return (
    <main style={S.main}>
      {/* 顶部 */}
      <Link href="/" style={{ fontSize: 13, color: "#6b7280" }}>← 返回列表</Link>
      <h1 style={{ fontSize: 18, marginTop: 8, marginBottom: 4 }}>
        {task.title || task.source_url || task.id}
      </h1>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
        <span
          style={{
            fontSize: 12,
            padding: "2px 10px",
            borderRadius: 12,
            background: task.status === "done" ? "#dcfce7" : task.status === "failed" ? "#fee2e2" : "#eff6ff",
            color: task.status === "done" ? "#15803d" : task.status === "failed" ? "#dc2626" : "#2563eb",
            fontWeight: 600,
          }}
        >
          {task.status}
        </span>
        <span style={{ fontSize: 12, color: "#9ca3af" }}>
          {stages.filter(s => s.status === "done").length} / {STAGES.length} 阶段完成
        </span>
      </div>

      {/* 处理日志 */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <div>
        {STAGES.map((def, i) => {
          const st = stages.find((s) => s.kind === def.kind);
          return (
            <StageRow
              key={def.kind}
              def={def}
              st={st}
              index={i}
              onApprove={approve}
              onRerun={rerun}
              taskId={id}
            />
          );
        })}
      </div>

      {/* 成片下载 */}
      {taskDone && renderStage?.output_ref && (
        <DownloadButton storagePath={renderStage.output_ref} />
      )}
    </main>
  );
}

const S: Record<string, React.CSSProperties> = {
  main: { maxWidth: 720, margin: "40px auto", padding: "0 16px", fontFamily: "system-ui, sans-serif" },
  approveBtn: { padding: "3px 10px", background: "#d97706", color: "#fff", border: "none", borderRadius: 5, cursor: "pointer", fontSize: 12 },
  rerunBtn: { padding: "3px 10px", background: "#f3f4f6", color: "#374151", border: "none", borderRadius: 5, cursor: "pointer", fontSize: 12 },
};
