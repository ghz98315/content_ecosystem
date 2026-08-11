"use client";
export const dynamic = "force-dynamic";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { Task, Stage, StageKind, STAGES } from "@/lib/types";
import { AppShell }    from "@/components/AppShell";
import { PipelineBar } from "@/components/PipelineBar";
import { StageDetail } from "@/components/StageDetail";
import { PreflightPanel } from "@/components/PreflightPanel";

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { userId } = useAnonAuth();

  const [task,   setTask]   = useState<Task | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [tasks,  setTasks]  = useState<Task[]>([]);
  const [selected, setSelected] = useState<StageKind>("ingest");
  const [workspaceView, setWorkspaceView] = useState<"flow" | "preflight">("flow");
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
    const next = kind === "book" || kind === "render" ? "done" : "pending";
    const { error } = await supabase
      .from("stages")
      .update({ status: next, error: null })
      .eq("id", stageId);
    if (error) {
      setActionNotice({ text: error.message, ok: false });
      return;
    }
    const { error: taskError } = await supabase
      .from("tasks")
      .update({ status: kind === "render" ? "done" : "processing" })
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
    return <AppShell><div className="page-loading"><div className="skeleton loading-line" /><div className="skeleton loading-block" /></div></AppShell>;
  }

  const doneCount = stages.filter(s => s.status === "done").length;
  const currentStage = stages.find(stage => stage.kind === selected);
  const taskStatusLabel = task.status === "processing" ? "处理中" : task.status === "needs_review" ? "待确认" : task.status === "done" ? "已完成" : task.status === "failed" ? "失败" : task.status === "cancelled" ? "已取消" : "待处理";
  const canDeletePending = task.status === "pending"
    && stages.length > 0
    && stages.every(stage => stage.status === "pending");
  const openStage = (kind: StageKind) => { setSelected(kind); setWorkspaceView("flow"); };

  return (
    <AppShell tasks={tasks} currentTaskId={id}>
      <div className="task-workspace">
        {/* 任务标题栏 */}
        <div className="task-header">
          <div className="task-header-copy">
            <span className="task-header-kicker">内容任务 · {task.id.slice(0, 8)}</span>
            <strong>{task.title || task.source_url || task.id}</strong>
          </div>
          <div className="task-header-progress" aria-label={`已完成 ${doneCount} 个阶段，共 ${STAGES.length} 个阶段`}>
            <div><span>{taskStatusLabel}</span><b>{doneCount} / {STAGES.length}</b></div>
            <span className="task-progress-track"><i style={{ width: `${Math.round(doneCount / STAGES.length * 100)}%` }} /></span>
          </div>
          {!["done", "cancelled", "failed"].includes(task.status) && (
            <button
              onClick={canDeletePending ? cancelAndDeletePendingTask : cancelTask}
              disabled={actionBusy}
              className="task-cancel hoverable"
              style={{
                padding: "3px 10px", fontSize: 12, background: "none",
                border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
                cursor: actionBusy ? "wait" : "pointer",
                color: canDeletePending ? "var(--status-failed)" : "var(--text-secondary)",
                opacity: actionBusy ? 0.65 : 1,
                transition: "background 0.12s ease",
              }}
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

        <nav className="workspace-tabs" aria-label="项目工作区">
          <button className={workspaceView === "flow" ? "is-active" : ""} onClick={() => setWorkspaceView("flow")}>流程工作台</button>
          <button className={workspaceView === "preflight" ? "is-active" : ""} onClick={() => setWorkspaceView("preflight")}>生成前确认<span className="tab-count">{stages.filter(stage => stage.kind !== "render" && stage.status === "done").length}/7</span></button>
        </nav>

        {workspaceView === "flow" ? <>
          <PipelineBar stages={stages} selected={selected} onSelect={setSelected} />
          <div className="task-stage-context"><span>当前阶段</span><strong>{STAGES.find(item => item.kind === selected)?.label}</strong><span className={`status-badge status-${currentStage?.status || "pending"}`}>{currentStage ? ({ pending: "待处理", processing: "处理中", done: "已完成", failed: "失败", needs_review: "待确认", cancelled: "已取消" } as const)[currentStage.status] : "待处理"}</span><small>{currentStage?.updated_at ? `更新于 ${new Date(currentStage.updated_at).toLocaleString("zh-CN", { hour12: false })}` : "等待阶段开始"}</small></div>
          <div className="task-stage-content"><StageDetail key={selected} kind={selected} stage={currentStage} stages={stages} taskId={id} task={task} onRerun={rerun} onApprove={approve} /></div>
        </> : <div className="task-stage-content"><PreflightPanel task={task} stages={stages} onOpenStage={openStage} /></div>}
      </div>
    </AppShell>
  );
}
