"use client";
import { Stage, Task, STAGES } from '@/lib/types';
import { clockLabel, elapsedLabel } from '@/lib/workflowTiming';
import { WorkflowClock } from '@/lib/useWorkflowClock';
import { Icon } from './Icon';

export function WorkflowTiming({ task, stages, clock }: { task: Task; stages: Stage[]; clock: WorkflowClock }) {
  const timing = clock.summary;
  if (!timing) return null;
  const running = stages.filter(stage => stage.status === 'processing').length;
  return <section className="workflow-telemetry" aria-label="全流程耗时">
    <div className="timing-primary"><span><Icon name="clock" size={14}/>{timing.finished ? '创建至成片' : '总历时'}</span><strong>{clockLabel(timing.total)}</strong><small>{running ? `${running} 个节点运行中` : task.status === 'needs_review' ? '等待人工确认' : '按实际执行记录统计'}</small></div>
    <div className="timing-secondary"><span>自动处理</span><strong>{clockLabel(timing.processing)}</strong><small>并行时间已去重</small></div>
    <div className="timing-secondary"><span>等待与排队</span><strong>{timing.waiting == null ? '—' : clockLabel(timing.waiting)}</strong><small>{timing.waiting == null ? '历史记录不完整' : '含人工确认时间'}</small></div>
    <details className="timing-records"><summary>执行记录<Icon name="chevron" size={13}/></summary><div className="timing-record-list">{timing.byStage.map(item => <p key={item.kind}><span>{STAGES.find(stage => stage.kind === item.kind)?.label}</span><b>{item.attempts ? elapsedLabel(item.milliseconds) : item.skipped ? '已复用' : '暂无记录'}</b><small>{item.attempts ? `${item.attempts}次执行` : ''}</small></p>)}{!timing.complete && <small>部分历史节点缺少计时记录，等待时长不作推算。</small>}</div></details>
    {clock.error && <span className="timing-error" role="status">{clock.error}</span>}
  </section>;
}
