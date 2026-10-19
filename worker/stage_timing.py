"""Persist per-attempt clocks using existing owner-protected artifacts."""
from datetime import datetime, timezone
import time
import uuid
import db


def resource_snapshot():
    """Optional point samples; these are not historical peak measurements."""
    try:
        import psutil
        return {'available_memory_mb': round(psutil.virtual_memory().available / 1024**2),
                'worker_memory_mb': round(psutil.Process().memory_info().rss / 1024**2),
                'cpu_percent_sample': psutil.cpu_percent(interval=0.1)}
    except Exception:
        return None


class StageTiming:
    def __init__(self, stage: dict):
        self.stage = stage
        self.id = str(uuid.uuid4())
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.clock = time.monotonic()
        self.meta = {'stage_id': stage['id'], 'started_at': self.started_at, 'state': 'running'}
        resources = resource_snapshot()
        if resources:
            self.meta['resources_at_start'] = resources
        self.saved = False

    def start(self):
        try:
            db.retry(lambda: db.get_client().table('artifacts').insert({
                'id': self.id, 'task_id': self.stage['task_id'], 'stage_kind': self.stage['kind'],
                'type': 'stage_timing', 'storage_path': f"{self.stage['task_id']}/timings/{self.id}",
                'meta': self.meta,
            }).execute(), attempts=2)
            self.saved = True
        except Exception as exc:
            print(f'  [timing] start unavailable: {type(exc).__name__}', flush=True)

    def finish(self):
        if not self.saved:
            return
        meta = {**self.meta, 'ended_at': datetime.now(timezone.utc).isoformat(),
                'processing_seconds': round(time.monotonic() - self.clock, 3), 'state': 'finished'}
        resources = resource_snapshot()
        if resources:
            meta['resources_at_end'] = resources
        try:
            db.retry(lambda: db.get_client().table('artifacts').update({'meta': meta}).eq('id', self.id).execute(), attempts=2)
        except Exception as exc:
            print(f'  [timing] finish unavailable: {type(exc).__name__}', flush=True)


def close_interrupted(stage: dict):
    """End abandoned clocks at the last heartbeat, excluding downtime."""
    rows = db.get_client().table('artifacts').select('id,meta').eq('task_id', stage['task_id']).eq('type', 'stage_timing').execute().data or []
    for row in rows:
        meta = row.get('meta') or {}
        if meta.get('stage_id') == stage['id'] and meta.get('state') == 'running':
            meta = {**meta, 'state': 'interrupted', 'ended_at': stage['updated_at']}
            db.get_client().table('artifacts').update({'meta': meta}).eq('id', row['id']).execute()
