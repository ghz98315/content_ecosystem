import { StageKind } from './types';
type SelectionStage = { kind: StageKind; status: string; seq: number };

export function resolveStageSelection(stages: SelectionStage[], selected: StageKind, manual: boolean): StageKind {
  if (manual && stages.some(stage => stage.kind === selected)) return selected;
  const current = stages.find(stage => stage.kind === selected);
  if (selected !== 'ingest' && current && ['pending', 'processing', 'needs_review', 'failed'].includes(current.status)) return selected;
  const active = stages.find(stage => ['processing', 'needs_review', 'failed'].includes(stage.status));
  if (active) return active.kind;
  const queued = stages.filter(stage => stage.status === 'pending').sort((a, b) => a.seq - b.seq);
  if (queued.length) return queued[0].kind;
  const completed = stages.filter(stage => stage.status === 'done').sort((a, b) => b.seq - a.seq);
  return completed[0]?.kind || selected;
}

export function workflowNeedsTick(status?: string) {
  return Boolean(status && !['done', 'failed', 'cancelled'].includes(status));
}
