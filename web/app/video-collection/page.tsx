"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { STATUS_COLOR, Task } from "@/lib/types";

type Artifact = { task_id: string; meta: Record<string, unknown> | null; created_at: string };
type Stage = { task_id: string; kind: string; seq: number; status: string };
type BookSignal = { task_id: string; detected_title: string | null; detected_author: string | null; confidence: string; evidence: string | null; confirmed_title: string | null; confirmed_author: string | null };
type VoiceProfile = { id: string; display_name: string; provider: "edge" | "cosyvoice2"; model: string | null; voice_id: string; sample_path: string | null; enabled: boolean };
const DEFAULT_EDGE_VOICE_ID = "zh-CN-XiaoxiaoNeural";
const DEFAULT_EDGE_LABEL = "晓晓 · edge-tts";

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

function sourcePlatformForUrl(url: string): "douyin" | "wechat_channels" {
  return /(?:channels\.weixin\.qq\.com|weixin\.qq\.com\/(?:channels|sph)\/)/i.test(url)
    ? "wechat_channels"
    : "douyin";
}

function VideoCollectionContent() {
  const { userId, error: authError } = useAnonAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [stages, setStages] = useState<Stage[]>([]);
  const [bookSignals, setBookSignals] = useState<BookSignal[]>([]);
  const [sourceText, setSourceText] = useState("");
  const [query, setQuery] = useState(() => searchParams.get("q") || "");
  const [status, setStatus] = useState(() => searchParams.get("status") || "all");
  const [minFollowers, setMinFollowers] = useState(() => searchParams.get("minFollowers") || "");
  const [minComments, setMinComments] = useState(() => searchParams.get("minComments") || "");
  const [bookQuery, setBookQuery] = useState(() => searchParams.get("book") || "");
  const [page, setPage] = useState(() => Math.max(1, Number(searchParams.get("page") || 1)));
  const [totalTasks, setTotalTasks] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [voiceProfiles, setVoiceProfiles] = useState<VoiceProfile[]>([]);
  const [selectedVoiceProfileId, setSelectedVoiceProfileId] = useState("system-default");
  const [contentCategory, setContentCategory] = useState<"health" | "social_science" | "education">("health");
  const [narrationMode, setNarrationMode] = useState<"single" | "dual_dialogue">("single");
  const [secondaryVoiceProfileId, setSecondaryVoiceProfileId] = useState("");
  const [voiceSampleUrl, setVoiceSampleUrl] = useState<string | null>(null);
  const [voiceSampleState, setVoiceSampleState] = useState<"idle" | "loading" | "missing" | "error">("idle");
  const defaultEdgeProfile = useMemo(() => voiceProfiles.find(profile => profile.provider === "edge" && profile.voice_id === DEFAULT_EDGE_VOICE_ID), [voiceProfiles]);
  const selectableVoiceProfiles = useMemo(() => voiceProfiles.filter(profile => profile.id !== defaultEdgeProfile?.id), [defaultEdgeProfile, voiceProfiles]);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    const pageSize = 25;
    const from = (page - 1) * pageSize;
    const taskResult = await supabase.rpc("collection_tasks", {
      p_query: query.trim() || null,
      p_status: status === "all" ? null : status,
      p_min_followers: minFollowers ? Number(minFollowers) : 0,
      p_min_comments: minComments ? Number(minComments) : 0,
      p_book_query: bookQuery.trim() || null,
    }, { count: "exact" }).range(from, from + pageSize - 1);
    if (taskResult.error) {
      const text = `采集任务加载失败：${taskResult.error.message}`;
      setLoadError(text);
      setMessage(text);
      setLoading(false);
      return;
    }
    const nextTasks = (taskResult.data || []) as Task[];
    setTasks(nextTasks);
    setTotalTasks(taskResult.count || 0);
    const taskIds = nextTasks.map(task => task.id);
    if (!taskIds.length) {
      setArtifacts([]);
      setStages([]);
      setBookSignals([]);
      setSelectedIds([]);
      setLoading(false);
      return;
    }
    const [artifactResult, stageResult, bookSignalResult] = await Promise.all([
      supabase.from("artifacts").select("task_id,meta,created_at").in("task_id", taskIds).in("type", ["audio", "transcript"]).order("created_at", { ascending: false }),
      supabase.from("stages").select("task_id,kind,seq,status").in("task_id", taskIds).order("seq"),
      supabase.from("task_book_signals").select("task_id,detected_title,detected_author,confidence,evidence,confirmed_title,confirmed_author").in("task_id", taskIds),
    ]);
    if (artifactResult.error || stageResult.error || bookSignalResult.error) {
      const text = `关联产物加载失败：${artifactResult.error?.message || stageResult.error?.message || bookSignalResult.error?.message || "请稍后重试"}`;
      setLoadError(text);
      setMessage(text);
    }
    setArtifacts((artifactResult.data || []) as Artifact[]);
    setStages((stageResult.data || []) as Stage[]);
    setBookSignals((bookSignalResult.data || []) as BookSignal[]);
    setSelectedIds(current => current.filter(id => taskIds.includes(id)));
    setLoading(false);
  };

  useEffect(() => {
    if (!userId) return;
    load();
    supabase.from("voice_profiles").select("id,display_name,provider,model,voice_id,sample_path,enabled").eq("enabled", true).order("updated_at", { ascending: false }).then(({ data }) => data && setVoiceProfiles(data as VoiceProfile[]));
    const channel = supabase.channel("video-collection-workbench")
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks" }, load)
      .on("postgres_changes", { event: "*", schema: "public", table: "artifacts" }, load)
      .on("postgres_changes", { event: "*", schema: "public", table: "stages" }, load)
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [userId, query, status, minFollowers, minComments, bookQuery, page]);

  useEffect(() => {
    const profile = selectedVoiceProfileId === "system-default"
      ? defaultEdgeProfile
      : voiceProfiles.find(item => item.id === selectedVoiceProfileId);
    if (!profile?.sample_path) {
      setVoiceSampleUrl(null);
      setVoiceSampleState(profile ? "missing" : "idle");
      return;
    }
    let active = true;
    setVoiceSampleUrl(null);
    setVoiceSampleState("loading");
    fetch(`/api/signed-url?path=${encodeURIComponent(profile.sample_path)}`)
      .then(async response => {
        if (!response.ok) throw new Error("sample unavailable");
        return response.json() as Promise<{ signedUrl?: string }>;
      })
      .then(result => {
        if (!active || !result.signedUrl) return;
        setVoiceSampleUrl(result.signedUrl);
        setVoiceSampleState("idle");
      })
      .catch(() => { if (active) setVoiceSampleState("error"); });
    return () => { active = false; };
  }, [defaultEdgeProfile, selectedVoiceProfileId, voiceProfiles]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (status !== "all") params.set("status", status);
    if (minFollowers) params.set("minFollowers", minFollowers);
    if (minComments) params.set("minComments", minComments);
    if (bookQuery.trim()) params.set("book", bookQuery.trim());
    if (page > 1) params.set("page", String(page));
    const next = params.toString();
    router.replace(next ? `/video-collection?${next}` : "/video-collection", { scroll: false });
  }, [bookQuery, minComments, minFollowers, page, query, router, status]);

  const artifactByTask = useMemo(() => {
    const map = new Map<string, Artifact>();
    artifacts.forEach(artifact => {
      const existing = map.get(artifact.task_id);
      map.set(artifact.task_id, {
        ...artifact,
        meta: { ...(artifact.meta || {}), ...(existing?.meta || {}) },
      });
    });
    return map;
  }, [artifacts]);
  const stagesByTask = useMemo(() => {
    const map = new Map<string, Stage[]>();
    stages.forEach(stage => map.set(stage.task_id, [...(map.get(stage.task_id) || []), stage]));
    return map;
  }, [stages]);
  const bookSignalByTask = useMemo(() => new Map(bookSignals.map(signal => [signal.task_id, signal])), [bookSignals]);
  const pageSize = 25;
  const totalPages = Math.max(1, Math.ceil(totalTasks / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedVisible = tasks;

  const createTasks = async () => {
    const urls = Array.from(new Set((sourceText.match(/https?:\/\/[^\s]+/g) || []).map(url => url.replace(/[，。；！）】]+$/, ""))));
    if (!userId || !urls.length || creating) return;
    setCreating(true);
    let selectedProfile = voiceProfiles.find(profile => profile.id === selectedVoiceProfileId);
    if (selectedVoiceProfileId !== "system-default") {
      const { data, error: profileError } = await supabase
        .from("voice_profiles")
        .select("id,display_name,provider,model,voice_id,sample_path,enabled")
        .eq("id", selectedVoiceProfileId)
        .eq("enabled", true)
        .maybeSingle();
      if (profileError || !data) {
        setCreating(false);
        setSelectedVoiceProfileId("system-default");
        setMessage(profileError?.message || "所选音色已不可用，已切换为系统默认 Edge 音色");
        return;
      }
      selectedProfile = data as VoiceProfile;
    }
    const taskVoice = selectedProfile ?? {
      id: null,
      display_name: DEFAULT_EDGE_LABEL,
      provider: "edge" as const,
      model: "edge-tts",
      voice_id: DEFAULT_EDGE_VOICE_ID,
    };
    const secondaryProfile = voiceProfiles.find(profile => profile.id === secondaryVoiceProfileId);
    if (narrationMode === "dual_dialogue" && !secondaryProfile) {
      setCreating(false);
      setMessage("双人口播需要选择第二音色");
      return;
    }
    const { error } = await supabase.from("tasks").insert(urls.map(source_url => ({
      owner: userId,
      source_url,
      source_platform: sourcePlatformForUrl(source_url),
      status: "pending",
      tts_voice_profile_id: taskVoice.id,
      tts_provider: taskVoice.provider,
      tts_model: taskVoice.model,
      tts_voice: taskVoice.voice_id,
      tts_voice_label: taskVoice.display_name,
      content_category: contentCategory,
      narration_mode: narrationMode,
      tts_secondary_voice_profile_id: secondaryProfile?.id || null,
      tts_secondary_provider: secondaryProfile?.provider || null,
      tts_secondary_model: secondaryProfile?.model || null,
      tts_secondary_voice: secondaryProfile?.voice_id || null,
      tts_secondary_voice_label: secondaryProfile?.display_name || null,
    })));
    setCreating(false);
    if (error) setMessage(`导入失败：${error.message}`);
    else { setSourceText(""); setMessage(`已创建 ${urls.length} 条采集任务，正在等待 Worker 处理。`); load(); }
  };

  const toggleSelected = (taskId: string) => {
    setSelectedIds(current => current.includes(taskId) ? current.filter(id => id !== taskId) : [...current, taskId]);
  };
  const pageIds = pagedVisible.map(task => task.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every(id => selectedIds.includes(id));
  const togglePageSelection = () => setSelectedIds(current => allPageSelected
    ? current.filter(id => !pageIds.includes(id))
    : Array.from(new Set([...current, ...pageIds])));
  const copySelectedUrls = async () => {
    const urls = pagedVisible.filter(task => selectedIds.includes(task.id)).map(task => task.source_url).filter((url): url is string => Boolean(url));
    if (!urls.length) {
      setMessage("所选任务没有可复制的来源链接。");
      return;
    }
    try {
      await navigator.clipboard.writeText(urls.join("\n"));
      setMessage(`已复制 ${urls.length} 条来源链接。`);
    } catch {
      setMessage("复制失败，请检查浏览器剪贴板权限。");
    }
  };
  const cancelSelectedPending = async () => {
    const pendingIds = pagedVisible.filter(task => selectedIds.includes(task.id) && task.status === "pending").map(task => task.id);
    if (!pendingIds.length) {
      setMessage("只有待处理任务可以批量取消。");
      return;
    }
    if (!window.confirm(`确认取消 ${pendingIds.length} 个待处理任务？`)) return;
    setLoading(true);
    const { data, error } = await supabase.from("tasks").update({ status: "cancelled" }).in("id", pendingIds).eq("status", "pending").select("id");
    if (error) {
      setMessage(`批量取消失败：${error.message}`);
      setLoading(false);
      return;
    }
    await supabase.from("stages").update({ status: "cancelled" }).in("task_id", pendingIds).eq("status", "pending");
    setSelectedIds([]);
    setMessage(`已取消 ${data?.length || 0} 个待处理任务。`);
    await load();
  };

  if (!userId && !authError) return <AppShell><div className="page-loading"><div className="skeleton loading-line" /><div className="skeleton loading-block" /></div></AppShell>;
  if (authError) return <AppShell><div className="state-panel error-state" role="alert"><strong>连接工作区失败</strong><span>{authError}</span></div></AppShell>;

  return <AppShell tasks={tasks}>
    <div className="collection-page anim-fade-in">
      <header className="collection-heading"><div><p className="eyebrow">素材运营台</p><h1>视频采集工作台</h1><p>批量导入来源视频，按采集结果、互动数据和任务进度统一查看。</p></div><button type="button" className="secondary-action" onClick={load} disabled={loading} aria-busy={loading}>刷新数据</button></header>
      <section className="collection-import" aria-label="批量导入视频"><div><h2>导入视频来源</h2><p>支持多行 URL 或包含链接的分享文本，每个链接将创建一条独立任务。</p></div><textarea value={sourceText} onChange={event => setSourceText(event.target.value)} placeholder="粘贴视频链接或分享文本，一行一个" aria-label="视频链接或分享文本" /><div className="collection-import-footer"><div className="collection-voice-setting"><span>内容流程</span><select value={contentCategory} onChange={event => setContentCategory(event.target.value as "health" | "social_science" | "education")} aria-label="内容流程模板"><option value="health">健康类书籍</option><option value="social_science">历史社科</option><option value="education">经管书籍</option></select><small>{contentCategory === "health" ? "健康合规红线与温润生活视觉" : contentCategory === "social_science" ? "史实边界、克制叙事与史料感画面" : "数据边界、非投顾表达与现代商务画面"}</small></div><div className="collection-voice-setting"><span>任务配音快照</span><select value={selectedVoiceProfileId} onChange={event => setSelectedVoiceProfileId(event.target.value)} aria-label="任务默认音色"><option value="system-default">{DEFAULT_EDGE_LABEL}（系统默认）</option>{selectableVoiceProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.display_name} · {profile.model || profile.provider}</option>)}</select>{voiceSampleState === "loading" ? <small>正在加载当前音色样本…</small> : voiceSampleUrl ? <div className="collection-voice-preview"><small>当前音色样本</small><audio controls preload="none" src={voiceSampleUrl} /></div> : <small>{voiceSampleState === "error" ? "样本加载失败，请到音色管理页检查。" : selectedVoiceProfileId === "system-default" ? "使用 `zh-CN-XiaoxiaoNeural`，当前未登记可试听样本。" : "该音色未登记样本，无法试听。"}</small>}</div><button className="primary-action" disabled={creating || !/https?:\/\//.test(sourceText)} onClick={createTasks}>{creating ? "导入中…" : "导入并创建任务"}</button></div></section>
      <section className="collection-import" aria-label="内容生产设置"><div><h2>内容生产设置</h2><p>设置会随新任务保存；不影响已创建任务。</p></div><div className="collection-import-footer"><div className="collection-voice-setting"><span>口播方式</span><select value={narrationMode} onChange={event => setNarrationMode(event.target.value as "single" | "dual_dialogue")} aria-label="口播方式"><option value="single">单人口播</option><option value="dual_dialogue">双人口播</option></select><small>{narrationMode === "dual_dialogue" ? "改写稿按主持人/嘉宾分段，分别使用两套音色" : "一套音色完成整条口播"}</small></div>{narrationMode === "dual_dialogue" && <div className="collection-voice-setting"><span>第二音色</span><select value={secondaryVoiceProfileId} onChange={event => setSecondaryVoiceProfileId(event.target.value)} aria-label="第二音色"><option value="">选择第二音色</option>{voiceProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.display_name} · {profile.model || profile.provider}</option>)}</select><small>主持人与嘉宾音色分别快照保存</small></div>}</div></section>
      {message && <p className="collection-notice" role="status">{message}</p>}
      {loading && <div className="collection-loading" role="status"><span className="collection-loading-bar" /><span className="collection-loading-bar short" />正在更新当前页…</div>}
      {loadError && <div className="collection-load-error" role="alert"><span>{loadError}</span><button type="button" className="secondary-action" onClick={load} disabled={loading} aria-busy={loading}>重试</button></div>}
      <section className="collection-results" aria-labelledby="collection-results-heading"><div className="collection-toolbar"><div><h2 id="collection-results-heading">采集结果 <span>{totalTasks}</span></h2><p>每页读取 25 条任务及其关联产物；缺失字段不会以示例数据替代。</p></div><div className="collection-filters"><input value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} placeholder="搜索标题、作者或链接" aria-label="搜索采集任务" /><select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }} aria-label="按任务状态筛选"><option value="all">全部状态</option>{Object.entries(STATUS_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><input value={minFollowers} onChange={event => { setMinFollowers(event.target.value.replace(/[^0-9]/g, "")); setPage(1); }} inputMode="numeric" placeholder="最低粉丝" aria-label="最低粉丝数" /><input value={minComments} onChange={event => { setMinComments(event.target.value.replace(/[^0-9]/g, "")); setPage(1); }} inputMode="numeric" placeholder="最低评论" aria-label="最低评论数" /></div></div>
        {selectedIds.length > 0 && <div className="collection-bulk-bar"><span>已选 {selectedIds.length} 条</span><button className="secondary-action" onClick={copySelectedUrls}>复制来源链接</button><button className="secondary-action" onClick={cancelSelectedPending}>取消待处理任务</button><button className="collection-bulk-clear" onClick={() => setSelectedIds([])}>清除选择</button></div>}
        <div className="collection-table-wrap"><table className="collection-table"><thead><tr><th><input type="checkbox" checked={allPageSelected} onChange={togglePageSelection} aria-label="选择当前页任务" /></th><th>序号</th><th>标题</th><th>识别书籍</th><th>描述</th><th>作者</th><th>粉丝</th><th>时长</th><th>采集时间</th><th>点赞</th><th>评论</th><th>分享</th><th>收藏</th><th>任务状态</th><th>操作</th></tr></thead><tbody>{pagedVisible.map((task, index) => {
          const meta = artifactByTask.get(task.id)?.meta || {};
          const author = (task.author || {}) as Record<string, unknown>;
          const taskStages = stagesByTask.get(task.id) || [];
          const signal = bookSignalByTask.get(task.id);
          const book = (meta.book_signal || meta.book || meta.book_info || {}) as Record<string, unknown>;
          const bookTitle = signal?.confirmed_title || signal?.detected_title || (book.title ? String(book.title) : "");
          const action = task.status === "needs_review" ? "去确认" : task.status === "done" ? "查看成片" : task.status === "failed" ? "查看异常" : "查看任务";
          return <tr key={task.id}><td><input type="checkbox" checked={selectedIds.includes(task.id)} onChange={() => toggleSelected(task.id)} aria-label={`选择 ${task.title || task.id}`} /></td><td>{String((currentPage - 1) * pageSize + index + 1).padStart(2, "0")}</td><td className="collection-title"><strong>{task.title || "未取得标题"}</strong><a href={task.source_url || undefined} target="_blank" rel="noreferrer">来源链接</a></td><td>{book.title ? <><strong>《{String(book.title)}》</strong><small>{book.author ? String(book.author) : "已识别"}</small></> : <span className="muted">等待逐字稿</span>}</td><td className="collection-description">{String(meta.desc || meta.description || "—")}</td><td>{author.name ? `@${String(author.name)}` : "—"}</td><td>{numberText(author.fans_count || author.follower_count)}</td><td>{durationText(meta.duration)}</td><td>{dateText(task.created_at)}</td><td>{numberText(meta.digg_count ?? task.play_count)}</td><td>{numberText(meta.comment_count)}</td><td>{numberText(meta.share_count)}</td><td>{numberText(meta.collect_count)}</td><td><span className={`status-badge status-${task.status}`}><i style={{ background: STATUS_COLOR[task.status as keyof typeof STATUS_COLOR] }} />{STATUS_LABEL[task.status] || task.status}</span><small className="collection-stage">{currentStage(taskStages)}</small></td><td><Link className="collection-action" href={`/task/${task.id}`}>{action}</Link><button className="collection-copy" onClick={() => task.source_url && navigator.clipboard.writeText(task.source_url)}>复制链接</button></td></tr>;
        })}</tbody></table>{!totalTasks && <div className="state-panel compact"><strong>没有匹配的采集任务</strong><span>调整筛选条件，或从上方导入新的视频链接。</span></div>}</div>
        <div className="collection-mobile-list">{pagedVisible.map(task => {
          const meta = artifactByTask.get(task.id)?.meta || {};
          const author = (task.author || {}) as Record<string, unknown>;
          const taskStages = stagesByTask.get(task.id) || [];
          const action = task.status === "needs_review" ? "去确认" : task.status === "done" ? "查看成片" : task.status === "failed" ? "查看异常" : "查看任务";
          const signal = bookSignalByTask.get(task.id);
          const book = (meta.book_signal || meta.book || meta.book_info || {}) as Record<string, unknown>;
          const bookTitle = signal?.confirmed_title || signal?.detected_title || (book.title ? String(book.title) : "");
          return <article className="collection-mobile-card" key={task.id}>
            <header><div className="collection-mobile-card-heading"><input type="checkbox" checked={selectedIds.includes(task.id)} onChange={() => toggleSelected(task.id)} aria-label={`选择 ${task.title || task.id}`} /><div><strong>{task.title || "未取得标题"}</strong><span>{author.name ? `@${String(author.name)}` : "—"}</span></div></div><span className={`status-badge status-${task.status}`}><i style={{ background: STATUS_COLOR[task.status as keyof typeof STATUS_COLOR] }} />{STATUS_LABEL[task.status] || task.status}</span></header>
            <a className="collection-mobile-source" href={task.source_url || undefined} target="_blank" rel="noreferrer">{task.source_url || "—"}</a>
            <p className="collection-mobile-book">书籍信号：{bookTitle ? `《${bookTitle}》（${signal?.confirmed_title ? "已确认" : signal?.confidence === "medium" ? "中置信度" : "低置信度"}）` : "待逐字稿识别"}</p>
            <dl><div><dt>粉丝</dt><dd>{numberText(author.fans_count || author.follower_count)}</dd></div><div><dt>时长</dt><dd>{durationText(meta.duration)}</dd></div><div><dt>点赞</dt><dd>{numberText(meta.digg_count ?? task.play_count)}</dd></div><div><dt>评论</dt><dd>{numberText(meta.comment_count)}</dd></div><div><dt>分享</dt><dd>{numberText(meta.share_count)}</dd></div><div><dt>收藏</dt><dd>{numberText(meta.collect_count)}</dd></div></dl>
            <footer><span>阶段 {currentStage(taskStages)} · 采集 {dateText(task.created_at)}</span><Link className="collection-action" href={`/task/${task.id}`}>{action}</Link></footer>
          </article>;
        })}</div>
        {totalTasks > 0 && <div className="collection-pagination"><span>第 {currentPage} / {totalPages} 页 · 共 {totalTasks} 条</span><button className="secondary-action" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>上一页</button><button className="secondary-action" disabled={currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}>下一页</button></div>}
      </section>
    </div>
  </AppShell>;
}

export default function VideoCollectionPage() {
  return (
    <Suspense fallback={<AppShell><div className="page-loading"><div className="skeleton loading-line" /><div className="skeleton loading-block" /></div></AppShell>}>
      <VideoCollectionContent />
    </Suspense>
  );
}
