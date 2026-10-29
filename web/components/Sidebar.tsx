"use client";
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Task, STATUS_LABEL } from '@/lib/types';
import { Icon } from './Icon';
const GROUPS = [
  { label: '创作', items: [{ href: '/', label: '内容项目', icon: 'projects' }, { href: '/video-collection', label: '视频采集', icon: 'collection' }, { href: '/xhs', label: '知识图文', icon: 'knowledge' }] },
  { label: '素材', items: [{ href: '/book-library', label: '书籍库', icon: 'book' }, { href: '/voice-cloning', label: '音色管理', icon: 'voice' }] },
  { label: '运营', items: [{ href: '/performance', label: '发布数据', icon: 'performance' }, { href: '/account', label: '账号管理', icon: 'projects' }] },
];
export function Sidebar({ tasks, currentTaskId, onCreateTask, owner = '', connection = '连接中' }: { tasks: Task[]; currentTaskId?: string; onCreateTask?: () => void; owner?: string; connection?: string }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false), [mobileOpen, setMobileOpen] = useState(false), [query, setQuery] = useState(''), [filter, setFilter] = useState('all');
  useEffect(() => { try { setCollapsed(localStorage.getItem('sidebar-collapsed') === 'true'); } catch { /* Optional preference. */ } }, []);
  useEffect(() => { setMobileOpen(false); }, [pathname, currentTaskId]);
  useEffect(() => { if (!mobileOpen) return; const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileOpen(false); }; window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape); }, [mobileOpen]);
  const toggle = () => { setCollapsed(previous => { try { localStorage.setItem('sidebar-collapsed', String(!previous)); } catch { /* Optional preference. */ } return !previous; }); };
  const activeTasks = tasks.filter(task => task.status !== 'cancelled');
  const visible = activeTasks.filter(task => (!query.trim() || `${task.title || ''} ${task.id}`.toLowerCase().includes(query.trim().toLowerCase())) && (filter === 'all' || task.status === filter));
  const review = tasks.filter(task => task.status === 'needs_review').length;
  return <>
    <button className="mobile-sidebar-trigger" aria-label="打开导航" aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)}><Icon name="panel"/></button>
    {mobileOpen && <button className="mobile-sidebar-backdrop" aria-label="关闭导航" onClick={() => setMobileOpen(false)}/>}
    <aside className={`app-sidebar studio-sidebar${collapsed ? ' is-collapsed' : ''}${mobileOpen ? ' is-mobile-open' : ''}`} aria-label="工作台导航">
      <div className="sidebar-brand"><Link href="/" className="studio-mark" aria-label="映作工作台首页"><Icon name="projects" size={20}/></Link><div className="sidebar-expanded"><strong>映作工作台</strong><small>YINGZUO STUDIO</small></div><button className="sidebar-collapse" aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'} title={collapsed ? '展开侧边栏' : '收起侧边栏'} onClick={toggle}><Icon name="panel" size={16}/></button></div>
      <div className="sidebar-create-wrap">{onCreateTask ? <button className="sidebar-create" onClick={onCreateTask} title="新建项目"><Icon name="plus"/><span className="sidebar-expanded">新建项目</span></button> : <Link className="sidebar-create" href="/?new=1" title="新建项目"><Icon name="plus"/><span className="sidebar-expanded">新建项目</span></Link>}</div>
      <nav className="sidebar-navigation">{GROUPS.map(group => <div className="sidebar-group" key={group.label}><span className="sidebar-section-label sidebar-expanded">{group.label}</span>{group.items.map(item => {
        const active = item.href === '/' ? pathname === '/' || pathname.startsWith('/task') : pathname.startsWith(item.href);
        return <Link key={item.href} href={item.href} title={item.label} aria-current={active ? 'page' : undefined} className={`sidebar-nav-item${active ? ' is-active' : ''}`}><Icon name={item.icon}/><span className="sidebar-expanded">{item.label}</span>{item.href === '/' && review > 0 && <b className="sidebar-count sidebar-expanded">{review}</b>}</Link>;
      })}</div>)}</nav>
      <div className="sidebar-recents"><div className="sidebar-recents-heading sidebar-expanded"><span className="sidebar-section-label">最近任务</span><small>{activeTasks.length}</small></div>
        <div className="sidebar-task-tools sidebar-expanded"><input aria-label="搜索任务" placeholder="搜索任务…" value={query} onChange={event => setQuery(event.target.value)}/><select aria-label="按状态筛选" value={filter} onChange={event => setFilter(event.target.value)}><option value="all">全部状态</option><option value="processing">运行中</option><option value="needs_review">待确认</option><option value="done">已完成</option><option value="failed">失败</option></select></div>
        <div className="sidebar-task-list">{visible.slice(0, 20).map(task => <Link key={task.id} href={`/task/${task.id}`} title={`${task.title || task.id} · ${STATUS_LABEL[task.status as keyof typeof STATUS_LABEL] || task.status}`} className={`sidebar-task${task.id === currentTaskId ? ' is-active' : ''}`}><span className={`task-signal signal-${task.status}${task.status === 'processing' ? ' anim-pulse' : ''}`}/><span className="sidebar-expanded"><strong>{task.title || '未命名项目'}</strong><small>{STATUS_LABEL[task.status as keyof typeof STATUS_LABEL] || task.status}</small></span></Link>)}{!visible.length && <p className="sidebar-empty sidebar-expanded">{tasks.length ? '没有匹配的任务' : '从一个链接开始创作'}</p>}</div>
      </div>
      <footer className="sidebar-footer" title={`当前工作区 ${owner || '连接中'}；${connection}`}><span className="workspace-avatar">{owner ? owner.slice(0, 2).toUpperCase() : '—'}</span><div className="sidebar-expanded"><strong>当前工作区</strong><small>{owner ? `${owner.slice(0, 8)} · ${connection}` : connection}</small></div></footer>
    </aside>
  </>;
}
