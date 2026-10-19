"use client";
import { useEffect, useState } from 'react';
import { supabase } from './supabase';
import { Stage, Task } from './types';
import { TimingRecord, workflowTiming } from './workflowTiming';
import { workflowNeedsTick } from './workflowStability';

export function useWorkflowClock(task: Task | null, stages: Stage[]) {
  const [records, setRecords] = useState<TimingRecord[]>([]);
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState('');
  useEffect(() => { setRecords([]); setError(''); }, [task?.id]);
  const signature = stages.map(stage => `${stage.id}:${stage.status}`).join('|');
  const ticking = workflowNeedsTick(task?.status);
  useEffect(() => {
    if (!task?.id) return;
    let active = true, pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const { data, error } = await supabase.from('artifacts').select('type,stage_kind,created_at,meta').eq('task_id', task!.id).in('type', ['stage_timing', 'final']).order('created_at');
        if (!active) return;
        if (error) setError('计时记录暂时读取失败');
        else {
          const next = (data || []) as TimingRecord[];
          setRecords(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
          setError('');
        }
      } catch { if (active) setError('计时记录暂时读取失败'); }
      finally { pending = false; }
    }
    void load();
    const poll = ticking ? setInterval(() => void load(), 10_000) : null;
    // Fetch once more after a terminal transition to include its closing clock.
    const settled = !ticking ? setTimeout(() => void load(), 1500) : null;
    return () => { active = false; if (poll) clearInterval(poll); if (settled) clearTimeout(settled); };
  }, [task?.id, signature, ticking]);
  useEffect(() => {
    if (!ticking) return;
    setNow(Date.now());
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [ticking]);
  const stop = task && ['failed', 'cancelled'].includes(task.status) ? Date.parse(task.updated_at) : now;
  return { records, now, error, summary: task ? workflowTiming(task.created_at, task.status, records, stages, stop) : null };
}
export type WorkflowClock = ReturnType<typeof useWorkflowClock>;
