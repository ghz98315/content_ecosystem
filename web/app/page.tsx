"use client";
export const dynamic = "force-dynamic";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { STATUS_COLOR, Task } from "@/lib/types";
import { AppShell } from "@/components/AppShell";

const STATUS_LABEL: Record<string, string> = { pending: "待处理", processing: "处理中", done: "已完成", failed: "失败", needs_review: "待确认", cancelled: "已取消" };
const FILTERS = [{ id: "all", label: "全部" }, { id: "processing", label: "处理中" }, { id: "needs_review", label: "待确认" }, { id: "done", label: "已完成" }, { id: "failed", label: "失败" }];

export default function HomePage() {
  const { userId, error: authError } = useAnonAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [creating, setCreating] = useState(false);
  const [ttsSource, setTtsSource] = useState<'external' | 'automatic'>('external');
  const [tasksLoading, setTasksLoading] = useState(true);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setTasksLoading(true);
    setTasksError(null);
    try {
      const { data, error } = await supabase.from("tasks").select("*").order("created_at", { ascending: false });
      if (error) {
        setTasksError(error.message);
        return;
      }
      setTasks((data || []) as Task[]);
    } catch (error) {
      setTasksError(error instanceof Error ? error.message : "读取任务时发生未知错误");
    } finally {
      setTasksLoading(false);
    }
  };
  useEffect(() => { if (!userId) return; load(); const ch = supabase.channel("tasks-dashboard").on("postgres_changes", { event: "*", schema: "public", table: "tasks" }, load).subscribe(); return () => { supabase.removeChannel(ch); }; }, [userId]);

  const stats = useMemo(() => ({ total: tasks.length, active: tasks.filter(t => t.status === "processing").length, review: tasks.filter(t => t.status === "needs_review").length, done: tasks.filter(t => t.status === "done").length }), [tasks]);
  const visible = useMemo(() => tasks.filter(task => { const text = `${task.title || ""} ${task.source_url || ""}`.toLowerCase(); return (!query.trim() || text.includes(query.trim().toLowerCase())) && (filter === "all" || task.status === filter); }), [tasks, query, filter]);
  const groups = useMemo(() => {
    const map = new Map<string, Task[]>();
    visible.forEach(task => { const key = task.title?.trim() || "未命名项目"; map.set(key, [...(map.get(key) || []), task]); });
    return Array.from(map.entries()).slice(0, 6);
  }, [visible]);

  const openForm = () => { setShowForm(true); setTimeout(() => inputRef.current?.focus(), 80); };
  const createTask = async () => {
    if (!url.trim() || !userId || creating) return;
    setCreating(true); setMsg(null);
    const { data: createdTask, error } = await supabase.from("tasks").insert({
      owner: userId,
      source_url: url.trim(),
      status: "pending",
      tts_source: ttsSource,
      tts_provider: "indextts25",
      tts_model: "index-tts-2.5",
      tts_voice: "narrator35",
      tts_voice_label: "旁白35（IndexTTS 2.5）",
    }).select("id").single();
    if (!error && createdTask?.id) {
      const { error: imageConfigError } = await supabase.from("stages").update({
        params: { image_provider: "apimart", image_model: "gpt-image-2" },
      }).eq("task_id", createdTask.id).eq("kind", "image");
      if (imageConfigError) {
        setCreating(false);
        setMsg({ text: `生图通道快照保存失败：${imageConfigError.message}`, ok: false });
        return;
      }
    }
    setCreating(false);
    if (error) setMsg({ text: `创建失败：${error.message}`, ok: false });
    else { setUrl(""); setShowForm(false); setMsg({ text: "任务已创建，正在进入采集阶段", ok: true }); load(); setTimeout(() => setMsg(null), 3500); }
  };

  if (!userId && !authError) return <AppShell><div className="page-loading"><div className="skeleton loading-line" /><div className="skeleton loading-block" /></div></AppShell>;
  if (authError) return <AppShell><div className="state-panel error-state" role="alert"><strong>连接工作区失败</strong><span>{authError}</span></div></AppShell>;

  return <AppShell tasks={tasks} onCreateTask={openForm}>
    <div className="dashboard-page anim-fade-in">
      <section className="dashboard-heading">
        <div><p className="eyebrow">内容项目库</p><h1>把每一本书，变成可发布的内容</h1><p className="dashboard-lede">集中管理采集、改写、配音和成片，随时回到上次停下的位置。</p></div>
        <button className="primary-action dashboard-create" onClick={openForm}><span aria-hidden="true">＋</span> 新建项目</button>
      </section>

      <section className="metric-grid" aria-label="项目概览">
        {[{ label: "全部项目", value: stats.total, hint: "累计创建" }, { label: "正在处理", value: stats.active, hint: "worker 处理中" }, { label: "待确认", value: stats.review, hint: "需要你的判断" }, { label: "已产出成片", value: stats.done, hint: "可下载发布" }].map((item, i) => <div className={`metric-card metric-${i}`} key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>{item.hint}</small></div>)}
      </section>

      {showForm && <section className="create-panel create-panel-large anim-fade-in" aria-label="新建项目">
        <div className="section-heading"><div><h2>新建内容项目</h2><p>粘贴抖音分享链接，先完成逐字稿与二创确认，再按所选配音方式制作视频。</p></div><button className="icon-button" onClick={() => setShowForm(false)} aria-label="关闭新建项目">×</button></div>
        <div className="setup-strip"><label>配音方式 <select value={ttsSource} onChange={event => setTtsSource(event.target.value as 'external' | 'automatic')}><option value="external">确认文案后上传配音</option><option value="automatic">自动配音</option></select></label><span className="setup-pill">APIMart 生图</span><span className="setup-note">高级选项请在视频集合页调整</span></div>
        <div className="create-row"><input ref={inputRef} className="url-input" placeholder="粘贴抖音分享链接" value={url} onChange={e => setUrl(e.target.value)} onKeyDown={e => e.key === "Enter" && createTask()} /><button className="primary-action" onClick={createTask} disabled={creating || !url.trim()}>{creating ? "创建中…" : "开始处理"}</button><button className="secondary-action" onClick={() => { setShowForm(false); setUrl(""); }}>取消</button></div>
        <p className="form-hint">支持单条分享链接。任务创建后会锁定本次音色与处理设置，避免中途混用。</p>
      </section>}

      {msg && <div className={`notice ${msg.ok ? "notice-success" : "notice-error"}`} role={msg.ok ? "status" : "alert"}>{msg.text}</div>}
      {tasksError && <div className="notice notice-error" role="alert"><span>读取项目失败：{tasksError}</span><button className="secondary-action" onClick={() => void load()}>重试</button></div>}

      <section className="dashboard-section"><div className="section-heading"><div><p className="eyebrow">项目总览</p><h2>按书籍查看进度</h2></div><Link href="/xhs" className="text-link">打开知识图文 →</Link></div>
        {tasksLoading ? <div className="state-panel"><strong>正在读取项目</strong><span>正在同步当前账号可访问的任务。</span></div> : groups.length ? <div className="book-grid">{groups.map(([name, items]) => { const done = items.filter(t => t.status === "done").length; const active = items.filter(t => t.status === "processing").length; const failed = items.filter(t => t.status === "failed").length; return <article className="book-card" key={name}><div className="book-card-top"><span className="book-glyph" aria-hidden="true">▤</span><span className="status-label">{active ? "处理中" : failed ? "有异常" : done ? "最近完成" : "待开始"}</span></div><h3>{name}</h3><div className="book-card-meta"><span>{items.length} 个任务</span><span>{done} 个成片</span></div><div className="progress-track"><span style={{ width: `${Math.round((done / items.length) * 100)}%` }} /></div><div className="book-card-footer"><span>最近更新 {new Date(items[0].updated_at || items[0].created_at).toLocaleDateString("zh-CN")}</span><Link href={`/task/${items[0].id}`} aria-label={`打开${name}最近任务`}>打开 →</Link></div></article>; })}</div> : tasksError ? <div className="state-panel"><strong>暂时无法读取项目</strong><span>连接恢复后可重试；如果当前浏览器刚重新建立匿名会话，原会话创建的项目可能不可见。</span><button className="secondary-action" onClick={() => void load()}>重试</button></div> : <div className="state-panel"><span className="state-icon" aria-hidden="true">＋</span><strong>当前账号下没有内容项目</strong><span>项目按浏览器匿名账号隔离；如果清理过网站数据或换了浏览器，旧项目可能属于原来的会话。</span><button className="primary-action" onClick={openForm}>新建第一个项目</button></div>}
      </section>

      <section className="dashboard-section recent-section"><div className="section-heading"><div><p className="eyebrow">生产队列</p><h2>最近任务</h2></div><div className="list-tools"><input aria-label="搜索任务" placeholder="搜索项目" value={query} onChange={e => setQuery(e.target.value)} /><div className="filter-tabs" role="tablist">{FILTERS.map(item => <button key={item.id} className={filter === item.id ? "is-active" : ""} onClick={() => setFilter(item.id)} role="tab" aria-selected={filter === item.id}>{item.label}</button>)}</div></div></div>{tasksLoading ? <div className="state-panel compact"><strong>正在读取最近任务…</strong></div> : visible.length ? <div className="task-table">{visible.slice(0, 12).map(task => <Link className="task-table-row" href={`/task/${task.id}`} key={task.id}><span className="status-dot" style={{ background: STATUS_COLOR[task.status as keyof typeof STATUS_COLOR] || "var(--status-pending)" }} /><span className="task-main"><strong>{task.title || "未命名项目"}</strong><small>{task.source_url || task.id}</small></span><span className={`status-badge status-${task.status}`}>{STATUS_LABEL[task.status] || task.status}</span><span className="task-date">{new Date(task.created_at).toLocaleDateString("zh-CN")}</span><span className="row-arrow" aria-hidden="true">→</span></Link>)}</div> : <div className="state-panel compact"><strong>{tasksError ? "任务暂不可用" : "没有匹配任务"}</strong><span>{tasksError ? "请检查上方连接错误后重试。" : "尝试清空搜索或切换状态筛选。"}</span></div>}</section>
    </div>
  </AppShell>;
}
