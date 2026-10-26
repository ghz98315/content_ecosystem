"use client";
export const dynamic = "force-dynamic";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ProductionSetup } from "@/components/ProductionSetup";
import { MUSIC_PRESETS } from "@/lib/musicPresets";
import { PRODUCTION_TEMPLATES, ProductionTemplateId, productionTemplate, configureProductionTasks, databaseCategory } from "@/lib/productionTemplates";
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
  const [inputMode, setInputMode] = useState<'link' | 'ready_script'>('link');
  const [scriptTitle, setScriptTitle] = useState('');
  const [readyScript, setReadyScript] = useState('');
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [creating, setCreating] = useState(false);
  const [templateId, setTemplateId] = useState<ProductionTemplateId>("health-v1");
  const [ttsSource, setTtsSource] = useState<'external' | 'automatic'>('external');
  const [visualMode,setVisualMode]=useState<'ai_images'|'stock_video'>('ai_images');
  const [tasksLoading, setTasksLoading] = useState(true);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { const mode = new URLSearchParams(window.location.search).get('new'); if (mode === '1' || mode === 'ready_script') setShowForm(true); if (mode === 'ready_script') setInputMode('ready_script'); }, []);

  const load = async () => {
    setTasksLoading(true);
    setTasksError(null);
    try {
      const { data, error } = await supabase.from("tasks").select("*").neq("status", "cancelled").order("created_at", { ascending: false });
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
    const script = readyScript.trim();
    if (!userId || creating || (inputMode === 'link' ? !url.trim() : script.length < 20 || script.length > 30000)) return;
    setCreating(true); setMsg(null);
    let voice={id:null as string|null,provider:'edge',model:'edge-tts',voice_id:'zh-CN-XiaoxiaoNeural',display_name:'晓晓 · edge-tts'};
    if(ttsSource==='automatic'){
      const profiles=await supabase.from('voice_profiles').select('id,provider,model,voice_id,display_name,is_default').eq('enabled',true).order('updated_at',{ascending:false});
      if(profiles.error){setCreating(false);setMsg({text:'默认音色读取失败，请重试，或选择上传配音。',ok:false});return;}
      const selected=profiles.data?.find(p=>p.is_default)||profiles.data?.find(p=>p.provider==='edge'&&p.voice_id==='zh-CN-XiaoxiaoNeural');
      if(selected)voice={...voice,...selected};
    }
    const { data: createdTask, error } = await supabase.from("tasks").insert({
      owner: userId,
      source_url: inputMode === 'link' ? url.trim() : null,
      source_platform: inputMode === 'ready_script' ? 'manual' : /weixin\.qq\.com|channels\.weixin\.qq\.com/i.test(url) ? "wechat_channels" : "douyin",
      title: inputMode === 'ready_script' ? (scriptTitle.trim() || script.split(/[。！？\n]/)[0].slice(0, 36) || '已导入成稿') : null,
      bgm_path: MUSIC_PRESETS.find(p=>p.category===productionTemplate(templateId).category)?.path || null,
      bgm_volume:0.15,
      bgm_authorization_confirmed: Boolean(MUSIC_PRESETS.find(p=>p.category===productionTemplate(templateId).category)),
      tts_rate:"-8%",
      status: "configuring",
      content_category: databaseCategory(templateId),
      tts_source: ttsSource,
      tts_voice_profile_id:voice.id,
      tts_provider:voice.provider,
      tts_model:voice.model,
      tts_voice:voice.voice_id,
      tts_voice_label:voice.display_name,
    }).select("id").single();
    if (!error && createdTask?.id) {
      try {
        if (inputMode === 'ready_script') {
          const saved = await supabase.from('stages').update({ params: { input_mode: 'ready_script', ready_script_text: script } })
            .eq('task_id', createdTask.id).eq('kind', 'ingest').select('id');
          if (saved.error || saved.data?.length !== 1) throw new Error(saved.error?.message || '成稿保存失败');
        }
        await configureProductionTasks(supabase, [createdTask.id], templateId, { visual_mode:visualMode,image_provider: "apimart", image_model: "gpt-image-2", generation_mode: "prompt", reference_mode: "scene_continuity" });
      } catch (configurationError) {
        await supabase.from('tasks').update({ status: 'cancelled' }).eq('id', createdTask.id).eq('status', 'configuring');
        setCreating(false);
        setMsg({ text: `模板配置失败，任务未启动：${configurationError instanceof Error ? configurationError.message : "请重试"}`, ok: false });
        return;
      }
    }
    setCreating(false);
    if (error) setMsg({ text: `创建失败：${error.message}`, ok: false });
    else { setUrl(""); setReadyScript(''); setScriptTitle(''); setShowForm(false); setMsg({ text: inputMode === 'ready_script' ? '成稿已提交，正在进入配音与画面流程' : '任务已创建，正在进入采集阶段', ok: true }); load(); setTimeout(() => setMsg(null), 3500); }
  };

  if (!userId && !authError) return <AppShell><div className="page-loading"><div className="skeleton loading-line" /><div className="skeleton loading-block" /></div></AppShell>;
  if (authError) return <AppShell><div className="state-panel error-state" role="alert"><strong>连接工作区失败</strong><span>{authError}</span></div></AppShell>;

  return <AppShell tasks={tasks} onCreateTask={openForm}>
    <div className="dashboard-page anim-fade-in">
      <section className="dashboard-heading">
        <div><p className="eyebrow">创作工作台 / OVERVIEW</p><h1>让每个好选题，都有下一步。</h1><p className="dashboard-lede">从链接到成片，在一个工作台里完成。</p></div>
        <button className="primary-action dashboard-create" onClick={openForm}><span aria-hidden="true">＋</span> 新建项目</button>
      </section>

      <section className="welcome-path" aria-label="新手开始指引"><div><span>01</span><p><strong>导入一个选题</strong><small>支持来源链接或已确认成稿</small></p></div><div><span>02</span><p><strong>确认文案与配音</strong><small>按步骤检查，保留你的判断</small></p></div><div><span>03</span><p><strong>预览并导出成片</strong><small>文字、配乐与素材可再调整</small></p></div><Link href="/video-collection">批量采集 →</Link></section>

      <section className="metric-grid" aria-label="项目概览">
        {[{ label: "全部项目", value: stats.total, hint: "累计创建" }, { label: "正在处理", value: stats.active, hint: "后台处理中" }, { label: "待确认", value: stats.review, hint: "需要你的判断" }, { label: "已产出成片", value: stats.done, hint: "可下载发布" }].map((item, i) => <div className={`metric-card metric-${i}`} key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>{item.hint}</small></div>)}
      </section>

      {showForm && <section className="create-panel create-panel-large anim-fade-in" aria-label="新建项目">
        <div className="section-heading"><div><h2>新建内容项目</h2><p>可从视频链接采集，也可直接导入已经确认的成稿。</p></div><button className="icon-button" onClick={() => setShowForm(false)} aria-label="关闭新建项目">×</button></div>
        <div className="create-input-mode" role="group" aria-label="文案来源"><button type="button" className={inputMode === 'link' ? 'is-active' : ''} disabled={creating} onClick={() => setInputMode('link')}>从链接采集并改写</button><button type="button" className={inputMode === 'ready_script' ? 'is-active' : ''} disabled={creating} onClick={() => setInputMode('ready_script')}>已有成稿，直接制作</button></div>
        <ProductionSetup templateId={templateId} onTemplate={setTemplateId} visualMode={visualMode} onVisualMode={setVisualMode} ttsSource={ttsSource} onTtsSource={setTtsSource} inputMode={inputMode} disabled={creating}/>
        {inputMode === 'link' ? <div className="create-row"><input ref={inputRef} className="url-input" placeholder="粘贴抖音或视频号分享链接" value={url} onChange={e => setUrl(e.target.value)} onKeyDown={e => e.key === "Enter" && createTask()} /><button className="primary-action" onClick={createTask} disabled={creating || !url.trim()}>{creating ? "创建中…" : "开始处理"}</button><button className="secondary-action" onClick={() => { setShowForm(false); setUrl(""); }}>取消</button></div> : <div className="ready-script-entry"><label>项目标题（可选）<input value={scriptTitle} maxLength={80} onChange={e => setScriptTitle(e.target.value)} placeholder="用于工作台识别任务" /></label><label>已确认的完整口播文案<textarea value={readyScript} maxLength={30000} onChange={e => setReadyScript(e.target.value)} placeholder="粘贴已改写、无需再次二创的最终文案；保留自然分段和标点" /></label><small>{readyScript.trim().length} / 30000 字符。系统将原样保存此稿，跳过采集、逐字稿、清洗和改写。</small><div className="create-row"><button className="primary-action" onClick={createTask} disabled={creating || readyScript.trim().length < 20}>{creating ? '创建中…' : '导入成稿并开始制作'}</button><button className="secondary-action" onClick={() => setShowForm(false)}>取消</button></div></div>}
        <p className="form-hint">{inputMode === 'link' ? '支持单条链接；多条内容可到视频采集工作台批量创建。' : '导入成稿不会调用二创模型；配音、画面和成片沿用所选内容类型的模板。'}国学和健康类默认配乐可在配音步骤调整。</p>
      </section>}

      {msg && <div className={`notice ${msg.ok ? "notice-success" : "notice-error"}`} role={msg.ok ? "status" : "alert"}>{msg.text}</div>}
      {tasksError && <div className="notice notice-error" role="alert"><span>读取项目失败：{tasksError}</span><button className="secondary-action" onClick={() => void load()}>重试</button></div>}

      <section className="dashboard-section"><div className="section-heading"><div><p className="eyebrow">项目总览</p><h2>最近创作项目</h2></div><Link href="/xhs" className="text-link">打开知识图文 →</Link></div>
        {tasksLoading ? <div className="state-panel"><strong>正在读取项目</strong><span>正在同步当前账号可访问的任务。</span></div> : groups.length ? <div className="book-grid">{groups.map(([name, items]) => { const done = items.filter(t => t.status === "done").length; const active = items.filter(t => t.status === "processing").length; const failed = items.filter(t => t.status === "failed").length; return <article className="book-card" key={name}><div className="book-card-top"><span className="book-glyph" aria-hidden="true">▤</span><span className="status-label">{active ? "处理中" : failed ? "有异常" : done ? "最近完成" : "待开始"}</span></div><h3>{name}</h3><div className="book-card-meta"><span>{items.length} 个任务</span><span>{done} 个成片</span></div><div className="progress-track"><span style={{ width: `${Math.round((done / items.length) * 100)}%` }} /></div><div className="book-card-footer"><span>最近更新 {new Date(items[0].updated_at || items[0].created_at).toLocaleDateString("zh-CN")}</span><Link href={`/task/${items[0].id}`} aria-label={`打开${name}最近任务`}>打开 →</Link></div></article>; })}</div> : tasksError ? <div className="state-panel"><strong>暂时无法读取项目</strong><span>连接恢复后可重试；如果当前浏览器刚重新建立匿名会话，原会话创建的项目可能不可见。</span><button className="secondary-action" onClick={() => void load()}>重试</button></div> : <div className="state-panel"><span className="state-icon" aria-hidden="true">＋</span><strong>当前账号下没有内容项目</strong><span>从一个选题开始，完成你的第一条内容。</span><button className="primary-action" onClick={openForm}>新建第一个项目</button></div>}
      </section>

      <section className="dashboard-section recent-section"><div className="section-heading"><div><p className="eyebrow">生产队列</p><h2>最近任务</h2></div><div className="list-tools"><input aria-label="搜索任务" placeholder="搜索项目" value={query} onChange={e => setQuery(e.target.value)} /><div className="filter-tabs" role="tablist">{FILTERS.map(item => <button key={item.id} className={filter === item.id ? "is-active" : ""} onClick={() => setFilter(item.id)} role="tab" aria-selected={filter === item.id}>{item.label}</button>)}</div></div></div>{tasksLoading ? <div className="state-panel compact"><strong>正在读取最近任务…</strong></div> : visible.length ? <div className="task-table">{visible.slice(0, 12).map(task => <Link className="task-table-row" href={`/task/${task.id}`} key={task.id}><span className="status-dot" style={{ background: STATUS_COLOR[task.status as keyof typeof STATUS_COLOR] || "var(--status-pending)" }} /><span className="task-main"><strong>{task.title || "未命名项目"}</strong><small>{task.source_url || task.id}</small></span><span className={`status-badge status-${task.status}`}>{STATUS_LABEL[task.status] || task.status}</span><span className="task-date">{new Date(task.created_at).toLocaleDateString("zh-CN")}</span><span className="row-arrow" aria-hidden="true">→</span></Link>)}</div> : <div className="state-panel compact"><strong>{tasksError ? "任务暂不可用" : "没有匹配任务"}</strong><span>{tasksError ? "请检查上方连接错误后重试。" : "尝试清空搜索或切换状态筛选。"}</span></div>}</section>
    </div>
  </AppShell>;
}
