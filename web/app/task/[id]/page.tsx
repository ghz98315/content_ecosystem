"use client";

export const dynamic = "force-dynamic";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { Task, Stage, StageKind, STAGES, STATUS_LABEL } from "@/lib/types";
import { AppShell } from "@/components/AppShell";
import { PipelineBar } from "@/components/PipelineBar";
import { StageDetail } from "@/components/StageDetail";
import { PreflightPanel } from "@/components/PreflightPanel";

interface SourceMeta {
  duration?: number;
  digg_count?: number;
  comment_count?: number;
  share_count?: number;
  collect_count?: number;
}

function formatCount(value?: number | null) {
  if (value == null) return "-";
  return value >= 10000 ? `${(value / 10000).toFixed(1)}w` : value.toLocaleString("zh-CN");
}

function formatDuration(value?: number | null) {
  if (value == null) return "-";
  return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, "0")}`;
}

export default function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { userId } = useAnonAuth();
  const [task, setTask] = useState<Task | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [sourceMeta, setSourceMeta] = useState<SourceMeta | null>(null);
  const [sourceCapturedAt, setSourceCapturedAt] = useState<string | null>(null);
  const [selected, setSelected] = useState<StageKind>("ingest");
  const [workspaceView, setWorkspaceView] = useState<"flow" | "preflight">("flow");
  const [actionBusy, setActionBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = async () => {
    if (!userId || !id) return;
    setLoading(true);
    setLoadError(null);
    const [taskResult, stageResult, tasksResult, artifactResult] = await Promise.all([
      supabase.from("tasks").select("*").eq("id", id).single(),
      supabase.from("stages").select("*").eq("task_id", id).order("seq"),
      supabase.from("tasks").select("*").order("created_at", { ascending: false }),
      supabase.from("artifacts").select("meta,created_at").eq("task_id", id).eq("stage_kind", "ingest").eq("type", "audio").order("created_at", { ascending: false }).limit(1),
    ]);
    if (taskResult.error && taskResult.error.code !== "PGRST116") setLoadError(taskResult.error.message);
    if (taskResult.data) setTask(taskResult.data as Task);
    if (stageResult.error) setLoadError(current => current || stageResult.error.message);
    if (stageResult.data) setStages(stageResult.data as Stage[]);
    if (tasksResult.data) setTasks(tasksResult.data as Task[]);
    const artifact = artifactResult.data?.[0];
    if (artifact) {
      setSourceMeta((artifact.meta || {}) as SourceMeta);
      setSourceCapturedAt(artifact.created_at || null);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (!userId || !id) return;
    void load();
    const channel = supabase.channel(`task-${id}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks", filter: `id=eq.${id}` }, load)
      .on("postgres_changes", { event: "*", schema: "public", table: "stages", filter: `task_id=eq.${id}` }, load)
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, [userId, id]);

  useEffect(() => {
    const active = stages.find(stage => ["processing", "needs_review", "failed"].includes(stage.status)) || stages.find(stage => stage.status === "done");
    if (active) setSelected(active.kind);
  }, [stages]);

  const currentStage = stages.find(stage => stage.kind === selected);
  const doneCount = stages.filter(stage => stage.status === "done").length;
  const taskStatusLabel = task ? (STATUS_LABEL[task.status as keyof typeof STATUS_LABEL] || task.status) : "";
  const sourceSummary = useMemo(() => {
    if (!task) return [] as Array<[string, string]>;
    const author = task.author as Record<string, unknown> | null;
    const voice = task.tts_voice_label || task.tts_voice;
    return [
      ["作者", author?.name ? `@${String(author.name)}` : "-"],
      ["时长", formatDuration(sourceMeta?.duration)],
      ["采集时间", sourceCapturedAt ? new Date(sourceCapturedAt).toLocaleString("zh-CN", { hour12: false }) : "-"],
      ["互动数据", `${formatCount(sourceMeta?.digg_count ?? task.play_count)} 赞 / ${formatCount(sourceMeta?.comment_count)} 评 / ${formatCount(sourceMeta?.share_count)} 转 / ${formatCount(sourceMeta?.collect_count)} 藏`],
      ["配音快照", voice ? `${voice} / ${task.tts_provider || "edge"}` : "系统默认 Edge 音色"],
    ];
  }, [sourceCapturedAt, sourceMeta, task]);

  const setAction = (text: string, ok = true) => setNotice({ text, ok });
  const openStage = (kind: StageKind) => { setSelected(kind); setWorkspaceView("flow"); };

  const rerun = async (stageId: string) => {
    if (actionBusy) return;
    const stage = stages.find(item => item.id === stageId);
    const stageIndex = stage ? STAGES.findIndex(item => item.kind === stage.kind) : -1;
    const downstreamCount = stageIndex >= 0 ? STAGES.length - stageIndex - 1 : 0;
    const scope = downstreamCount > 0 ? `当前阶段及下游 ${downstreamCount} 个阶段` : "当前阶段";
    if (!window.confirm(`确认重跑${scope}？已完成的上游产物不会被重跑。`)) return;
    setActionBusy(true);
    const { data, error } = await supabase.rpc("rerun_stage", { p_stage_id: stageId });
    setActionBusy(false);
    if (error || !data?.length) setAction(error?.message || "重新运行失败", false);
    else { setAction("已重新排队运行"); await load(); }
  };

  const approve = async (stageId: string, kind: string) => {
    setActionBusy(true);
    const result = kind === "render"
      ? await supabase.rpc("review_render_stage", { p_stage_id: stageId, p_decision: "approved" })
      : await supabase.from("stages").update({ status: kind === "book" ? "done" : "pending", error: null }).eq("id", stageId);
    if (!result.error && kind !== "render") await supabase.from("tasks").update({ status: "processing" }).eq("id", id).eq("status", "needs_review");
    setActionBusy(false);
    if (result.error) setAction(result.error.message, false); else { setAction("已确认当前阶段"); await load(); }
  };

  const cancelTask = async () => {
    if (!task || actionBusy) return;
    setActionBusy(true);
    const { error } = await supabase.from("tasks").update({ status: "cancelled" }).eq("id", id).eq("status", task.status);
    if (!error) await supabase.from("stages").update({ status: "cancelled" }).eq("task_id", id).eq("status", "pending");
    setActionBusy(false);
    if (error) setAction(error.message, false); else { setTask({ ...task, status: "cancelled" }); setAction("任务已取消"); }
  };

  if (!userId) return <AppShell><div className="page-loading">正在连接工作区...</div></AppShell>;
  if (loading && !task) return <AppShell><div className="page-loading"><div className="skeleton loading-line" /><div className="skeleton loading-block" /></div></AppShell>;
  if (loadError && !task) return <AppShell><div className="state-panel error-state" role="alert"><strong>任务加载失败</strong><span>{loadError}</span><button className="secondary-action" onClick={load}>重试</button></div></AppShell>;
  if (!task) return <AppShell><div className="state-panel"><strong>任务不存在</strong><span>该任务可能已被删除，或当前工作区无权访问。</span><button className="secondary-action" onClick={() => router.push("/video-collection")}>返回采集工作台</button></div></AppShell>;

  return <AppShell tasks={tasks} currentTaskId={id}>
    <div className="task-workspace">
      <div className="task-header">
        <div className="task-header-copy"><span className="task-header-kicker">任务 {task.id.slice(0, 8)}</span><strong>{task.title || task.source_url || task.id}</strong></div>
        <div className="task-header-progress"><div><span>{taskStatusLabel}</span><b>{doneCount} / {STAGES.length}</b></div><span className="task-progress-track"><i style={{ width: `${Math.round(doneCount / STAGES.length * 100)}%` }} /></span></div>
        {!['done', 'cancelled', 'failed'].includes(task.status) && <button className="task-cancel" onClick={cancelTask} disabled={actionBusy} aria-busy={actionBusy}>{actionBusy ? "处理中..." : "取消任务"}</button>}
      </div>
      <div className="task-source-summary" aria-label="任务来源摘要">
        {sourceSummary.map(([label, value]) => <span key={label}><b>{label}</b>{value}</span>)}
        <span className="task-source-url"><b>来源链接</b>{task.source_url || "-"}</span>
      </div>
      {notice && <div className={`task-notice ${notice.ok ? "is-ok" : "is-error"}`} role="status">{notice.text}</div>}
      {loadError && <div className="task-notice is-error" role="alert"><span>{loadError}</span><button type="button" className="secondary-action" onClick={load} disabled={loading}>重试</button></div>}
      <nav className="workspace-tabs" aria-label="任务工作区视图">
        <button type="button" className={workspaceView === "flow" ? "is-active" : ""} aria-pressed={workspaceView === "flow"} onClick={() => setWorkspaceView("flow")}>处理流程</button>
        <button type="button" className={workspaceView === "preflight" ? "is-active" : ""} aria-pressed={workspaceView === "preflight"} onClick={() => setWorkspaceView("preflight")}>生成前检查 <span className="tab-count">{stages.filter(stage => stage.kind !== "render" && stage.status === "done").length}/7</span></button>
      </nav>
      {workspaceView === "flow" ? <>
        <PipelineBar stages={stages} selected={selected} onSelect={setSelected} />
        {stages.length === 0 && <div className="task-stage-empty" role="status">当前任务还没有阶段记录，稍后会自动刷新。</div>}
        <div className="task-stage-context"><span>当前阶段</span><strong>{STAGES.find(item => item.kind === selected)?.label}</strong><span className={`status-badge status-${currentStage?.status || "pending"}`}>{currentStage?.status || "pending"}</span><small>{currentStage?.updated_at ? new Date(currentStage.updated_at).toLocaleString("zh-CN", { hour12: false }) : "等待处理"}</small></div>
        <div className="task-stage-content"><StageDetail key={selected} kind={selected} stage={currentStage} stages={stages} taskId={id} task={task} onRerun={rerun} onApprove={approve} /></div>
      </> : <div className="task-stage-content"><PreflightPanel task={task} stages={stages} onOpenStage={openStage} /></div>}
    </div>
  </AppShell>;
}
