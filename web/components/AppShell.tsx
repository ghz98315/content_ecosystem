"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { Task } from "@/lib/types";

export function AppShell({
  children,
  tasks = [],
  currentTaskId,
  onCreateTask,
}: {
  children: React.ReactNode;
  tasks?: Task[];
  currentTaskId?: string;
  onCreateTask?: () => void;
}) {
  const pathname = usePathname();
  const primary = [
    { href: "/", label: "内容项目", short: "项目" },
    { href: "/xhs", label: "知识图文", short: "图文" },
  ];

  return (
    <div className="app-frame">
      <Sidebar tasks={tasks} currentTaskId={currentTaskId} onCreateTask={onCreateTask} />
      <div className="app-surface">
        <header className="topbar">
          <div className="topbar-brand">
            <span className="brand-mark" aria-hidden="true">C</span>
            <span className="brand-name">内容创作台</span>
          </div>
          <nav className="topbar-nav" aria-label="主导航">
            {primary.map(item => {
              const active = item.href === "/" ? pathname === "/" || pathname.startsWith("/task") : pathname.startsWith(item.href);
              return <Link key={item.href} href={item.href} className={`topbar-link${active ? " is-active" : ""}`} aria-current={active ? "page" : undefined}><span className="topbar-link-full">{item.label}</span><span className="topbar-link-short">{item.short}</span></Link>;
            })}
          </nav>
          <div className="topbar-actions">
            <Link href="/voice-cloning" className="topbar-tool">音色管理</Link>
            <span className="workspace-chip"><span className="status-dot" style={{ background: "var(--status-done)" }} />工作区正常</span>
          </div>
        </header>
        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}
