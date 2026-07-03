"use client";
export const dynamic = "force-dynamic";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { Task, Stage, StageKind, STAGES } from "@/lib/types";
import { Sidebar }     from "@/components/Sidebar";
import { PipelineBar } from "@/components/PipelineBar";
import { StageDetail } from "@/components/StageDetail";

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const { userId } = useAnonAuth();

  const [task,   setTask]   = useState<Task | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [tasks,  setTasks]  = useState<Task[]>([]);
  const [selected, setSelected] = useState<StageKind>("ingest");

  // 加载当前任务 + 全部任务（给 Sidebar）
  useEffect(() => {
    if (!userId || !id) return;
    let active = true;

    const load = async () => {
      const [{ data: t }, { data: s }, { data: all }] = await Promise.all([
        supabase.from("tasks").select("*").eq("id", id).single(),
        supabase.from("stages").select("*").eq("task_id", id).order("seq"),
        supabase.from("tasks").select("*").order("created_at", { ascending: false }),
      ]);
      if (!active) return;
      if (t)   setTask(t as Task);
      if (s)   setStages(s as Stage[]);
      if (all) setTasks(all as Task[]);
    };
    load();

    // 实时订阅
    const ch = supabase.channel(`task-${id}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "stages", filter: `task_id=eq.${id}` }, load)
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks",  filter: `id=eq.${id}` }, load)
      .subscribe();

    return () => { active = false; supabase.removeChannel(ch); };
  }, [userId, id]);

  // 自动切到第一个非 pending/cancelled 的阶段
  useEffect(() => {
    if (!stages.length) return;
    const active = stages.find(s =>
      s.status === "processing" || s.status === "needs_review" || s.status === "failed"
    ) ?? stages.find(s => s.status === "done");
    if (active) setSelected(active.kind);
  }, [stages]);

  const approve = async (stageId: string, kind: string) => {
    const next = kind === "book" ? "done" : "pending";
    await supabase.from("stages").update({ status: next }).eq("id", stageId);
  };

  const rerun = async (stageId: string) => {
    const stage = stages.find(s => s.id === stageId);
    const params = { ...(stage?.params ?? {}) };
    delete params.chosen_index;
    delete params.manual_book_name;
    await supabase.from("stages").update({ status: "pending", error: null, params }).eq("id", stageId);
  };

  if (!task) {
    return (
      <div style={{ display: "flex", height: "100vh" }}>
        <Sidebar tasks={[]} />
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <p style={{ color: "var(--text-disabled)", fontSize: 13 }}>加载中…</p>
        </div>
      </div>
    );
  }

  const doneCount = stages.filter(s => s.status === "done").length;

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar tasks={tasks} currentTaskId={id} />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden" }}>
        {/* 任务标题栏 */}
        <div style={{
          height: 48, display: "flex", alignItems: "center",
          padding: "0 20px", gap: 12, flexShrink: 0,
          borderBottom: "1px solid var(--border)",
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {task.title || task.source_url || task.id}
          </span>
          <span style={{ fontSize: 12, color: "var(--text-secondary)", flexShrink: 0 }}>
            {doneCount} / {STAGES.length} 完成
          </span>
          {!["done", "cancelled", "failed"].includes(task.status) && (
            <button
              onClick={() => supabase.from("tasks").update({ status: "cancelled" }).eq("id", id)}
              style={{
                padding: "3px 10px", fontSize: 12, background: "none",
                border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
                cursor: "pointer", color: "var(--text-secondary)",
                transition: "background 0.12s ease",
              }}
              className="hoverable"
            >
              取消任务
            </button>
          )}
        </div>

        {/* 流程条 */}
        <PipelineBar stages={stages} selected={selected} onSelect={setSelected} />

        {/* 详情面板 */}
        <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px" }}>
          <StageDetail
            key={selected}
            kind={selected}
            stage={stages.find(s => s.kind === selected)}
            taskId={id}
            task={task}
            onRerun={rerun}
            onApprove={approve}
          />
        </div>
      </div>
    </div>
  );
}
