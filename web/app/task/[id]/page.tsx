"use client";
export const dynamic = "force-dynamic";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { Task, Stage, StageKind, STAGES } from "@/lib/types";
import { Sidebar }     from "@/components/Sidebar";
import { PipelineBar } from "@/components/PipelineBar";
import { StageDetail } from "@/components/StageDetail";

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { userId } = useAnonAuth();

  const [task,   setTask]   = useState<Task | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [tasks,  setTasks]  = useState<Task[]>([]);
  const [selected, setSelected] = useState<StageKind>("ingest");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionNotice, setActionNotice] = useState<{ text: string; ok: boolean } | null>(null);

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
    const { error } = await supabase.from("stages").update({ status: next }).eq("id", stageId);
    if (error) {
      setActionNotice({ text: error.message, ok: false });
      return;
    }
    const { error: taskError } = await supabase
      .from("tasks")
      .update({ status: "processing" })
      .eq("id", id)
      .eq("status", "needs_review");
    if (taskError) {
      setActionNotice({ text: taskError.message, ok: false });
      return;
    }
    setActionNotice({ text: "已确认，任务继续处理中", ok: true });
  };

  const rerun = async (stageId: string) => {
    const stage = stages.find(s => s.id === stageId);
    if (!stage || actionBusy) return;
    setActionBusy(true);
    setActionNotice(null);

    // The RPC updates the selected stage and every downstream stage atomically.
    const { data, error: rpcError } = await supabase.rpc("rerun_stage", { p_stage_id: stageId });
    if (rpcError || !data?.length) {
      setActionNotice({
        text: rpcError?.message || "重跑未更新任何阶段，请确认数据库迁移已完成。",
        ok: false,
      });
    } else {
      setActionNotice({ text: "已将当前阶段及下游阶段重新排队。", ok: true });
    }
    setActionBusy(false);
  };

  const cancelTask = async () => {
    if (!task || actionBusy) return;
    if (!window.confirm("确认取消这个任务？尚未开始的阶段将一并取消。")) return;

    setActionBusy(true);
    setActionNotice(null);
    const { data, error } = await supabase
      .from("tasks")
      .update({ status: "cancelled" })
      .eq("id", id)
      .eq("status", task.status)
      .select("id, status");

    if (error || !data?.length) {
      setActionNotice({
        text: error?.message || "取消失败：任务状态已变化，请刷新后重试。",
        ok: false,
      });
      setActionBusy(false);
      return;
    }

    const { error: stageError } = await supabase
      .from("stages")
      .update({ status: "cancelled" })
      .eq("task_id", id)
      .eq("status", "pending");

    if (stageError) {
      setActionNotice({ text: `任务已取消，但阶段状态同步失败：${stageError.message}`, ok: false });
    } else {
      setStages(current => current.map(stage =>
        stage.status === "pending" ? { ...stage, status: "cancelled" } : stage
      ));
      setActionNotice({ text: "任务已取消。", ok: true });
    }
    setTask(current => current ? { ...current, status: "cancelled" } : current);
    setActionBusy(false);
  };

  const cancelAndDeletePendingTask = async () => {
    if (!task || actionBusy) return;
    if (!window.confirm("确认取消并删除这个尚未开始的任务？删除后无法恢复。")) return;

    setActionBusy(true);
    setActionNotice(null);

    const { data: cancelled, error: cancelError } = await supabase
      .from("tasks")
      .update({ status: "cancelled" })
      .eq("id", id)
      .eq("status", "pending")
      .select("id");

    if (cancelError || !cancelled?.length) {
      setActionNotice({
        text: cancelError?.message || "删除失败：任务已经开始处理，请刷新后改用取消任务。",
        ok: false,
      });
      setActionBusy(false);
      return;
    }

    const { error: stageError } = await supabase
      .from("stages")
      .update({ status: "cancelled" })
      .eq("task_id", id)
      .eq("status", "pending");
    if (stageError) {
      setActionNotice({ text: `任务已取消，但删除前检查失败：${stageError.message}`, ok: false });
      setTask(current => current ? { ...current, status: "cancelled" } : current);
      setActionBusy(false);
      return;
    }

    const { data: activeStages, error: checkError } = await supabase
      .from("stages")
      .select("id")
      .eq("task_id", id)
      .neq("status", "cancelled")
      .limit(1);
    if (checkError || activeStages?.length) {
      setActionNotice({
        text: checkError?.message || "任务已取消，但已有阶段开始处理，因此没有删除任务数据。",
        ok: false,
      });
      setTask(current => current ? { ...current, status: "cancelled" } : current);
      setActionBusy(false);
      return;
    }

    const { data: deleted, error: deleteError } = await supabase
      .from("tasks")
      .delete()
      .eq("id", id)
      .eq("status", "cancelled")
      .select("id");
    if (deleteError || !deleted?.length) {
      setActionNotice({
        text: deleteError?.message || "任务已取消，但删除失败，请刷新后重试。",
        ok: false,
      });
      setActionBusy(false);
      return;
    }

    router.replace("/");
    router.refresh();
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
  const canDeletePending = task.status === "pending"
    && stages.length > 0
    && stages.every(stage => stage.status === "pending");

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
              onClick={canDeletePending ? cancelAndDeletePendingTask : cancelTask}
              disabled={actionBusy}
              style={{
                padding: "3px 10px", fontSize: 12, background: "none",
                border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
                cursor: actionBusy ? "wait" : "pointer",
                color: canDeletePending ? "var(--status-failed)" : "var(--text-secondary)",
                opacity: actionBusy ? 0.65 : 1,
                transition: "background 0.12s ease",
              }}
              className="hoverable"
            >
              {actionBusy ? "处理中…" : canDeletePending ? "取消并删除" : "取消任务"}
            </button>
          )}
        </div>

        {actionNotice && (
          <div style={{
            padding: "8px 20px", fontSize: 12,
            color: actionNotice.ok ? "var(--status-done)" : "var(--status-failed)",
            background: actionNotice.ok ? "#f0fdf4" : "#fff5f5",
            borderBottom: "1px solid var(--border)",
          }}>
            {actionNotice.text}
          </div>
        )}

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
