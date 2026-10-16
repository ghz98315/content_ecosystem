"use client";
import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabase';
import { Stage, Task, STAGES } from '@/lib/types';
import { elapsedLabel, TimingRecord, workflowTiming } from '@/lib/workflowTiming';
import { PRODUCTION_TEMPLATES } from '@/lib/productionTemplates';

export function WorkflowTiming({ task, stages }: { task: Task; stages: Stage[] }) {
  const [records,setRecords] = useState<TimingRecord[]>([]);
  const [now,setNow] = useState(Date.now());
  const [error,setError] = useState('');
  useEffect(() => {
    let active = true;
    async function load() {
      const { data,error } = await supabase.from('artifacts').select('type,stage_kind,created_at,meta').eq('task_id',task.id).in('type',['stage_timing','final']).order('created_at');
      if (!active) return;
      setNow(Date.now());
      if (error) setError('计时记录暂时读取失败');
      else { setRecords((data || []) as TimingRecord[]); setError(''); }
    }
    void load();
    const interval=setInterval(() => { void load(); },10000);
    return () => { active=false; clearInterval(interval); };
  },[task.id,task.updated_at]);
  const stopped = ['cancelled','failed'].includes(task.status) ? Date.parse(task.updated_at) : now;
  const timing=workflowTiming(task.created_at,task.status,records,stages,stopped);
  const template=stages.find(stage => stage.kind === 'render')?.params.production_template;
  return <section className="book-info-panel" aria-label="全流程耗时" style={{ margin: '12px 0',padding: 16 }}>
    <strong>全流程耗时</strong> {Boolean(template) && <span> · {PRODUCTION_TEMPLATES.find(item => item.id === template)?.label || '历史模板'}</span>}
    <p>{timing.finished ? '创建至成片' : '自创建累计'}：{elapsedLabel(timing.total)}　已记录处理：{elapsedLabel(timing.processing)}　等待确认与排队：{timing.waiting == null ? '记录不完整，暂不估算' : elapsedLabel(timing.waiting)}</p>
    <details><summary>各节点处理耗时</summary>{timing.byStage.map(stage => <p key={stage.kind}>{STAGES.find(item => item.kind === stage.kind)?.label}：{stage.attempts ? `${elapsedLabel(stage.milliseconds)}（${stage.attempts}次执行）` : '暂无计时记录'}</p>)}</details>
    {!timing.complete && <small>历史任务或中断节点可能缺少计时，已有成片的总耗时仍按实际创建和产出时间计算。</small>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
