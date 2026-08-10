"use client";
export const dynamic = "force-dynamic";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { Task } from "@/lib/types";
import { Sidebar } from "@/components/Sidebar";
import { STATUS_COLOR } from "@/lib/types";

export default function HomePage() {
  const { userId, error: authError } = useAnonAuth();
  const [tasks,    setTasks]    = useState<Task[]>([]);
  const [url,      setUrl]      = useState("");
  const [creating, setCreating] = useState(false);
  const [msg,      setMsg]      = useState<{ text: string; ok: boolean } | null>(null);
  const [showForm, setShowForm] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const categories = [
    { value: "health", label: "健康类", available: true },
    { value: "social_science", label: "社科类", available: false },
    { value: "education", label: "教育类", available: false },
  ] as const;

  useEffect(() => {
    if (!userId) return;
    let active = true;
    const load = async () => {
      const { data } = await supabase.from("tasks").select("*").order("created_at", { ascending: false });
      if (active && data) setTasks(data as Task[]);
    };
    load();
    const ch = supabase.channel("tasks-list")
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks" }, load)
      .subscribe();
    return () => { active = false; supabase.removeChannel(ch); };
  }, [userId]);

  const openForm = () => {
    setShowForm(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const createTask = async () => {
    if (!url.trim() || !userId) return;
    setCreating(true); setMsg(null);
    const { error } = await supabase.from("tasks").insert({
      owner: userId,
      source_url: url.trim(),
      status: "pending",
    });
    setCreating(false);
    if (error) {
      setMsg({ text: "创建失败：" + error.message, ok: false });
    } else {
      setUrl(""); setShowForm(false);
      setMsg({ text: "任务已创建，worker 自动开始处理", ok: true });
      setTimeout(() => setMsg(null), 3000);
    }
  };

  if (authError) {
    return (
      <div style={{ display: "flex", height: "100vh" }}>
        <Sidebar tasks={[]} />
        <main className="workspace-main" style={S.main}>
          <p style={{ color: "var(--status-failed)", fontSize: 13 }}>
            登录失败：{authError}
          </p>
        </main>
      </div>
    );
  }

  if (!userId) {
    return (
      <div style={{ display: "flex", height: "100vh" }}>
        <Sidebar tasks={[]} />
        <main className="workspace-main" style={S.main}><p style={{ color: "var(--text-disabled)" }}>连接中…</p></main>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar tasks={tasks} onCreateTask={openForm} />

      <main className="workspace-main">
        <div className="home-content">

          {/* 标题 */}
          <h1 className="home-title" style={{ fontWeight: 700 }}>抖音带货视频创作台</h1>
          <p className="home-subtitle" style={{ fontSize: 13, marginBottom: 28 }}>
            粘贴抖音链接 → 8 阶段自动处理 → 导出带字幕竖版成片
          </p>

          {/* 新建任务表单 */}
          <div className="create-panel" style={{ marginBottom: 32, background: showForm ? "var(--bg-surface)" : "var(--bg-hover)" }}>
            {showForm ? (
              <>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>新建任务</div>
                <div className="category-grid">
                  {categories.map(category => (
                    <button
                      key={category.value}
                      type="button"
                      disabled={!category.available}
                      title={category.available ? category.label : `${category.label}待开发`}
                      style={{
                        minHeight: 38,
                        padding: "6px 8px",
                        border: `1px solid ${category.available ? "#111827" : "var(--border)"}`,
                        borderRadius: "var(--radius-md)",
                        background: category.available ? "#111827" : "var(--bg-hover)",
                        color: category.available ? "#fff" : "var(--text-disabled)",
                        fontSize: 12,
                        cursor: category.available ? "default" : "not-allowed",
                      }}
                    >
                      <span style={{ display: "block", fontWeight: 600 }}>{category.label}</span>
                      {!category.available && <span style={{ display: "block", marginTop: 1, fontSize: 10 }}>待开发</span>}
                    </button>
                  ))}
                </div>
                <div className="create-row">
                  <input
                    ref={inputRef}
                    className="url-input"
                    placeholder="粘贴抖音分享链接或整段分享文案…"
                    value={url}
                    onChange={e => setUrl(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && createTask()}
                  />
                  <button
                    onClick={createTask}
                    disabled={creating || !url.trim()}
                    className="primary-action"
                  >
                    {creating ? "创建中…" : "创建"}
                  </button>
                  <button
                    onClick={() => { setShowForm(false); setUrl(""); }}
                    className="secondary-action"
                  >
                    取消
                  </button>
                </div>
              </>
            ) : (
              <button
                onClick={openForm}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 10,
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--text-secondary)", fontSize: 14, padding: 0,
                }}
              >
                <span style={{ fontSize: 20, fontWeight: 300, lineHeight: 1 }}>＋</span>
                <span>新建任务</span>
              </button>
            )}
          </div>

          {msg && (
            <div style={{
              fontSize: 13, padding: "8px 12px", borderRadius: "var(--radius-md)",
              background: msg.ok ? "#f0fdf4" : "#fff5f5",
              color: msg.ok ? "var(--status-done)" : "var(--status-failed)",
              marginBottom: 16,
              animation: "fadeSlideIn 0.18s ease both",
            }}>
              {msg.text}
            </div>
          )}

          {/* 任务列表 */}
          <div>
            <div style={{
              fontSize: 11, fontWeight: 600, color: "var(--text-disabled)",
              letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 8,
            }}>
              任务列表
            </div>

            {tasks.length === 0 ? (
              <p style={{ fontSize: 13, color: "var(--text-disabled)", padding: "12px 0" }}>
                还没有任务，点击上方新建
              </p>
            ) : (
              <div className="task-list">
                {tasks.map((t, i) => {
                  const dotColor = STATUS_COLOR[t.status as keyof typeof STATUS_COLOR] ?? "var(--status-pending)";
                  const isLast = i === tasks.length - 1;
                  return (
                    <Link
                      key={t.id}
                      href={`/task/${t.id}`}
                      className="task-row"
                    >
                      <span className="status-dot" style={{ background: dotColor }} />
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {t.title || t.source_url || t.id}
                      </span>
                      <span style={{
                        fontSize: 12, color: "var(--text-secondary)",
                        flexShrink: 0,
                      }}>
                        {new Date(t.created_at).toLocaleDateString("zh-CN")}
                      </span>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

const S = {
  main: { flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 32 } as React.CSSProperties,
};
