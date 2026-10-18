"use client";
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Sidebar } from './Sidebar';
import { Icon } from './Icon';
import { Task } from '@/lib/types';
import { useWorkspaceStatus } from '@/lib/useWorkspaceStatus';

export function AppShell({ children, tasks, currentTaskId, onCreateTask, activity }: {
  children: React.ReactNode; tasks?: Task[]; currentTaskId?: string; onCreateTask?: () => void; activity?: React.ReactNode;
}) {
  const pathname = usePathname();
  const workspace = useWorkspaceStatus();
  const allTasks = tasks?.length ? tasks : workspace.tasks;
  const current = allTasks.find(task => task.id === currentTaskId);
  const section = pathname.startsWith('/task') ? '内容项目' : pathname.startsWith('/performance') ? '发布数据' : pathname.startsWith('/book-library') ? '书籍库' : pathname.startsWith('/voice-cloning') ? '音色管理' : pathname.startsWith('/video-collection') ? '视频采集' : pathname.startsWith('/xhs') ? '知识图文' : '内容项目';
  const status = { connecting: '连接中', connected: '已连接', error: '连接异常', offline: '网络离线' }[workspace.status];
  const running = allTasks.filter(task => task.status === 'processing');
  return <div className="app-frame">
    <Sidebar tasks={allTasks} currentTaskId={currentTaskId} onCreateTask={onCreateTask} owner={workspace.owner} connection={status}/>
    <div className="app-surface">
      <header className="topbar">
        <nav className="topbar-breadcrumb" aria-label="当前位置"><Link href="/">工作台</Link><Icon name="chevron" size={12}/><span>{section}</span>{current && <><Icon name="chevron" size={12}/><strong title={current.title || current.id}>{current.title || current.id.slice(0, 8)}</strong></>}</nav>
        <div className="topbar-activity">{activity || <><span className={`status-dot${running.length ? ' anim-pulse' : ''}`} style={{ background: running.length ? 'var(--accent)' : 'var(--text-disabled)' }}/>{running.length ? `${running.length} 个任务正在运行` : '准备开始下一次创作'}</>}</div>
        <div className="topbar-actions"><span className={`connection-chip connection-${workspace.status}`} title={`数据库：${status}；${workspace.worker}`}><Icon name="signal" size={14}/><span>{status}</span></span>
          {onCreateTask ? <button className="topbar-create" onClick={onCreateTask}><Icon name="plus" size={15}/><span>新建项目</span></button> : <Link className="topbar-create" href="/?new=1"><Icon name="plus" size={15}/><span>新建项目</span></Link>}
        </div>
      </header>
      <main className="app-main"><div className="route-content" key={pathname}>{children}</div></main>
    </div>
  </div>;
}
