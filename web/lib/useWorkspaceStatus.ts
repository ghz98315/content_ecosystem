"use client";
import { useEffect, useState } from 'react';
import { supabase } from './supabase';
import { Task } from './types';

export function useWorkspaceStatus() {
  const [state, setState] = useState<{ status: 'connecting' | 'connected' | 'error' | 'offline'; owner: string; tasks: Task[]; worker: string }>({ status: 'connecting', owner: '', tasks: [], worker: '尚未检查' });
  useEffect(() => {
    let active = true, loading = false;
    async function load() {
      if (loading) return;
      if (!navigator.onLine) { setState(previous => ({ ...previous, status: 'offline' })); return; }
      loading = true;
      try {
        const { data: session, error: sessionError } = await supabase.auth.getSession();
        if (sessionError) throw sessionError;
        if (!session.session) { if (active) setState(previous => ({ ...previous, status: 'connecting', owner: '', tasks: [] })); return; }
        const owner = session.session.user.id;
        const [tasks, health] = await Promise.all([
          supabase.from('tasks').select('*').eq('owner', owner).neq('status', 'cancelled').order('created_at', { ascending: false }).limit(30),
          fetch('/api/worker-health',{headers:{Authorization:'Bearer '+session.session.access_token},signal:AbortSignal.timeout(7000)}).then(response=>response.ok?response.json():null).catch(()=>null),
        ]);
        if (tasks.error) throw tasks.error;
        const worker = health?.message || '暂时无法检查 Worker 状态';
        if (active) setState({ status: 'connected', owner, tasks: (tasks.data || []) as Task[], worker });
      } catch { if (active) setState(previous => ({ ...previous, status: 'error', worker: '连接恢复后重新检查' })); }
      finally { loading = false; }
    }
    void load();
    const interval = setInterval(() => void load(), 30_000);
    const online = () => void load();
    const offline = () => setState(previous => ({ ...previous, status: 'offline' }));
    window.addEventListener('online', online); window.addEventListener('offline', offline);
    const { data: subscription } = supabase.auth.onAuthStateChange(() => { setTimeout(() => { if (active) void load(); }, 0); });
    return () => { active = false; clearInterval(interval); subscription.subscription.unsubscribe(); window.removeEventListener('online', online); window.removeEventListener('offline', offline); };
  }, []);
  return state;
}

