"use client";
export const dynamic = "force-dynamic";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import {
  Task,
  Stage,
  STAGES,
  STATUS_LABEL,
  STATUS_COLOR,
} from "@/lib/types";
import { ManualUpload } from "@/components/ManualUpload";
import { RewriteReview } from "@/components/RewriteReview";

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
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "stages", filter: `task_id=eq.${id}` },
        () => load()
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "tasks", filter: `id=eq.${id}` },
        () => load()
      )
      .subscribe();

    return () => {
      active = false;
      supabase.removeChannel(ch);
    };
  }, [userId, id]);

  // 评审门确认：needs_review → pending，worker 会继续往下
  const approve = async (stageId: string) => {
    await supabase.from("stages").update({ status: "pending" }).eq("id", stageId);
  };

  // 重跑：任意 stage 重置为 pending
  const rerun = async (stageId: string) => {
    await supabase
      .from("stages")
      .update({ status: "pending", error: null })
      .eq("id", stageId);
  };

  if (!task)
    return (
      <main style={S.main}>
        <p>加载中…</p>
      </main>
    );

  return (
    <main style={S.main}>
      <Link href="/" style={{ fontSize: 13, color: "#6b7280" }}>
        ← 返回列表
      </Link>
      <h1 style={{ fontSize: 18, marginTop: 8 }}>
        {task.title || task.source_url || task.id}
      </h1>
      <p style={{ fontSize: 13, color: "#6b7280", marginTop: 0 }}>
        总状态：<b>{task.status}</b>
      </p>

      <div style={{ marginTop: 16 }}>
        {STAGES.map((def, i) => {
          const st = stages.find((s) => s.kind === def.kind);
          const status = st?.status ?? "pending";
          const isIngestReview  = def.kind === "ingest"  && status === "needs_review";
          const isRewriteReview = def.kind === "rewrite" && status === "needs_review";
          return (
            <div key={def.kind}>
              <div style={S.stageRow}>
                <span style={{ ...S.dot, background: STATUS_COLOR[status] }}>
                  {i + 1}
                </span>
                <span style={{ width: 90, fontSize: 14 }}>{def.label}</span>
                <span style={{ ...S.stageStatus, color: STATUS_COLOR[status] }}>
                  {STATUS_LABEL[status]}
                </span>
                <span style={{ flex: 1, fontSize: 12, color: "#9ca3af" }}>
                  {st?.error ? "⚠ " + st.error : st?.output_ref ?? ""}
                </span>
                {/* ingest 的 needs_review 走手动上传，不显示"确认继续" */}
                {/* rewrite 的 needs_review 走候选展示，不显示"确认继续" */}
                {status === "needs_review" && st && !isIngestReview && !isRewriteReview && (
                  <button style={S.approveBtn} onClick={() => approve(st.id)}>
                    确认继续
                  </button>
                )}
                {st && status !== "processing" && status !== "pending" && (
                  <button style={S.rerunBtn} onClick={() => rerun(st.id)}>
                    重跑
                  </button>
                )}
              </div>
              {isIngestReview && st && (
                <ManualUpload taskId={task.id} stage={st} />
              )}
              {isRewriteReview && st && (
                <RewriteReview taskId={task.id} stage={st} />
              )}
            </div>
          );
        })}
      </div>
    </main>
  );
}

const S: Record<string, React.CSSProperties> = {
  main: { maxWidth: 760, margin: "40px auto", padding: "0 16px", fontFamily: "system-ui, sans-serif" },
  stageRow: { display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: "1px solid #f3f4f6" },
  dot: { width: 22, height: 22, borderRadius: "50%", color: "#fff", fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  stageStatus: { width: 60, fontSize: 12 },
  approveBtn: { padding: "3px 10px", background: "#d97706", color: "#fff", border: "none", borderRadius: 5, cursor: "pointer", fontSize: 12 },
  rerunBtn: { padding: "3px 10px", background: "#f3f4f6", color: "#374151", border: "none", borderRadius: 5, cursor: "pointer", fontSize: 12 },
};
