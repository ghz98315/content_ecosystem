"use client";
import { authenticatedFetch } from "@/lib/authenticatedFetch";


import Link from "next/link";
import { ProductionSetup } from "@/components/ProductionSetup";
import { PRODUCTION_TEMPLATES, ProductionTemplateId, productionTemplate, configureProductionTasks, databaseCategory } from "@/lib/productionTemplates";
import { MUSIC_PRESETS } from "@/lib/musicPresets";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { STATUS_COLOR, Task } from "@/lib/types";
import { compactTitle, splitSourceDescription } from "@/lib/sourceMetadata";

type Artifact = { task_id: string; type: string; meta: Record<string, unknown> | null; created_at: string };
type Stage = { task_id: string; kind: string; seq: number; status: string };
type BookSignal = { task_id: string; detected_title: string | null; detected_author: string | null; confidence: string; evidence: string | null; confirmed_title: string | null; confirmed_author: string | null };
type VoiceProfile = { id: string; display_name: string; provider: "edge" | "cosyvoice2" | "indextts25"; model: string | null; voice_id: string; sample_path: string | null; enabled: boolean; is_default: boolean };
const DEFAULT_EDGE_VOICE_ID = "zh-CN-XiaoxiaoNeural";
const DEFAULT_EDGE_LABEL = "晓晓 · edge-tts";

const STATUS_LABEL: Record<string, string> = {
  configuring: "配置中", pending: "待处理", processing: "处理中", done: "已完成", failed: "异常",
  needs_review: "待确认", cancelled: "已取消",
};

function numberText(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return "—";
  return number >= 10000 ? `${(number / 10000).toFixed(1)}万` : number.toLocaleString("zh-CN");
}

function engagementText(meta: Record<string, unknown>, key: "likes" | "comments" | "shares" | "saves", fallback: unknown, author?: Record<string, unknown>) {
  const saved = author?.source_engagement as {display?:Record<string,unknown>;exact?:Record<string,unknown>} | undefined;
  const display = (meta.stats_display as Record<string, unknown> | undefined) || saved?.display;
  const exact = (meta.stats_exact as Record<string, unknown> | undefined) || saved?.exact;
  const value = display?.[key];
  return typeof value === "string" && value.trim() ? value : numberText(exact?.[key] ?? fallback);
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

function sourcePresentation(task: Task) {
  const url = task.source_url?.trim() || null;
  if (!url) return { platform: "自创", url: null, detail: "附件" };
  if (task.source_platform === "manual") return { platform: "自创", url: null, detail: "附件" };
  if (/(?:douyin\.com|iesdouyin\.com)/i.test(url)) return { platform: "抖音", url, detail: url };
  if (/(?:channels\.weixin\.qq\.com|weixin\.qq\.com\/(?:channels|sph)\/)/i.test(url)) return { platform: "视频号", url, detail: url };
  if (/(?:toutiao\.com|ixigua\.com)/i.test(url)) return { platform: "今日头条", url, detail: url };
  if (/douban\.com/i.test(url)) return { platform: "豆瓣", url, detail: url };
  if (/(?:baijiahao\.baidu\.com|baijiahao\.com)/i.test(url)) return { platform: "百家号", url, detail: url };
  return { platform: "外部来源", url, detail: url };
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
  const [category, setCategory] = useState(() => searchParams.get("category") || "all");
  const [hookScope, setHookScope] = useState<"sentences" | "paragraph">("sentences");
  const [exportingHooks, setExportingHooks] = useState(false);
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
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const [hoveredTitleId, setHoveredTitleId] = useState<string | null>(null);
  const [voiceProfiles, setVoiceProfiles] = useState<VoiceProfile[]>([]);
  const [selectedVoiceProfileId, setSelectedVoiceProfileId] = useState("system-default");
  const [imageProvider, setImageProvider] = useState<"apimart" | "xcode">("apimart");
  const [referenceMode, setReferenceMode] = useState("scene_continuity");
  const generationMode="prompt";
  const [visualMode, setVisualMode] = useState<'ai_images' | 'stock_video'>('ai_images');
  const [bgmVolume, setBgmVolume] = useState("0.15");
  const [ttsRate, setTtsRate] = useState("-8%");
  const [ttsSource, setTtsSource] = useState<'external' | 'automatic'>('external');
  const [productionTemplateId, setProductionTemplateId] = useState<ProductionTemplateId>("health-v1");
  const contentCategory=productionTemplate(productionTemplateId).category;
  const [narrationMode, setNarrationMode] = useState<"single" | "dual_dialogue">("single");
  const [secondaryVoiceProfileId, setSecondaryVoiceProfileId] = useState("");
  const [voiceSampleUrl, setVoiceSampleUrl] = useState<string | null>(null);
  const [voiceSampleState, setVoiceSampleState] = useState<"idle" | "loading" | "missing" | "error">("idle");
  const defaultEdgeProfile = useMemo(() => voiceProfiles.find(profile => profile.provider === "edge" && profile.voice_id === DEFAULT_EDGE_VOICE_ID), [voiceProfiles]);
  const defaultVoiceProfile = useMemo(() => voiceProfiles.find(profile => profile.is_default) || defaultEdgeProfile, [defaultEdgeProfile, voiceProfiles]);
  const defaultVoiceLabel = defaultVoiceProfile ? `${defaultVoiceProfile.display_name} · ${defaultVoiceProfile.model || defaultVoiceProfile.provider}` : DEFAULT_EDGE_LABEL;
  const isDualDialogueProfile = (profile: Pick<VoiceProfile, "provider" | "voice_id">) => profile.provider === "indextts25" && ["podcast_host_male", "podcast_guest_female"].includes(profile.voice_id);
  const dialogueVoiceProfiles = useMemo(() => voiceProfiles.filter(isDualDialogueProfile), [voiceProfiles]);
  const selectableVoiceProfiles = useMemo(() => voiceProfiles.filter(profile => narrationMode === "dual_dialogue" ? isDualDialogueProfile(profile) : profile.id !== defaultVoiceProfile?.id && !isDualDialogueProfile(profile)), [defaultVoiceProfile, narrationMode, voiceProfiles]);

  const loadVersion = useRef(0);
  const load = async () => {
    const request = ++loadVersion.current;
    setLoading(true);
    setLoadError(null);
    const pageSize = 25;
    const from = (page - 1) * pageSize;
    let taskQuery = supabase.rpc("collection_tasks", {
      p_query: query.trim() || null,
      p_status: status === "all" ? null : status,
      p_min_followers: minFollowers ? Number(minFollowers) : 0,
      p_min_comments: minComments ? Number(minComments) : 0,
      p_book_query: bookQuery.trim() || null,
    }, { count: "exact" });
    if (category !== "all") taskQuery = taskQuery.eq("content_category", category);
    const taskResult = await taskQuery.range(from, from + pageSize - 1);
    if (request !== loadVersion.current) return;
    if (taskResult.error) {
      const text = `采集任务加载失败：${taskResult.error.message}`;
      setLoadError(text);
      setMessage(text);
      setLoading(false);
      return;
    }
    const nextTasks = ((taskResult.data || []) as Task[]).filter(task => task.status !== 'cancelled');
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
      supabase.from("artifacts").select("task_id,type,meta,created_at").in("task_id", taskIds).in("type", ["audio", "transcript", "book"]).order("created_at", { ascending: false }),
      supabase.from("stages").select("task_id,kind,seq,status").in("task_id", taskIds).order("seq"),
      supabase.from("task_book_signals").select("task_id,detected_title,detected_author,confidence,evidence,confirmed_title,confirmed_author").in("task_id", taskIds),
    ]);
    if (request !== loadVersion.current) return;
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
    supabase.from("voice_profiles").select("id,display_name,provider,model,voice_id,sample_path,enabled,is_default").eq("enabled", true).order("updated_at", { ascending: false }).then(({ data }) => data && setVoiceProfiles(data as VoiceProfile[]));
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => { clearTimeout(refreshTimer); refreshTimer = setTimeout(() => void load(), 250); };
    const channel = supabase.channel("video-collection-workbench")
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks" }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "artifacts" }, refresh)
      .on("postgres_changes", { event: "*", schema: "public", table: "stages" }, refresh)
      .subscribe();
    return () => { ++loadVersion.current; clearTimeout(refreshTimer); supabase.removeChannel(channel); };
  }, [userId, query, status, category, minFollowers, minComments, bookQuery, page]);

  useEffect(() => {
    if(ttsSource!=='automatic'){setVoiceSampleUrl(null);setVoiceSampleState('idle');return;}
    const profile = selectedVoiceProfileId === "system-default"
      ? defaultVoiceProfile
      : voiceProfiles.find(item => item.id === selectedVoiceProfileId);
    if (!profile?.sample_path) {
      setVoiceSampleUrl(null);
      setVoiceSampleState(profile ? "missing" : "idle");
      return;
    }
    let active = true;
    setVoiceSampleUrl(null);
    setVoiceSampleState("loading");
    authenticatedFetch(`/api/signed-url?path=${encodeURIComponent(profile.sample_path)}`)
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
  }, [defaultVoiceProfile, selectedVoiceProfileId, voiceProfiles,ttsSource]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    if (status !== "all") params.set("status", status);
    if (category !== "all") params.set("category", category);
    if (minFollowers) params.set("minFollowers", minFollowers);
    if (minComments) params.set("minComments", minComments);
    if (bookQuery.trim()) params.set("book", bookQuery.trim());
    if (page > 1) params.set("page", String(page));
    const next = params.toString();
    router.replace(next ? `/video-collection?${next}` : "/video-collection", { scroll: false });
  }, [bookQuery, category, minComments, minFollowers, page, query, router, status]);

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
    let selectedProfile = selectedVoiceProfileId === "system-default"
      ? defaultVoiceProfile
      : voiceProfiles.find(profile => profile.id === selectedVoiceProfileId);
    if (ttsSource === 'automatic' && selectedVoiceProfileId !== "system-default") {
      const { data, error: profileError } = await supabase
        .from("voice_profiles")
        .select("id,display_name,provider,model,voice_id,sample_path,enabled,is_default")
        .eq("id", selectedVoiceProfileId)
        .eq("enabled", true)
        .maybeSingle();
      if (profileError || !data) {
        setCreating(false);
        setSelectedVoiceProfileId("system-default");
        setMessage(profileError?.message || "所选音色已不可用，已切换为新任务默认音色");
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
    if (ttsSource === 'automatic' && narrationMode === "dual_dialogue" && (!secondaryProfile || !isDualDialogueProfile(taskVoice) || !isDualDialogueProfile(secondaryProfile) || taskVoice.id === secondaryProfile.id)) {
      setCreating(false);
      setMessage("双人口播需要分别选择已验收的 IndexTTS 主持人与嘉宾音色");
      return;
    }
    const musicCategory = productionTemplate(productionTemplateId).category;
    const defaultPreset = MUSIC_PRESETS.find(preset => preset.category === musicCategory);
    const { data: createdTasks, error } = await supabase.from("tasks").insert(urls.map(source_url => ({
      owner: userId,
      source_url,
      source_platform: sourcePlatformForUrl(source_url),
      status: "configuring",
      tts_voice_profile_id: taskVoice.id,
      tts_provider: taskVoice.provider,
      tts_model: taskVoice.model,
      tts_voice: taskVoice.voice_id,
      tts_voice_label: taskVoice.display_name,
      content_category: databaseCategory(productionTemplateId),
      bgm_volume: Number(bgmVolume),
      bgm_path: defaultPreset?.path || null,
      bgm_authorization_confirmed: Boolean(defaultPreset),
      narration_mode: ttsSource === 'automatic' ? narrationMode : 'single',
      tts_secondary_voice_profile_id: ttsSource === 'automatic' && narrationMode === 'dual_dialogue' ? secondaryProfile?.id || null : null,
      tts_secondary_provider: ttsSource === 'automatic' && narrationMode === 'dual_dialogue' ? secondaryProfile?.provider || null : null,
      tts_secondary_model: ttsSource === 'automatic' && narrationMode === 'dual_dialogue' ? secondaryProfile?.model || null : null,
      tts_secondary_voice: ttsSource === 'automatic' && narrationMode === 'dual_dialogue' ? secondaryProfile?.voice_id || null : null,
      tts_secondary_voice_label: ttsSource === 'automatic' && narrationMode === 'dual_dialogue' ? secondaryProfile?.display_name || null : null,
      tts_rate: ttsRate,
      tts_source: ttsSource,
    }))).select("id");
    if (!error && createdTasks?.length) {
      try {
        await configureProductionTasks(supabase, createdTasks.map(task => task.id), productionTemplateId, {
          visual_mode: visualMode, stock_policy: visualMode === 'stock_video' ? 'stock-video-v1' : undefined,
          image_provider: imageProvider, image_model: "gpt-image-2", reference_mode: referenceMode,
          generation_mode: generationMode, reference_asset_ids: [],
        });
      } catch (configurationError) {
        setCreating(false);
        setMessage(`模板配置失败，任务未启动：${configurationError instanceof Error ? configurationError.message : "请重试"}`);
        return;
      }
    }
    setCreating(false);
    if (error) setMessage(`导入失败：${error.message}`);
    else {
      setSourceText("");
      if (urls.length === 1 && createdTasks?.[0]?.id) {
        router.push(`/task/${createdTasks[0].id}`);
        return;
      }
      setMessage(`已创建 ${urls.length} 条采集任务，正在等待 Worker 处理。`);
      load();
    }
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
  const downloadSelectedHooks = async () => {
    const taskIds = pagedVisible.filter(task => selectedIds.includes(task.id)).map(task => task.id);
    if (!taskIds.length) { setMessage("请先勾选有原始逐字稿的任务。"); return; }
    setExportingHooks(true);
    try {
      const { data } = await supabase.auth.getSession();
      if (!data.session) throw new Error("登录会话已失效");
      const response = await fetch('/api/collection-hooks', { method: 'POST', headers: { Authorization: `Bearer ${data.session.access_token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ taskIds, scope: hookScope }) });
      if (!response.ok) { const result = await response.json(); throw new Error(result.error || '导出失败'); }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `原始开头钩子_${new Date().toISOString().slice(0,10)}.md`; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage(`已下载 ${taskIds.length} 条任务的原始开头钩子，缺少逐字稿的任务会在文件中说明。`);
    } catch (error) { setMessage(error instanceof Error ? error.message : '导出失败'); }
    finally { setExportingHooks(false); }
  };
  const copyText = async (value: string, label: string) => {
    if (!value) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(value);
      else {
        const area = document.createElement("textarea");
        area.value = value;
        area.setAttribute("readonly", "true");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        if (!document.execCommand("copy")) throw new Error("copy failed");
        area.remove();
      }
      setCopyNotice(`${label}已复制`);
    } catch {
      setCopyNotice("复制失败，请检查浏览器剪贴板权限");
    }
    window.setTimeout(() => setCopyNotice(null), 1800);
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
    try {
      await authenticatedFetch('/api/tasks/cleanup-cancelled', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ taskIds: (data || []).map(task => task.id) }) });
    } catch { /* The daily cleanup retries if immediate cleanup is unavailable. */ }
    setSelectedIds([]);
    setMessage(`已取消 ${data?.length || 0} 个待处理任务。`);
    await load();
  };

  if (!userId && !authError) return <AppShell><div className="page-loading"><div className="skeleton loading-line" /><div className="skeleton loading-block" /></div></AppShell>;
  if (authError) return <AppShell><div className="state-panel error-state" role="alert"><strong>连接工作区失败</strong><span>{authError}</span></div></AppShell>;

  return <AppShell tasks={tasks}>
    <div className="collection-page anim-fade-in">
      <header className="collection-heading"><div><p className="eyebrow">采集与创作</p><h1>把好选题，变成下一条内容。</h1><p>导入来源、确认文案，再制作成片。每一步都清楚可见。</p></div><button type="button" className="secondary-action" onClick={load} disabled={loading} aria-busy={loading}>刷新数据</button></header>
      <section className="collection-create-card" aria-label="新建采集任务">
        <p className="form-hint">文案已经写好？<Link href="/?new=ready_script">导入确认成稿，直接进入配音与画面制作 →</Link></p>
        <div className="creation-card-heading"><div><p className="eyebrow">开始一条新内容</p><h2>选好方向，粘贴链接即可开始</h2><p>常用设置已准备好。文案、配音和素材会按步骤引导你确认。</p></div><span className="creation-badge">支持批量导入</span></div>
        <ProductionSetup templateId={productionTemplateId} onTemplate={id=>{setProductionTemplateId(id);if(productionTemplate(id).category==='scene'){setNarrationMode('single');setSelectedVoiceProfileId('system-default');}}} visualMode={visualMode} onVisualMode={setVisualMode} ttsSource={ttsSource} onTtsSource={setTtsSource} disabled={creating}/>
        <div className="creation-source"><label htmlFor="collection-source-input">视频链接或分享文本</label><textarea id="collection-source-input" value={sourceText} disabled={creating} onChange={event=>setSourceText(event.target.value)} placeholder="粘贴抖音或视频号分享内容；多个链接请换行" aria-label="视频链接或分享文本"/><small>每个链接创建一个独立任务。只导入一条也可以。</small></div>
        <details className="creation-advanced"><summary><span>高级设置 <small>音色、配乐与备用服务，按需调整</small></span><span aria-hidden="true">⌄</span></summary><div className="creation-advanced-content">
          {ttsSource==='automatic'&&<><section className="collection-import" aria-label="自动配音设置"><h3>自动配音</h3><div className="collection-import-footer"><div className="collection-voice-setting"><span>自动配音音色</span><select value={selectedVoiceProfileId} onChange={event => setSelectedVoiceProfileId(event.target.value)} aria-label="任务默认音色">{narrationMode !== "dual_dialogue" && <option value="system-default">{defaultVoiceLabel}（新任务默认）</option>}{selectableVoiceProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}</select>{voiceSampleState === "loading" ? <small>正在加载当前音色样本…</small> : voiceSampleUrl ? <div className="collection-voice-preview"><small>当前音色样本</small><audio controls preload="none" src={voiceSampleUrl} /></div> : <small>{voiceSampleState === "error" ? "样本加载失败，请到音色管理页检查。" : selectedVoiceProfileId === "system-default" ? `${defaultVoiceLabel}，当前未登记可试听样本。` : "该音色未登记样本，无法试听。"}</small>}</div><div className="collection-voice-setting"><span>口播方式</span><select value={narrationMode} onChange={event => { const next = event.target.value as "single" | "dual_dialogue"; setNarrationMode(next); if (next === "dual_dialogue") { setSelectedVoiceProfileId(dialogueVoiceProfiles.find(profile => profile.voice_id === "podcast_host_male")?.id || ""); setSecondaryVoiceProfileId(dialogueVoiceProfiles.find(profile => profile.voice_id === "podcast_guest_female")?.id || ""); } else if (isDualDialogueProfile(voiceProfiles.find(profile => profile.id === selectedVoiceProfileId) || {} as VoiceProfile)) { setSelectedVoiceProfileId("system-default"); setSecondaryVoiceProfileId(""); } }} aria-label="口播方式"><option value="single">单人口播</option><option value="dual_dialogue" disabled={contentCategory === "scene"||dialogueVoiceProfiles.length<2}>双人口播</option></select><small>{narrationMode === "dual_dialogue" ? "角色顺序：第一音色＝男主持人，第二音色＝女嘉宾。改写稿按主持人/嘉宾分段。" : "一套音色完成整条口播"}</small></div>{narrationMode === "dual_dialogue" && <div className="collection-voice-setting"><span>第二音色</span><select value={secondaryVoiceProfileId} onChange={event => setSecondaryVoiceProfileId(event.target.value)} aria-label="第二音色"><option value="">选择第二音色</option>{dialogueVoiceProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}</select><small>角色顺序：第一音色为男主持人；此处第二音色为女嘉宾。两套音色分别快照保存。</small></div>}</div></section>      <section className="collection-import" aria-label="配音速度设置"><div><h2>配音速度</h2><p>速度会随新任务保存，也可在配音阶段调整后重跑。</p></div><div className="collection-import-footer"><div className="collection-voice-setting"><span>口播速度</span><select value={ttsRate} onChange={event => setTtsRate(event.target.value)} aria-label="默认配音速度"><option value="-5%">稍慢 5%</option><option value="-8%">舒缓 8%（推荐）</option><option value="-12%">慢速 12%</option><option value="0%">标准速度</option></select></div></div></section>
</>}
                <section className="collection-import" aria-label="背景音乐预设">
        <div><h2>背景音乐预设</h2><p>国学和健康类新任务会自动保存对应类别的第一首音乐。预设曲目需要在发布简介中署名。</p></div>
        <div className="collection-import-footer"><div className="collection-voice-setting"><span>配音下的背景音乐音量</span><select value={bgmVolume} onChange={event => setBgmVolume(event.target.value)} aria-label="默认背景音乐音量"><option value="0.05">轻柔 5%</option><option value="0.08">轻柔 8%</option><option value="0.12">清晰 12%</option><option value="0.15">标准 15%（推荐）</option><option value="0.20">明显 20%</option><option value="0.30">上限 30%</option></select><small>国学和健康任务自动选用对应类别的第一首预设音乐；可在任务中更换或移除。</small></div></div>
      </section>

          {visualMode==='ai_images'&&<>      <section className="collection-import" aria-label="生图通道设置">
        <div><h3>备用图片服务</h3><p>正常使用无需修改；仅在默认服务异常时切换。</p></div>
        <div className="collection-import-footer">
          <div className="collection-voice-setting">
            <span>服务通道</span>
            <select value={imageProvider} onChange={event => setImageProvider(event.target.value as "apimart" | "xcode")} aria-label="任务生图通道">
              <option value="apimart">APIMart（默认）</option>
              <option value="xcode">xcode.best（备用）</option>
            </select>
            <small>不自动静默切换，避免两个平台重复计费。</small>
          </div>
        </div>
      </section>
<section className="collection-import" aria-label="图片参考设置"><h3>图片参考</h3><label>参考方向<select value={referenceMode} onChange={e=>setReferenceMode(e.target.value)}><option value="scene_continuity">保持镜头风格连续 · 推荐</option><option value="book_cover">借鉴书籍气质</option><option value="none">使用类型默认风格</option></select></label><small>画面风格和比例已随内容类型确定，无需重复选择。</small></section></>}
        </div></details>
        <div className="creation-submit"><p><strong>下一步：确认改写文案</strong><span>{ttsSource==='external'?'确认后上传配音，系统继续处理字幕与画面。':'确认后自动处理配音与画面。'}{visualMode==='stock_video'?'公共素材会先列出清单供你预览。':''}</span></p><button className="primary-action" disabled={creating||!userId||!/https?:\/\//.test(sourceText)} onClick={createTasks}>{creating?'正在创建…':'创建并开始采集'}<span aria-hidden="true"> →</span></button></div>
      </section>
      {(copyNotice || message) && <p className="collection-notice" role="status">{copyNotice || message}</p>}
      <div className={`collection-loading${loading ? '' : ' is-idle'}`} role="status" aria-hidden={!loading}><span className="collection-loading-bar" /><span className="collection-loading-bar short" />正在更新当前页…</div>
      {loadError && <div className="collection-load-error" role="alert"><span>{loadError}</span><button type="button" className="secondary-action" onClick={load} disabled={loading} aria-busy={loading}>重试</button></div>}
      <div className="collection-category-filter"><label htmlFor="collection-category">采集结果类别</label><select id="collection-category" value={category} onChange={event => { setCategory(event.target.value); setPage(1); }}><option value="all">全部类别</option><option value="guoxue">国学类</option><option value="health">健康类</option><option value="scene">场景类</option><option value="social_science">社科类</option><option value="education">教育类</option></select></div>
      <section className="collection-results" aria-labelledby="collection-results-heading"><div className="collection-toolbar"><div><h2 id="collection-results-heading">采集结果 <span>{totalTasks}</span></h2><p>查看来源表现、制作进度，找到值得继续创作的选题。</p></div><div className="collection-filters"><input value={query} onChange={event => { setQuery(event.target.value); setPage(1); }} placeholder="搜索标题、作者或链接" aria-label="搜索采集任务" /><select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }} aria-label="按任务状态筛选"><option value="all">全部状态</option>{Object.entries(STATUS_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><input value={minFollowers} onChange={event => { setMinFollowers(event.target.value.replace(/[^0-9]/g, "")); setPage(1); }} inputMode="numeric" placeholder="最低粉丝" aria-label="最低粉丝数" /><input value={minComments} onChange={event => { setMinComments(event.target.value.replace(/[^0-9]/g, "")); setPage(1); }} inputMode="numeric" placeholder="最低评论" aria-label="最低评论数" /></div></div>
        {selectedIds.length > 0 && <div className="collection-bulk-bar"><span>已选 {selectedIds.length} 条</span><select value={hookScope} onChange={event => setHookScope(event.target.value as "sentences" | "paragraph")} aria-label="开头钩子提取范围"><option value="sentences">开头前四句</option><option value="paragraph">开头第一段</option></select><button className="secondary-action" onClick={downloadSelectedHooks} disabled={exportingHooks}>{exportingHooks ? '正在整理…' : '下载原始开头钩子 Markdown'}</button><button className="secondary-action" onClick={copySelectedUrls}>复制来源链接</button><button className="secondary-action" onClick={cancelSelectedPending}>取消待处理任务</button><button className="collection-bulk-clear" onClick={() => setSelectedIds([])}>清除选择</button></div>}
        <div className="collection-table-wrap"><table className="collection-table"><thead><tr><th><input type="checkbox" checked={allPageSelected} onChange={togglePageSelection} aria-label="选择当前页任务" /></th><th>序号</th><th>标题</th><th>识别书籍</th><th>采集来源</th><th>作者</th><th>粉丝</th><th>时长</th><th>采集时间</th><th>点赞</th><th>评论</th><th>分享</th><th>收藏</th><th>任务状态</th><th>操作</th></tr></thead><tbody>{pagedVisible.map((task, index) => {
          const meta = artifactByTask.get(task.id)?.meta || {};
          const author = (task.author || {}) as Record<string, unknown>;
          const taskStages = stagesByTask.get(task.id) || [];
          const signal = bookSignalByTask.get(task.id);
          const book = (meta.book_signal || meta.book || meta.book_info || {}) as Record<string, unknown>;
          const finalBookTitle = meta.book_name ? String(meta.book_name) : "";
          const bookTitle = signal?.confirmed_title || finalBookTitle || signal?.detected_title || (book.title ? String(book.title) : "");
          const parsedSource = splitSourceDescription(task.title);
          const sourceTags = task.source_tags?.length ? task.source_tags : parsedSource.tags;
          const fullTitle = parsedSource.title || "未取得标题";
          const source = sourcePresentation(task);
          const action = task.status === "needs_review" ? "去确认" : task.status === "done" ? "查看成片" : task.status === "failed" ? "查看异常" : "查看任务";
          return <tr key={task.id}><td><input type="checkbox" checked={selectedIds.includes(task.id)} onChange={() => toggleSelected(task.id)} aria-label={`选择 ${task.title || task.id}`} /></td><td>{String((currentPage - 1) * pageSize + index + 1).padStart(2, "0")}</td><td className="collection-title"><button type="button" className="collection-title-copy" title={`${fullTitle}\n点击复制完整标题`} aria-label={`复制完整标题：${fullTitle}`} onClick={() => void copyText(fullTitle, "标题")}>{compactTitle(fullTitle)}</button>{sourceTags.length > 0 && <div className="collection-tags" aria-label="来源标签">{sourceTags.map(tag => <span key={tag}>#{tag}</span>)}</div>}</td><td>{bookTitle ? <><strong>《{bookTitle.replace(/^《|》$/g, "")}》</strong><small>{signal?.confirmed_title ? "已确认书名" : finalBookTitle ? "书籍阶段识别" : "逐字稿识别"}</small></> : <span className="muted">等待书籍阶段</span>}</td><td className="collection-source"><strong>{source.platform}</strong>{source.url ? <a href={source.url} target="_blank" rel="noreferrer" title={source.detail}>{source.detail}</a> : <small>{source.detail}</small>}</td><td>{author.name ? `@${String(author.name)}` : "—"}</td><td>{numberText(author.fans_count || author.follower_count)}</td><td>{durationText(meta.duration)}</td><td>{dateText(task.created_at)}</td><td>{engagementText(meta,"likes",meta.digg_count ?? task.play_count,author)}</td><td>{engagementText(meta,"comments",meta.comment_count,author)}</td><td>{engagementText(meta,"shares",meta.share_count,author)}</td><td>{engagementText(meta,"saves",meta.collect_count,author)}</td><td><span className={`status-badge status-${task.status}`}><i style={{ background: STATUS_COLOR[task.status as keyof typeof STATUS_COLOR] }} />{STATUS_LABEL[task.status] || task.status}</span><small className="collection-stage">{currentStage(taskStages)}</small></td><td><Link className="collection-action" href={`/task/${task.id}`}>{action}</Link><button className="collection-copy" onClick={() => task.source_url && void copyText(task.source_url, "来源链接")}>复制链接</button></td></tr>;
        })}</tbody></table>{!totalTasks && <div className="state-panel compact"><strong>没有匹配的采集任务</strong><span>调整筛选条件，或从上方导入新的视频链接。</span></div>}</div>
        <div className="collection-mobile-list">{pagedVisible.map(task => {
          const meta = artifactByTask.get(task.id)?.meta || {};
          const author = (task.author || {}) as Record<string, unknown>;
          const taskStages = stagesByTask.get(task.id) || [];
          const action = task.status === "needs_review" ? "去确认" : task.status === "done" ? "查看成片" : task.status === "failed" ? "查看异常" : "查看任务";
          const signal = bookSignalByTask.get(task.id);
          const book = (meta.book_signal || meta.book || meta.book_info || {}) as Record<string, unknown>;
          const finalBookTitle = meta.book_name ? String(meta.book_name) : "";
          const bookTitle = signal?.confirmed_title || finalBookTitle || signal?.detected_title || (book.title ? String(book.title) : "");
          const parsedSource = splitSourceDescription(task.title);
          const sourceTags = task.source_tags?.length ? task.source_tags : parsedSource.tags;
          const fullTitle = parsedSource.title || "未取得标题";
          return <article className="collection-mobile-card" key={task.id}>
            <header><div className="collection-mobile-card-heading"><input type="checkbox" checked={selectedIds.includes(task.id)} onChange={() => toggleSelected(task.id)} aria-label={`选择 ${task.title || task.id}`} /><div><button type="button" className="collection-title-copy" title={`${fullTitle}\n点击复制完整标题`} aria-label={`复制完整标题：${fullTitle}`} onClick={() => void copyText(fullTitle, "标题")}>{compactTitle(fullTitle)}</button><span>{author.name ? `@${String(author.name)}` : "—"}</span></div></div><span className={`status-badge status-${task.status}`}><i style={{ background: STATUS_COLOR[task.status as keyof typeof STATUS_COLOR] }} />{STATUS_LABEL[task.status] || task.status}</span></header>
            {sourceTags.length > 0 && <div className="collection-tags">{sourceTags.map(tag => <span key={tag}>#{tag}</span>)}</div>}
            <a className="collection-mobile-source" href={task.source_url || undefined} target="_blank" rel="noreferrer">{task.source_url || "—"}</a>
            <p className="collection-mobile-book">书籍信号：{bookTitle ? `《${bookTitle}》（${signal?.confirmed_title ? "已确认" : signal?.confidence === "medium" ? "中置信度" : "低置信度"}）` : "待逐字稿识别"}</p>
            <dl><div><dt>粉丝</dt><dd>{numberText(author.fans_count || author.follower_count)}</dd></div><div><dt>时长</dt><dd>{durationText(meta.duration)}</dd></div><div><dt>点赞</dt><dd>{engagementText(meta,"likes",meta.digg_count ?? task.play_count,author)}</dd></div><div><dt>评论</dt><dd>{engagementText(meta,"comments",meta.comment_count,author)}</dd></div><div><dt>分享</dt><dd>{engagementText(meta,"shares",meta.share_count,author)}</dd></div><div><dt>收藏</dt><dd>{engagementText(meta,"saves",meta.collect_count,author)}</dd></div></dl>
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
