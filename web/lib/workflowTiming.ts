export type TimingRecord = { type: string; stage_kind: string; created_at: string; meta: Record<string, any> };
export function unionMilliseconds(ranges: Array<[number, number]>) {
  let total = 0, start = 0, end = 0;
  for (const [left, right] of ranges.filter(([a,b]) => Number.isFinite(a) && Number.isFinite(b) && b >= a).sort((a,b) => a[0]-b[0])) {
    if (left > end) { total += end-start; start = left; end = right; }
    else end = Math.max(end,right);
  }
  return total + end-start;
}
export function workflowTiming(createdAt: string, status: string, records: TimingRecord[], stages: Array<{ id: string; kind: string; status: string; updated_at: string; params: Record<string, any> }>, now = Date.now()) {
  const render = stages.find(stage => stage.kind === 'render');
  const finals = records.filter(row => row.type === 'final').map(row => Date.parse(row.created_at)).filter(Number.isFinite);
  const end = finals.length && ['done','needs_review'].includes(render?.status || '') ? Math.max(...finals) : now;
  const beginning = Date.parse(createdAt);
  const attempts = records.filter(row => row.type === 'stage_timing');
  const incomplete = attempts.some(row => row.meta.state === 'running' && stages.find(stage => stage.id === row.meta.stage_id)?.status !== 'processing');
  const required = stages.filter(stage => stage.status === 'done' && !stage.params.skipped);
  const covered = required.every(stage => attempts.some(row => row.meta.stage_id === stage.id));
  const ranges = (kind?: string): Array<[number,number]> => attempts.filter(row => !kind || row.stage_kind === kind).map(row => {
    const stage = stages.find(stage => stage.id === row.meta.stage_id);
    const finish = row.meta.ended_at ? Date.parse(row.meta.ended_at) : stage?.status === 'processing' ? end : Date.parse(stage?.updated_at || '');
    return [Math.max(beginning, Date.parse(row.meta.started_at)), Math.min(end, finish)];
  });
  const total = Math.max(0,end-beginning);
  const processing = Math.min(total,unionMilliseconds(ranges()));
  return { total, processing, waiting: covered && attempts.length > 0 && !incomplete ? Math.max(0,total-processing) : null,
    complete: covered && !incomplete && attempts.length > 0, finished: end !== now,
    byStage: stages.map(stage => ({ kind: stage.kind, milliseconds: unionMilliseconds(ranges(stage.kind)), attempts: attempts.filter(row => row.meta.stage_id === stage.id).length })) };
}
export function elapsedLabel(ms: number) {
  const seconds = Math.max(0, Math.floor(ms/1000));
  return `${Math.floor(seconds/3600)}小时${Math.floor(seconds%3600/60)}分${seconds%60}秒`;
}
