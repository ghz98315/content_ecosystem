"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Task } from "@/lib/types";
import { STATUS_COLOR } from "@/lib/types";

const TOOLS = [
  { id: "douyin",       label: "抖音带货视频", icon: "🎬", href: "/",    active: true  },
  { id: "xiaohongshu",  label: "小红书笔记",   icon: "📕", href: "/xhs", active: true  },
];

interface Props {
  tasks: Task[];
  currentTaskId?: string;
  onCreateTask?: () => void;
}

export function Sidebar({ tasks, currentTaskId, onCreateTask }: Props) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    const saved = localStorage.getItem("sidebar-collapsed");
    if (saved !== null) setCollapsed(saved === "true");
  }, []);
  useEffect(() => { setMobileOpen(false); }, [pathname]);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebar-collapsed", String(next));
  };

  const w = collapsed ? "var(--sidebar-collapsed)" : "var(--sidebar-width)";
  const normalizedQuery = query.trim().toLowerCase();
  const visibleTasks = tasks.filter(task => {
    const label = (task.title || task.source_url || task.id).toLowerCase();
    return (!normalizedQuery || label.includes(normalizedQuery))
      && (statusFilter === "all" || task.status === statusFilter);
  });

  return (
    <>
    <button
      className="mobile-sidebar-trigger"
      aria-label="打开导航"
      aria-expanded={mobileOpen}
      onClick={() => setMobileOpen(true)}
    >☰</button>
    {mobileOpen && <button className="mobile-sidebar-backdrop" aria-label="关闭导航" onClick={() => setMobileOpen(false)} />}
    <aside
      className={`app-sidebar${mobileOpen ? " is-mobile-open" : ""}`}
      style={{
        width: w,
        minWidth: w,
        height: "100vh",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        transition: "width 0.22s cubic-bezier(0.4,0,0.2,1), min-width 0.22s cubic-bezier(0.4,0,0.2,1)",
        background: "var(--bg-page)",
      }}
    >
      {/* 顶部 logo + 汉堡 */}
      <div style={{
        height: 48, display: "flex", alignItems: "center",
        padding: "0 12px", gap: 8, flexShrink: 0,
        borderBottom: "1px solid var(--border)",
      }}>
        <button
          onClick={toggle}
          title={collapsed ? "展开侧边栏" : "收起侧边栏"}
          style={{
            width: 28, height: 28, border: "none", background: "none",
            borderRadius: "var(--radius-sm)", display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 4, flexShrink: 0,
            cursor: "pointer", padding: 0,
          }}
          className="hoverable"
        >
          {[0, 1, 2].map(i => (
            <span key={i} style={{
              display: "block", width: 14, height: 1.5,
              background: "var(--text-secondary)", borderRadius: 1,
            }} />
          ))}
        </button>
        {!collapsed && (
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap" }}>
            内容创作台
          </span>
        )}
      </div>

      {/* 工具导航 */}
      <nav style={{ padding: "8px 6px 4px", flexShrink: 0 }}>
        {!collapsed && (
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-disabled)", padding: "4px 6px 2px", letterSpacing: "0.06em" }}>
            工具
          </div>
        )}
        {TOOLS.map(tool => {
          const isActive = tool.active && (
            tool.href === "/" ? pathname === "/" || pathname.startsWith("/task") : pathname.startsWith(tool.href)
          );
          return (
            <div key={tool.id} style={{ position: "relative" }}>
              {tool.active ? (
                <Link
                  href={tool.href}
                  title={collapsed ? tool.label : undefined}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 8px", borderRadius: "var(--radius-md)",
                    background: isActive ? "var(--bg-active)" : "transparent",
                    color: "var(--text-primary)", fontSize: 13,
                    transition: "background 0.12s ease",
                    overflow: "hidden", whiteSpace: "nowrap",
                  }}
                  className={isActive ? "" : "hoverable"}
                >
                  <span style={{ fontSize: 15, flexShrink: 0 }}>{tool.icon}</span>
                  {!collapsed && <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{tool.label}</span>}
                </Link>
              ) : (
                <div
                  title={collapsed ? tool.label : undefined}
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 8px", borderRadius: "var(--radius-md)",
                    color: "var(--text-disabled)", fontSize: 13,
                    overflow: "hidden", whiteSpace: "nowrap", cursor: "default",
                  }}
                >
                  <span style={{ fontSize: 15, flexShrink: 0, opacity: 0.5 }}>{tool.icon}</span>
                  {!collapsed && (
                    <>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{tool.label}</span>
                      <span style={{
                        fontSize: 10, padding: "1px 5px", borderRadius: 10,
                        background: "var(--bg-hover)", color: "var(--text-disabled)", flexShrink: 0,
                      }}>即将上线</span>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* 分割线 */}
      <div style={{ height: 1, background: "var(--border)", margin: "4px 12px", flexShrink: 0 }} />

      {/* 新建任务 */}
      <div style={{ padding: "6px 6px 2px", flexShrink: 0 }}>
        <button
          onClick={onCreateTask}
          title={collapsed ? "新建任务" : undefined}
          style={{
            width: "100%", display: "flex", alignItems: "center", gap: 8,
            padding: "6px 8px", border: "none", background: "none",
            borderRadius: "var(--radius-md)", fontSize: 13,
            color: "var(--text-secondary)", textAlign: "left",
            transition: "background 0.12s ease", overflow: "hidden", whiteSpace: "nowrap",
          }}
          className="hoverable"
        >
          <span style={{ fontSize: 16, fontWeight: 300, flexShrink: 0, lineHeight: 1 }}>＋</span>
          {!collapsed && <span>新建任务</span>}
        </button>
      </div>

      {/* 任务列表 */}
      <div style={{ flex: 1, overflowY: "auto", padding: "2px 6px 12px" }}>
        {!collapsed && tasks.length > 0 && (
          <div className="sidebar-task-tools">
            <input aria-label="搜索任务" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索任务" />
            <select aria-label="按状态筛选" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}>
              <option value="all">全部状态</option>
              <option value="processing">处理中</option>
              <option value="needs_review">待确认</option>
              <option value="done">已完成</option>
              <option value="failed">失败</option>
            </select>
          </div>
        )}
        {!collapsed && tasks.length === 0 && (
          <div className="sidebar-empty" role="status">
            <span className="empty-state-icon" aria-hidden="true">＋</span>
            <span>还没有任务</span>
            {onCreateTask && <button onClick={onCreateTask}>创建第一个任务</button>}
          </div>
        )}
        {!collapsed && tasks.length > 0 && visibleTasks.length === 0 && (
          <p style={{ fontSize: 12, color: "var(--text-disabled)", padding: "10px 8px" }}>没有匹配的任务</p>
        )}
        {visibleTasks.map(t => {
          const isCurrent = t.id === currentTaskId;
          const dotColor = STATUS_COLOR[t.status as keyof typeof STATUS_COLOR] ?? "var(--status-pending)";
          return (
            <Link
              key={t.id}
              href={`/task/${t.id}`}
              title={collapsed ? (t.title || t.source_url || t.id) : undefined}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "5px 8px", borderRadius: "var(--radius-md)",
                background: isCurrent ? "var(--bg-active)" : "transparent",
                color: "var(--text-primary)", fontSize: 13,
                transition: "background 0.12s ease",
                overflow: "hidden", whiteSpace: "nowrap",
              }}
              className={isCurrent ? "" : "hoverable"}
            >
              <span
                className="status-dot"
                style={{ background: dotColor }}
              />
              {!collapsed && (
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>
                  {t.title || t.source_url || t.id}
                </span>
              )}
            </Link>
          );
        })}
      </div>
    </aside>
    </>
  );
}
