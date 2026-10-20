"""Remove obsolete task uploads that have no database or stage references."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import db
from music_presets import PRESET_PATHS


def _all_rows(sb, table: str, columns: str) -> list[dict]:
    rows = []
    for offset in range(0, 100000, 1000):
        batch = sb.table(table).select(columns).range(offset, offset + 999).execute().data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
    raise RuntimeError(f'{table} row cap exceeded; orphan cleanup aborted')


def cleanup_orphan_uploads(*, limit: int = 100, dry_run: bool = False) -> dict:
    sb = db.get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    protected = {row['storage_path'] for row in _all_rows(sb, 'artifacts', 'storage_path')}
    for row in _all_rows(sb, 'external_narrations', 'original_path,audio_path,subtitle_path'):
        protected.update(path for path in row.values() if path)
    tasks = _all_rows(sb, 'tasks', 'id,status,bgm_path')
    statuses = {row['id']: row['status'] for row in tasks}
    protected.update(row['bgm_path'] for row in tasks if row.get('bgm_path'))
    protected.update(row['storage_path'] for row in _all_rows(sb, 'visual_reference_assets', 'storage_path'))
    protected.update(row['output_ref'] for row in _all_rows(sb, 'stages', 'output_ref') if row.get('output_ref'))
    protected.update(PRESET_PATHS)
    protected.add('style-references/guoxue-gongbi-reference.png')

    candidates = []
    folders = ['']
    while folders:
        folder = folders.pop()
        for offset in range(0, 10000, 100):
            batch = sb.storage.from_('artifacts').list(folder, {'limit': 100, 'offset': offset}) or []
            for item in batch:
                name = item['name']
                if name in ('.', '..') or '/' in name or '\\' in name:
                    raise RuntimeError('Unexpected Storage entry; orphan cleanup aborted')
                path = f'{folder}/{name}' if folder else name
                if not item.get('id'):
                    folders.append(path)
                    continue
                parts = path.split('/')
                if (path in protected or len(parts) < 3
                        or statuses.get(parts[0]) not in ('done', 'failed', 'cancelled')
                        or parts[1] not in ('external', 'background-music')):
                    continue
                modified = item.get('updated_at') or item.get('created_at')
                if not modified or datetime.fromisoformat(modified.replace('Z', '+00:00')) >= cutoff:
                    continue
                candidates.append((path, int((item.get('metadata') or {}).get('size') or 0)))
            if len(batch) < 100:
                break
        if len(candidates) >= limit:
            break

    removed = []
    failures = []
    for path, size in candidates[:limit]:
        try:
            if not dry_run:
                sb.storage.from_('artifacts').remove([path])
            removed.append((path, size))
        except Exception as exc:
            failures.append({'path': path, 'error': str(exc)[:180]})
    return {'candidates': len(candidates), 'removed': len(removed),
            'removed_bytes': sum(size for _, size in removed), 'failures': failures}
