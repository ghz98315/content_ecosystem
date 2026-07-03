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
      owner: userId, source_url: url.trim(), status: "pending",
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
        <main style={S.main}>
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
        <main style={S.main}><p style={{ color: "var(--text-disabled)" }}>连接中…</p></main>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Sidebar tasks={tasks} onCreateTask={openForm} />

      <main style={{ flex: 1, overflowY: "auto" }}>
        <div style={{ maxWidth: 680, margin: "0 auto", padding: "48px 32px" }}>

          {/* 标题 */}
          <h1 style={{ fontSize: 26, fontWeight: 700, marginBottom: 6 }}>抖音带货视频创作台</h1>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 32 }}>
            粘贴抖音链接 → 8 阶段自动处理 → 导出带字幕竖版成片
          </p>

          {/* 新建任务表单 */}
          <div style={{
            padding: "20px 24px",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            background: showForm ? "var(--bg-page)" : "var(--bg-hover)",
            marginBottom: 32,
            transition: "background 0.15s ease",
          }}>
            {showForm ? (
              <>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>新建任务</div>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    ref={inputRef}
                    style={{
                      flex: 1, padding: "8px 12px",
                      border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
                      fontSize: 14, outline: "none", fontFamily: "var(--font)",
                      transition: "border-color 0.15s ease",
                    }}
                    onFocus={e => (e.target.style.borderColor = "var(--border-focus)")}
                    onBlur={e => (e.target.style.borderColor = "var(--border)")}
                    placeholder="粘贴抖音分享链接或整段分享文案…"
                    value={url}
                    onChange={e => setUrl(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && createTask()}
                  />
                  <button
                    onClick={createTask}
                    disabled={creating || !url.trim()}
                    style={{
                      padding: "8px 18px",
                      background: creating || !url.trim() ? "var(--bg-hover)" : "#111827",
                      color: creating || !url.trim() ? "var(--text-disabled)" : "#fff",
                      border: "none", borderRadius: "var(--radius-md)",
                      fontSize: 14, cursor: creating || !url.trim() ? "not-allowed" : "pointer",
                      transition: "background 0.15s ease",
                    }}
                  >
                    {creating ? "创建中…" : "创建"}
                  </button>
                  <button
                    onClick={() => { setShowForm(false); setUrl(""); }}
                    style={{
                      padding: "8px 12px", background: "none",
                      border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
                      fontSize: 14, cursor: "pointer", color: "var(--text-secondary)",
                    }}
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
              <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", overflow: "hidden" }}>
                {tasks.map((t, i) => {
                  const dotColor = STATUS_COLOR[t.status as keyof typeof STATUS_COLOR] ?? "var(--status-pending)";
                  const isLast = i === tasks.length - 1;
                  return (
                    <Link
                      key={t.id}
                      href={`/task/${t.id}`}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "11px 16px",
                        borderBottom: isLast ? "none" : "1px solid var(--border)",
                        color: "var(--text-primary)", fontSize: 14,
                        transition: "background 0.12s ease",
                      }}
                      className="hoverable"
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
