"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { STATUS_COLOR, Task } from "@/lib/types";

type Artifact = { task_id: string; meta: Record<string, unknown> | null; created_at: string };
type Stage = { task_id: string; kind: string; seq: number; status: string };

const STATUS_LABEL: Record<string, string> = {
  pending: "待处理", processing: "处理中", done: "已完成", failed: "异常",
  needs_review: "待确认", cancelled: "已取消",
};

function numberText(value: unknown) {
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return "—";
  return number >= 10000 ? `${(number / 10000).toFixed(1)}万` : number.toLocaleString("zh-CN");
}

function durationText(value: unknown) {
  const seconds = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(seconds)) return "—";
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function dateText(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

function currentStage(stages: Stage[]) {
  const active = stages.find(stage => stage.status === "processing" || stage.status === "needs_review" || stage.status === "failed");
  const done = stages.filter(stage => stage.status === "done").length;
  return active ? `${active.kind} ${active.seq}/8` : `${done}/8`;
}

export default function VideoCollectionPage() {
  const { userId, error: authError } = useAnonAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [sourceText, setSourceText] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    const [taskResult, artifactResult, stageResult] = await Promise.all([
      supabase.from("tasks").select("*").order("created_at", { ascending: false }),
      supabase.from("artifacts").select("task_id,meta,created_at").eq("stage_kind", "ingest").eq("type", "audio").order("created_at", { ascending: false }),
      supabase.from("stages").select("task_id,kind,seq,status").order("seq"),
    ]);
    if (taskResult.data) setTasks(taskResult.data as Task[]);
    if (artifactResult.data) setArtifacts(artifactResult.data as Artifact[]);
    if (stageResult.data) setStages(stageResult.data as Stage[]);
  };

  useEffect(() => {
    if (!userId) return;
    load();
    const channel = supabase.channel("video-collection-workbench")
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks" }, load)
      .on("postgres_changes", { event: "*", schema: "public", table: "artifacts" }, load)
      .on("postgres_changes", { event: "*", schema: "public", table: "stages" }, load)
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [userId]);

  const artifactByTask = useMemo(() => new Map(artifacts.map(artifact => [artifact.task_id, artifact])), [artifacts]);
  const stagesByTask = useMemo(() => {
    const map = new Map<string, Stage[]>();
    stages.forEach(stage => map.set(stage.task_id, [...(map.get(stage.task_id) || []), stage]));
    return map;
  }, [stages]);
  const visible = useMemo(() => tasks.filter(task => {
    const meta = artifactByTask.get(task.id)?.meta || {};
    const author = (task.author || {}) as Record<string, unknown>;
    const source = [task.title, task.source_url, author.name, meta.desc, meta.description].filter(Boolean).join(" ").toLowerCase();
    return (status === "all" || task.status === status) && (!query.trim() || source.includes(query.trim().toLowerCase()));
  }), [artifactByTask, query, status, tasks]);

  const createTasks = async () => {
    const urls = Array.from(new Set((sourceText.match(/https?:\/\/[^\s]+/g) || []).map(url => url.replace(/[，。；！）】]+$/, ""))));
    if (!userId || !urls.length || creating) return;
    setCreating(true);
    const { error } = await supabase.from("tasks").insert(urls.map(source_url => ({ owner: userId, source_url, status: "pending" })));
    setCreating(false);
    if (error) setMessage(`导入失败：${error.message}`);
    else { setSourceText(""); setMessage(`已创建 ${urls.length} 条采集任务，正在等待 Worker 处理。`); load(); }
  };

  if (!userId && !authError) return <AppShell><div className="page-loading"><div className="skeleton loading-line" /><div className="skeleton loading-block" /></div></AppShell>;
  if (authError) return <AppShell><div className="state-panel error-state" role="alert"><strong>连接工作区失败</strong><span>{authError}</span></div></AppShell>;

  return <AppShell tasks={tasks}>
    <div className="collection-page anim-fade-in">
      <header className="collection-heading"><div><p className="eyebrow">素材运营台</p><h1>视频采集工作台</h1><p>批量导入来源视频，按采集结果、互动数据和任务进度统一查看。</p></div><button className="secondary-action" onClick={load}>刷新数据</button></header>
      <section className="collection-import" aria-label="批量导入视频"><div><h2>导入视频来源</h2><p>支持多行 URL 或包含链接的分享文本，每个链接将创建一条独立任务。</p></div><textarea value={sourceText} onChange={event => setSourceText(event.target.value)} placeholder="粘贴视频链接或分享文本，一行一个" aria-label="视频链接或分享文本" /><div className="collection-import-footer"><span>处理方式：自动完成</span><button className="primary-action" disabled={creating || !/https?:\/\//.test(sourceText)} onClick={createTasks}>{creating ? "导入中…" : "导入并创建任务"}</button></div></section>
      {message && <p className="collection-notice" role="status">{message}</p>}
      <section className="collection-results" aria-labelledby="collection-results-heading"><div className="collection-toolbar"><div><h2 id="collection-results-heading">采集结果 <span>{visible.length}</span></h2><p>已展示所有已导入任务；缺失的来源字段不会以示例数据替代。</p></div><div className="collection-filters"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索标题、作者或链接" aria-label="搜索采集任务" /><select value={status} onChange={event => setStatus(event.target.value)} aria-label="按任务状态筛选"><option value="all">全部状态</option>{Object.entries(STATUS_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div></div>
        <div className="collection-table-wrap"><table className="collection-table"><thead><tr><th>序号</th><th>标题</th><th>识别书籍</th><th>描述</th><th>作者</th><th>粉丝</th><th>时长</th><th>采集时间</th><th>点赞</th><th>评论</th><th>分享</th><th>收藏</th><th>任务状态</th><th>操作</th></tr></thead><tbody>{visible.map((task, index) => {
          const meta = artifactByTask.get(task.id)?.meta || {};
          const author = (task.author || {}) as Record<string, unknown>;
          const taskStages = stagesByTask.get(task.id) || [];
          const book = (meta.book || meta.book_info || {}) as Record<string, unknown>;
          const action = task.status === "needs_review" ? "去确认" : task.status === "done" ? "查看成片" : task.status === "failed" ? "查看异常" : "查看任务";
          return <tr key={task.id}><td>{String(index + 1).padStart(2, "0")}</td><td className="collection-title"><strong>{task.title || "未取得标题"}</strong><a href={task.source_url || undefined} target="_blank" rel="noreferrer">来源链接</a></td><td>{book.title ? <><strong>《{String(book.title)}》</strong><small>{book.author ? String(book.author) : "已识别"}</small></> : <span className="muted">等待逐字稿</span>}</td><td className="collection-description">{String(meta.desc || meta.description || "—")}</td><td>{author.name ? `@${String(author.name)}` : "—"}</td><td>{numberText(author.fans_count || author.follower_count)}</td><td>{durationText(meta.duration)}</td><td>{dateText(task.created_at)}</td><td>{numberText(meta.digg_count ?? task.play_count)}</td><td>{numberText(meta.comment_count)}</td><td>{numberText(meta.share_count)}</td><td>{numberText(meta.collect_count)}</td><td><span className={`status-badge status-${task.status}`}><i style={{ background: STATUS_COLOR[task.status as keyof typeof STATUS_COLOR] }} />{STATUS_LABEL[task.status] || task.status}</span><small className="collection-stage">{currentStage(taskStages)}</small></td><td><Link className="collection-action" href={`/task/${task.id}`}>{action}</Link><button className="collection-copy" onClick={() => task.source_url && navigator.clipboard.writeText(task.source_url)}>复制链接</button></td></tr>;
        })}</tbody></table>{!visible.length && <div className="state-panel compact"><strong>没有匹配的采集任务</strong><span>调整筛选条件，或从上方导入新的视频链接。</span></div>}</div>
      </section>
    </div>
  </AppShell>;
}
