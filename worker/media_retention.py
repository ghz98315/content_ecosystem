"""Expire source grids after 24h, images after 48h, and final videos after 7d.

Keep transcripts, rewrites, book data and publication metrics for history.
Use the Storage API so physical objects are removed as well as artifact rows.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import db

GRID_TYPES = ('image_grid',)
IMAGE_TYPES = ('image', 'image_replacement', 'cover_image')
VIDEO_TYPES = ('final',)
TERMINAL = {'done', 'failed', 'cancelled'}
UUID = re.compile(r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$', re.I)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def cleanup_expired_media(*, limit: int = 100, dry_run: bool = False) -> dict:
    sb = db.get_client()
    now = datetime.now(timezone.utc)
    cutoffs = {
        **{kind: (now - timedelta(hours=24)).isoformat() for kind in GRID_TYPES},
        **{kind: (now - timedelta(hours=48)).isoformat() for kind in IMAGE_TYPES},
        **{kind: (now - timedelta(days=7)).isoformat() for kind in VIDEO_TYPES},
    }
    rows = []
    for kinds in (GRID_TYPES, IMAGE_TYPES, VIDEO_TYPES):
        cutoff = cutoffs[kinds[0]]
        rows.extend(sb.table('artifacts').select('id,task_id,type,storage_path,created_at')
                    .in_('type', list(kinds)).lt('created_at', cutoff)
                    .order('created_at').limit(limit * 3).execute().data or [])
    task_ids = list({row['task_id'] for row in rows})
    statuses = {}
    for index in range(0, len(task_ids), 100):
        tasks = sb.table('tasks').select('id,status').in_('id', task_ids[index:index + 100]).execute().data or []
        statuses.update({task['id']: task['status'] for task in tasks})
    image_done = set()
    for index in range(0, len(task_ids), 100):
        stages = (sb.table('stages').select('task_id').in_('task_id', task_ids[index:index + 100])
                  .eq('kind', 'image').eq('status', 'done').execute().data or [])
        image_done.update(stage['task_id'] for stage in stages)

    report = {'scanned': len(rows), 'eligible': 0, 'removed': 0, 'removed_bytes': 0,
              'missing': 0, 'refreshed': 0, 'skipped': 0, 'failures': []}
    seen = set()
    for row in rows:
        if report['eligible'] >= limit:
            break
        task_id, kind, path = row['task_id'], row['type'], row['storage_path']
        if path in seen:
            continue
        seen.add(path)
        safe_stage = statuses.get(task_id) in TERMINAL or (kind == 'image_grid' and task_id in image_done)
        if (not safe_stage or not UUID.fullmatch(task_id)
                or not path.startswith(task_id + '/') or '\\' in path
                or any(part in ('', '.', '..') for part in path.split('/'))):
            report['skipped'] += 1
            continue
        report['eligible'] += 1
        cutoff = cutoffs[kind]
        try:
            latest = (sb.table('artifacts').select('created_at').eq('storage_path', path)
                      .order('created_at', desc=True).limit(1).execute().data or [])
            if not latest or _timestamp(latest[0]['created_at']) >= _timestamp(cutoff):
                report['skipped'] += 1
                continue
            try:
                info = sb.storage.from_('artifacts').info(path)
            except Exception as exc:
                if 'not found' not in str(exc).lower() and '404' not in str(exc):
                    raise
                report['missing'] += 1
                if not dry_run:
                    sb.table('artifacts').delete().eq('storage_path', path).eq('type', kind).lt('created_at', cutoff).execute()
                continue
            modified = info.get('last_modified')
            if not modified:
                raise RuntimeError('Storage object timestamp unavailable')
            if _timestamp(modified) >= _timestamp(cutoff):
                report['refreshed'] += 1
                if not dry_run:
                    sb.table('artifacts').update({'created_at': modified}).eq('storage_path', path).eq('type', kind).lt('created_at', cutoff).execute()
                continue
            if not dry_run:
                sb.storage.from_('artifacts').remove([path])
                sb.table('artifacts').delete().eq('storage_path', path).eq('type', kind).lt('created_at', cutoff).execute()
            report['removed'] += 1
            report['removed_bytes'] += int(info.get('size') or (info.get('metadata') or {}).get('size') or 0)
        except Exception as exc:
            report['failures'].append({'path': path, 'error': str(exc)[:180]})
    return report


def cleanup_expired_external_audio(*, limit: int = 50, dry_run: bool = False) -> dict:
    """Remove uploaded narration originals after 48h once their task is terminal.

    The transcript and alignment metadata stay in Postgres. Audio-dependent
    rerenders require a new upload after this point.
    """
    sb = db.get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    rows = (sb.table('external_narrations')
            .select('id,task_id,original_path,audio_path,review,created_at')
            .lt('created_at', cutoff.isoformat()).order('created_at')
            .limit(1000).execute().data or [])
    pending = [row for row in rows if not (row.get('review') or {}).get('audio_expired_at')][:limit]
    task_ids = list({row['task_id'] for row in pending})
    statuses = {}
    for index in range(0, len(task_ids), 100):
        tasks = (sb.table('tasks').select('id,status')
                 .in_('id', task_ids[index:index + 100]).execute().data or [])
        statuses.update({task['id']: task['status'] for task in tasks})
    report = {'scanned': len(pending), 'expired_versions': 0, 'removed': 0,
              'removed_bytes': 0, 'skipped': 0, 'failures': []}
    for row in pending:
        task_id = row['task_id']
        paths = {path for path in (row['original_path'], row.get('audio_path')) if path}
        if (statuses.get(task_id) not in TERMINAL or not UUID.fullmatch(task_id)
                or any(not path.startswith(task_id + '/external/') or '\\' in path
                       or any(part in ('', '.', '..') for part in path.split('/')) for path in paths)):
            report['skipped'] += 1
            continue
        try:
            eligible = []
            for path in paths:
                try:
                    info = sb.storage.from_('artifacts').info(path)
                except Exception as exc:
                    if 'not found' in str(exc).lower() or '404' in str(exc):
                        continue
                    raise
                modified = info.get('last_modified')
                if not modified or _timestamp(modified) >= cutoff:
                    raise RuntimeError('Audio object was modified within 48 hours')
                eligible.append((path, int(info.get('size') or (info.get('metadata') or {}).get('size') or 0)))
            if not dry_run:
                for path, _ in eligible:
                    sb.storage.from_('artifacts').remove([path])
                    sb.table('artifacts').delete().eq('task_id', task_id).eq('type', 'audio').eq('storage_path', path).execute()
                review = {**(row.get('review') or {}), 'audio_expired_at': datetime.now(timezone.utc).isoformat()}
                sb.table('external_narrations').update({'audio_path': None, 'review': review}).eq('id', row['id']).execute()
            report['expired_versions'] += 1
            report['removed'] += len(eligible)
            report['removed_bytes'] += sum(size for _, size in eligible)
        except Exception as exc:
            report['failures'].append({'id': row['id'], 'error': str(exc)[:180]})
    return report
