"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { authenticatedFetch } from "@/lib/authenticatedFetch";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { Task } from "@/lib/types";
import { PerformanceImport } from '@/components/PerformanceImport';

type Post = { id: string; task_id: string; platform: string; title: string; post_url: string | null; published_at: string };
type Metric = { id: string; post_id: string; recorded_at: string; views: number; likes: number; comments: number; shares: number; saves: number; follows: number; notes: string };
const platforms: Record<string, string> = { douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书", shipinhao: "视频号", bilibili: "B站", other: "其他" };
const fmt = (n: number) => Number(n || 0).toLocaleString("zh-CN");
const date = (v: string) => new Date(v).toLocaleDateString("zh-CN");
const box: React.CSSProperties = { background: "var(--bg-page)", border: "1px solid var(--border)", borderRadius: 12, padding: 18, marginBottom: 16 };
const input: React.CSSProperties = { padding: "9px 10px", border: "1px solid var(--border)", borderRadius: 7, background: "var(--bg-page)", color: "var(--text-primary)", minWidth: 0 };

export default function PerformancePage() {
  const { userId } = useAnonAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [selectedTask, setSelectedTask] = useState("");
  const [platform, setPlatform] = useState("douyin");
  const [title, setTitle] = useState("");
  const [postUrl, setPostUrl] = useState("");
  const [publishedAt, setPublishedAt] = useState(new Date().toISOString().slice(0, 10));
  const [selectedPost, setSelectedPost] = useState("");
  const [values, setValues] = useState({ views: "", likes: "", comments: "", shares: "", saves: "", follows: "" });
  const [notes, setNotes] = useState("");
  const [filterPlatform, setFilterPlatform] = useState("all");
  const [sortBy, setSortBy] = useState<"views" | "engagement" | "growth">("views");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [truncated, setTruncated] = useState(false);

  const reload = useCallback(async () => {
    const [taskResult, result] = await Promise.all([
      supabase.from("tasks").select("*").order("created_at", { ascending: false }).limit(500),
      authenticatedFetch("/api/performance"),
    ]);
    if (taskResult.error) throw new Error(taskResult.error.message);
    const payload = await result.json();
    if (!result.ok) throw new Error(payload.error || "读取发布数据失败");
    setTasks((taskResult.data || []) as Task[]);
    setPosts(payload.posts || []);
    setMetrics(payload.metrics || []);
    setTruncated(Boolean(payload.truncated));
  }, []);
  useEffect(() => { setSelectedTask(new URLSearchParams(window.location.search).get("task") || ""); }, []);
  useEffect(() => { if (userId) void reload().catch(e => setMessage(e.message)); }, [userId, reload]);

  const taskNames = useMemo(() => new Map(tasks.map(t => [t.id, t.title || t.source_url || t.id])), [tasks]);
  const rows = useMemo(() => posts.map(post => {
    const snapshots = metrics.filter(m => m.post_id === post.id).sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
    const latest = snapshots[0];
    const previous = snapshots[1];
    const interactions = latest ? latest.likes + latest.comments + latest.shares + latest.saves : 0;
    return { post, latest, snapshots: snapshots.length, engagement: latest?.views ? interactions / latest.views : 0,
      growth: latest && previous ? Math.max(0, latest.views - previous.views) : 0 };
  }).filter(row => filterPlatform === "all" || row.post.platform === filterPlatform)
    .sort((a, b) => (sortBy === "views" ? (b.latest?.views || 0) - (a.latest?.views || 0)
      : sortBy === "engagement" ? b.engagement - a.engagement : b.growth - a.growth)), [posts, metrics, filterPlatform, sortBy]);
  const totalViews = rows.reduce((sum, row) => sum + (row.latest?.views || 0), 0);
  const topicRows = useMemo(() => {
    const grouped = new Map<string, { taskId: string; views: number; interactions: number; posts: number; platforms: Set<string> }>();
    for (const row of rows) {
      if (!row.latest) continue;
      const item = grouped.get(row.post.task_id) || { taskId: row.post.task_id, views: 0, interactions: 0, posts: 0, platforms: new Set<string>() };
      item.views += row.latest.views;
      item.interactions += row.latest.likes + row.latest.comments + row.latest.shares + row.latest.saves;
      item.posts += 1;
      item.platforms.add(row.post.platform);
      grouped.set(row.post.task_id, item);
    }
    return [...grouped.values()].sort((a, b) => b.views - a.views);
  }, [rows]);

  async function submit(payload: Record<string, unknown>) {
    setBusy(true); setMessage("");
    try {
      const response = await authenticatedFetch("/api/performance", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "保存失败");
      await reload();
      setMessage("已保存，数据已进入历史记录");
      return result;
    } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); return null; }
    finally { setBusy(false); }
  }

  if (!userId) return <AppShell><div className="page-loading">正在连接工作区...</div></AppShell>;
  return <AppShell tasks={tasks}>
    <div style={{ maxWidth: 1160, margin: "0 auto", padding: "24px 20px 60px" }}>
      <h1 style={{ fontSize: 25, marginBottom: 6 }}>成片发布数据</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 22 }}>作品发布后录入平台后台数据。每次录入保留一条快照，用于比较选题表现；与采集原视频的互动数据分开存放。</p>
      {message && <div role="status" style={{ ...box, padding: 10 }}>{message}</div>}
      {truncated && <div role="alert" style={{ ...box, padding: 10 }}>数据量已超过当前页面读取上限，排行仅包含最近读取的记录。</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
        <section style={box}>
          <h2 style={{ fontSize: 17, marginBottom: 12 }}>登记已发布作品</h2>
          <form onSubmit={async e => { e.preventDefault(); const result = await submit({ action: "post", taskId: selectedTask, platform, title, postUrl, publishedAt: `${publishedAt}T12:00:00+08:00` }); if (result) { setSelectedPost(result.id); setPostUrl(""); } }} style={{ display: "grid", gap: 10 }}>
            <select aria-label="选择成片任务" required value={selectedTask} onChange={e => setSelectedTask(e.target.value)} style={input}><option value="">选择成片任务</option>{tasks.map(t => <option key={t.id} value={t.id}>{t.title || t.source_url || t.id}</option>)}</select>
            <select aria-label="发布平台" value={platform} onChange={e => setPlatform(e.target.value)} style={input}>{Object.entries(platforms).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
            <input aria-label="发布标题" placeholder="发布标题（可留空，沿用任务标题）" maxLength={200} value={title} onChange={e => setTitle(e.target.value)} style={input} />
            <input aria-label="作品链接" placeholder="作品链接 https://...（可选）" value={postUrl} onChange={e => setPostUrl(e.target.value)} style={input} />
            <label>发布日期 <input aria-label="发布日期" type="date" required value={publishedAt} onChange={e => setPublishedAt(e.target.value)} style={input} /></label>
            <button type="submit" disabled={busy || !selectedTask} className="secondary-action">保存作品</button>
          </form>
        </section>
        <section style={box}>
          <h2 style={{ fontSize: 17, marginBottom: 12 }}>录入最新表现</h2>
          <form onSubmit={async e => { e.preventDefault(); const result = await submit({ action: "metric", postId: selectedPost, ...Object.fromEntries(Object.entries(values).map(([k, v]) => [k, Number(v || 0)])), notes }); if (result) setNotes(""); }} style={{ display: "grid", gap: 10 }}>
            <select aria-label="选择已发布作品" required value={selectedPost} onChange={e => setSelectedPost(e.target.value)} style={input}><option value="">选择作品</option>{posts.map(p => <option key={p.id} value={p.id}>{platforms[p.platform]} · {p.title || taskNames.get(p.task_id) || p.id}</option>)}</select>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8 }}>{([ ["views", "播放"], ["likes", "点赞"], ["comments", "评论"], ["shares", "转发"], ["saves", "收藏"], ["follows", "涨粉"] ] as const).map(([key, label]) => <label key={key} style={{ fontSize: 12 }}>{label}<input type="number" min="0" step="1" required aria-label={label} value={values[key]} onChange={e => setValues(v => ({ ...v, [key]: e.target.value }))} style={{ ...input, width: "100%" }} /></label>)}</div>
            <input aria-label="记录备注" placeholder="备注，如发布后24小时（可选）" maxLength={500} value={notes} onChange={e => setNotes(e.target.value)} style={input} />
            <button type="submit" disabled={busy || !selectedPost} className="secondary-action">追加数据快照</button>
          </form>
        </section>
      </div>
      <PerformanceImport posts={posts} defaultPostId={selectedPost} onImported={reload} />
      <section style={box}>
        <h2 style={{ fontSize: 18, marginTop: 0 }}>选题汇总</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: 12 }}>同一任务在多个平台发布时合并展示，便于找出值得继续分发的选题。播放量是各平台最新快照之和，并非去重人数。</p>
        {topicRows.length === 0 ? <p>录入作品数据后显示选题表现。</p> : <div style={{ overflowX: "auto" }}><table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}><thead><tr>{["选题", "作品数", "覆盖平台", "累计播放", "综合互动率"].map(x => <th key={x} style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid var(--border)" }}>{x}</th>)}</tr></thead><tbody>{topicRows.map(row => <tr key={row.taskId}><td style={{ padding: "10px 8px", borderBottom: "1px solid var(--border)" }}><Link href={`/task/${row.taskId}`}>{taskNames.get(row.taskId) || row.taskId}</Link></td><td>{row.posts}</td><td>{[...row.platforms].map(p => platforms[p]).join("、")}</td><td>{fmt(row.views)}</td><td>{row.views ? `${(row.interactions / row.views * 100).toFixed(2)}%` : "—"}</td></tr>)}</tbody></table></div>}
      </section>
      <section style={box}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12, alignItems: "center" }}><div><h2 style={{ fontSize: 18, margin: 0 }}>选题表现</h2><small style={{ color: "var(--text-secondary)" }}>已登记 {rows.length} 条作品 · 最新累计播放 {fmt(totalViews)}</small></div><div style={{ display: "flex", gap: 8 }}><select aria-label="筛选平台" value={filterPlatform} onChange={e => setFilterPlatform(e.target.value)} style={input}><option value="all">全部平台</option>{Object.entries(platforms).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><select aria-label="排行方式" value={sortBy} onChange={e => setSortBy(e.target.value as typeof sortBy)} style={input}><option value="views">按播放量</option><option value="engagement">按互动率</option><option value="growth">按最近增长</option></select></div></div>
        <p style={{ color: "var(--text-secondary)", fontSize: 12 }}>互动率 =（赞 + 评 + 转 + 藏）÷ 播放；最近增长 = 最近两次快照播放差。不同平台的口径可能不同，优先在同平台比较。</p>
        {rows.length === 0 ? <p>还没有发布记录。成片发布后，可在上方登记作品和后台数据。</p> : <div style={{ overflowX: "auto" }}><table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}><thead><tr>{["作品 / 选题", "平台", "发布", "播放", "互动率", "最近增长", "快照"].map(x => <th key={x} style={{ textAlign: "left", padding: "10px 8px", borderBottom: "1px solid var(--border)" }}>{x}</th>)}</tr></thead><tbody>{rows.map(({ post, latest, engagement, growth, snapshots }) => <tr key={post.id}><td style={{ padding: "10px 8px", borderBottom: "1px solid var(--border)" }}><Link href={`/task/${post.task_id}`}>{post.title || taskNames.get(post.task_id) || post.task_id}</Link>{post.post_url && <a href={post.post_url} target="_blank" rel="noopener noreferrer" style={{ marginLeft: 8 }}>查看作品↗</a>}</td><td>{platforms[post.platform]}</td><td>{date(post.published_at)}</td><td>{latest ? fmt(latest.views) : "待录入"}</td><td>{latest?.views ? `${(engagement * 100).toFixed(2)}%` : "—"}</td><td>{snapshots > 1 ? `+${fmt(growth)}` : "—"}</td><td>{snapshots}</td></tr>)}</tbody></table></div>}
      </section>
    </div>
  </AppShell>;
}
