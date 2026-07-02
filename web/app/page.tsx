"use client";
export const dynamic = "force-dynamic";
import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { useAnonAuth } from "@/lib/useAnonAuth";
import { Task } from "@/lib/types";

export default function HomePage() {
  const { userId, error: authError } = useAnonAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [url, setUrl] = useState("");
  const [creating, setCreating] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // 拉列表 + 订阅 tasks 变更
  useEffect(() => {
    if (!userId) return;
    let active = true;

    const load = async () => {
      const { data } = await supabase
        .from("tasks")
        .select("*")
        .order("created_at", { ascending: false });
      if (active && data) setTasks(data as Task[]);
    };
    load();

    const ch = supabase
      .channel("tasks-list")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "tasks" },
        () => load()
      )
      .subscribe();

    return () => {
      active = false;
      supabase.removeChannel(ch);
    };
  }, [userId]);

  const createTask = async () => {
    if (!url.trim() || !userId) return;
    setCreating(true);
    setMsg(null);
    const { error } = await supabase
      .from("tasks")
      .insert({ owner: userId, source_url: url.trim(), status: "pending" });
    setCreating(false);
    if (error) setMsg("创建失败：" + error.message);
    else {
      setUrl("");
      setMsg("已创建，worker 会自动开始处理");
    }
  };

  if (authError)
    return (
      <main style={S.main}>
        <p style={{ color: "#dc2626" }}>
          登录失败：{authError}
          <br />
          请确认 Supabase 已开启 Anonymous 登录，且 .env.local 已填 URL/anon key。
        </p>
      </main>
    );

  if (!userId)
    return (
      <main style={S.main}>
        <p>连接中…</p>
      </main>
    );

  return (
    <main style={S.main}>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>图书带货视频创作台</h1>
      <p style={{ color: "#6b7280", marginTop: 0, fontSize: 13 }}>
        粘贴抖音分享链接 → 8 阶段自动跑 → 导出带字幕竖版成片
      </p>

      <div style={S.createRow}>
        <input
          style={S.input}
          placeholder="粘贴抖音分享链接或整段分享文案…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && createTask()}
        />
        <button style={S.btn} onClick={createTask} disabled={creating}>
          {creating ? "创建中…" : "新建任务"}
        </button>
      </div>
      {msg && <p style={{ fontSize: 13, color: "#6b7280" }}>{msg}</p>}

      <h2 style={{ fontSize: 15, marginTop: 24 }}>任务列表</h2>
      {tasks.length === 0 && (
        <p style={{ color: "#9ca3af", fontSize: 13 }}>还没有任务</p>
      )}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {tasks.map((t) => (
          <li key={t.id} style={S.taskItem}>
            <Link href={`/task/${t.id}`} style={S.taskLink}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {t.title || t.source_url || t.id}
              </span>
              <span style={S.badge}>{t.status}</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}

const S: Record<string, React.CSSProperties> = {
  main: { maxWidth: 760, margin: "40px auto", padding: "0 16px", fontFamily: "system-ui, sans-serif" },
  createRow: { display: "flex", gap: 8, marginTop: 16 },
  input: { flex: 1, padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 },
  btn: { padding: "8px 16px", background: "#111827", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14 },
  taskItem: { borderBottom: "1px solid #f3f4f6" },
  taskLink: { display: "flex", alignItems: "center", gap: 8, padding: "10px 4px", textDecoration: "none", color: "#111827", fontSize: 14 },
  badge: { fontSize: 12, color: "#6b7280", background: "#f3f4f6", padding: "2px 8px", borderRadius: 10 },
};
