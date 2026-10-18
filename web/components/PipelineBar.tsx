"use client";
import { Stage, StageKind, STAGES, STATUS_LABEL } from '@/lib/types';
import { nodeClock } from '@/lib/workflowTiming';
import { WorkflowClock } from '@/lib/useWorkflowClock';
import { Icon } from './Icon';
import { useEffect, useRef } from 'react';

export function PipelineBar({ stages, selected, onSelect, clock }: { stages: Stage[]; selected: StageKind; onSelect: (kind: StageKind) => void; clock: WorkflowClock }) {
  const navigation = useRef<HTMLElement>(null);
  useEffect(() => {
    const container = navigation.current;
    const node = container?.querySelector<HTMLElement>(`[data-kind="${selected}"]`);
    if (container && node && container.scrollWidth > container.clientWidth) {
      const left = container.scrollLeft + node.getBoundingClientRect().left - container.getBoundingClientRect().left - (container.clientWidth - node.offsetWidth) / 2;
      container.scrollTo({ left, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
  }, [selected]);
  const external = stages.find(stage => stage.kind === 'tts')?.params.audio_source === 'external';
  const definitions = external ? [...STAGES.slice(0, 4), STAGES[6], STAGES[4], STAGES[5], STAGES[7]] : STAGES;
  return <nav ref={navigation} className="pipeline-bar studio-pipeline" aria-label="处理流程节点">{definitions.map((def, index) => {
    const stage = stages.find(item => item.kind === def.kind);
    const status = stage?.status || 'pending';
    const timer = nodeClock(stage, clock.records, clock.now);
    return <button key={def.kind} data-kind={def.kind} onClick={() => onSelect(def.kind)} className={`pipeline-node node-${status}${selected === def.kind ? ' is-selected' : ''}`} aria-pressed={selected === def.kind} title={`${def.label} · ${STATUS_LABEL[status]} · ${timer.label}${timer.attempts ? ` · ${timer.attempts}次执行` : ''}`}>
      <span className="node-number">{status === 'done' ? <Icon name="check" size={14}/> : status === 'failed' ? <Icon name="close" size={14}/> : status === 'processing' ? <span className="node-spinner"/> : String(index + 1).padStart(2, '0')}</span>
      <span className="node-copy"><strong>{def.label}</strong><small>{timer.label}</small></span>
      <span className="node-state">{STATUS_LABEL[status]}</span>
    </button>;
  })}</nav>;
}
