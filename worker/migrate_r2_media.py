"""Inventory registered media, then copy or verify and remove its Supabase copy."""
import argparse
import hashlib
import json
import mimetypes
import tempfile
from pathlib import Path

from storage3.exceptions import StorageApiError

import db
import r2_media
import storage
from media_retention import GRID_TYPES, IMAGE_TYPES, VIDEO_TYPES, TERMINAL


def checksum(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def migrate(mode: str, limit: int) -> dict:
    if mode != 'inventory' and not r2_media.enabled():
        raise ValueError('请配置 R2_BUCKET 和 R2 S3 凭据')
    sb = db.get_client()
    source = sb.storage.from_(storage.BUCKET)
    kinds = list(GRID_TYPES + IMAGE_TYPES + VIDEO_TYPES)
    report = {'scanned': 0, 'bytes': 0, 'missing_source': 0, 'skipped_active': 0,
              'copied': 0, 'verified': 0, 'removed': 0, 'failures': []}
    seen = set()
    offset = 0
    while report['scanned'] < limit:
        rows = (sb.table('artifacts').select('task_id,storage_path').in_('type', kinds)
                .order('id').range(offset, offset + 99).execute().data or [])
        if not rows:
            break
        offset += len(rows)
        for row in rows:
            path, task = row['storage_path'], row['task_id']
            if path in seen or not path.startswith(task + '/') or not r2_media.media_path(path):
                continue
            seen.add(path)
            try:
                migrate_one(sb, source, path, task, mode, report)
            except Exception as exc:
                report['failures'].append({'path': path, 'error': type(exc).__name__ + ': ' + str(exc).split('?')[0][:100]})
            if report['scanned'] >= limit:
                break
    return report


def migrate_one(sb, source, path: str, task: str, mode: str, report: dict) -> None:
    report['scanned'] += 1
    try:
        original = source.info(path)
    except StorageApiError as exc:
        if str(exc.status) != '404':
            raise
        report['missing_source'] += 1
        return
    size = int(original.get('size') or (original.get('metadata') or {}).get('size') or 0)
    report['bytes'] += size
    if mode == 'inventory':
        return
    def idle() -> bool:
        row = sb.table('tasks').select('status').eq('id', task).maybe_single().execute().data
        return bool(row and row['status'] in TERMINAL)

    if not idle():
        report['skipped_active'] += 1
        return
    with tempfile.TemporaryDirectory() as folder:
        a, b = Path(folder) / 'source', Path(folder) / 'target'
        a.write_bytes(source.download(path))
        if size <= 0 or a.stat().st_size != size:
            raise ValueError('Supabase 文件大小不一致')
        if not r2_media.info(path):
            if mode == 'remove-verified':
                raise ValueError('R2 副本不存在')
            modified = original.get('last_modified')
            if not modified:
                raise ValueError('旧对象时间不可用')
            r2_media.upload_file(path, str(a), mimetypes.guess_type(path)[0] or 'application/octet-stream',
                                 {'source-modified-at': modified})
            report['copied'] += 1
        r2_media.download_file(path, str(b))
        if a.stat().st_size != b.stat().st_size or checksum(a) != checksum(b):
            raise ValueError('R2 副本与原件不一致')
        report['verified'] += 1
        if mode == 'remove-verified':
            if not idle() or source.info(path) != original:
                raise ValueError('任务状态或源文件已变化，保留 Supabase 文件')
            source.remove([path])
            report['removed'] += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inventory', 'copy', 'remove-verified'), nargs='?', default='inventory')
    parser.add_argument('--limit', type=int, default=200)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    output = migrate(args.mode, args.limit)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(bool(output['failures']))
