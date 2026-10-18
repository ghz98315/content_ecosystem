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
    byStage: stages.map(stage => ({ kind: stage.kind, skipped: Boolean(stage.params.skipped), milliseconds: unionMilliseconds(ranges(stage.kind)), attempts: attempts.filter(row => row.meta.stage_id === stage.id).length })) };
}
export function elapsedLabel(ms: number) {
  const seconds = Math.max(0, Math.floor(ms/1000));
  return `${Math.floor(seconds/3600)}小时${Math.floor(seconds%3600/60)}分${seconds%60}秒`;
}

export function clockLabel(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes >= 60 ? `${Math.floor(minutes / 60)}:` : ''}${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

export function nodeClock(stage: { id: string; status: string; updated_at: string; params: Record<string, unknown> } | undefined, records: TimingRecord[], now: number) {
  if (!stage) return { label: '等待上游', running: false, attempts: 0 };
  const attempts = records.filter(row => row.type === 'stage_timing' && row.meta.stage_id === stage.id).sort((a, b) => String(a.meta.started_at).localeCompare(String(b.meta.started_at)));
  const last = attempts[attempts.length - 1];
  if (stage.params.skipped && stage.status === 'done') return { label: '已复用', running: false, attempts: attempts.length };
  if (stage.status === 'processing') {
    const start = Date.parse(last?.meta.started_at || '');
    // A finished clock belongs to a previous attempt while the next start record is in flight.
    return { label: last?.meta.state === 'running' && Number.isFinite(start) ? clockLabel(now - start) : '计时同步中', running: true, attempts: attempts.length };
  }
  const duration = last ? Date.parse(last.meta.ended_at || stage.updated_at) - Date.parse(last.meta.started_at) : NaN;
  const label = stage.status === 'needs_review' ? `待确认 ${clockLabel(now - Date.parse(stage.updated_at))}`
    : stage.status === 'pending' ? '等待上游 / 排队'
    : stage.status === 'cancelled' ? '已取消'
    : Number.isFinite(duration) ? clockLabel(duration) : '暂无计时';
  return { label, running: false, attempts: attempts.length };
}
