"""Copy first-publication images into the repost's own retention scope."""
import hashlib
import json
import re
from difflib import SequenceMatcher

from storage3.exceptions import StorageApiError

import db
import storage
from storyboard import VERSION, effective_count, split_shots


def _resegment(text: str, scene: bool) -> list[dict]:
    count = effective_count if scene else lambda value: sum(not char.isspace() for char in value)
    cursor = 0
    result = []
    for index, sentence in enumerate(split_shots(text)):
        length = count(sentence)
        result.append({'index': index, 'sentence': sentence, 'text': sentence,
                       'char_start': cursor, 'char_end': cursor + length, 'char_count': length,
                       'effective_char_count': effective_count(sentence),
                       'estimated_duration': max(1.0, length / 3.5),
                       'motion': 'zoom_in' if index % 2 == 0 else 'zoom_out'})
        cursor += length
    return result


def _match_images(shots: list[dict], entries: list[dict]) -> list[dict]:
    # Exact and closely matching passages take priority when the script reorders
    # a section. The rest retain their relative order.
    norm = lambda value: ''.join(c for c in str(value) if c.isalnum())
    old = [norm(entry.get('sentence') or entry.get('text') or '') for entry in entries]
    pairs = []
    for shot in shots:
        new = norm(shot['sentence'])
        for index, original in enumerate(old):
            matcher = SequenceMatcher(None, original, new)
            if matcher.quick_ratio() < 0.55:
                continue
            score = matcher.ratio()
            if score >= 0.55:
                pairs.append((score, shot['index'], index))
    assigned = {}
    used = set()
    for _, target, source in sorted(pairs, reverse=True):
        if target not in assigned and source not in used:
            assigned[target] = source
            used.add(source)
    available = [i for i in range(len(entries)) if i not in used] or list(range(len(entries)))
    unmatched = [i for i in range(len(shots)) if i not in assigned]
    for index, target in enumerate(unmatched):
        assigned[target] = available[index * len(available) // len(unmatched)]
    return [entries[assigned[i]] for i in range(len(shots))]


def reuse_first_publication(stage: dict, text: str, context: dict) -> str | None:
    from stages.image import _existing_image_artifacts
    from stages.render import _apply_image_replacements
    from stages.render import _load_json_artifact

    source = str(context.get('source_task_id') or '')
    if context.get('rewrite_mode') != 'repost_dedup' or not source:
        return None
    task_id = stage['task_id']
    params = stage.get('params') or {}
    # Explicit image regeneration must ask the provider for new images.
    if params.get('generation_id'):
        return None
    client = db.get_client()
    tasks = client.table('tasks').select('id,owner').in_('id', [source, task_id]).execute().data or []
    if len(tasks) != 2 or not tasks[0]['owner'] or tasks[0]['owner'] != tasks[1]['owner']:
        raise ValueError('无权复用首发任务图片')
    try:
        raw_entries = _load_json_artifact(source, 'image_index')
        if not isinstance(raw_entries, list) or not raw_entries or not all(isinstance(entry, dict) and entry.get('path') for entry in raw_entries):
            return None
        entries = _apply_image_replacements(source, raw_entries)
    except StorageApiError as exc:
        if str(exc.status) == '404':
            return None
        raise
    if not entries:
        return None
    scene = params.get('production_template') == 'scene-v1'
    expected_ratio = params.get('image_aspect_ratio')
    if expected_ratio and any(e.get('cell_ratio') and e['cell_ratio'] != expected_ratio for e in entries):
        return None
    shots = _resegment(text, scene)
    if not shots:
        return None
    sources = _match_images(shots, entries)
    cover = entries[0].get('cover_path')
    paths = list(dict.fromkeys([entry['path'] for entry in sources] + ([cover] if cover else [])))
    if any(not isinstance(path, str) or not path.startswith(source + '/') or '\\' in path
           or any(part in ('', '.', '..') for part in path.split('/'))
           or not re.search(r'\.(?:png|jpe?g|webp)$', path, re.I) for path in paths):
        return None
    bucket = client.storage.from_('artifacts')
    signature = hashlib.sha256(json.dumps([VERSION, text, paths], ensure_ascii=False).encode()).hexdigest()[:20]
    root = f'{task_id}/repost-images/{signature}'
    destinations = {path: f"{root}/{i:03d}.{path.rsplit('.', 1)[1].lower()}" for i, path in enumerate(paths)}
    # Copy on the server so the first task can expire without breaking the new task.
    existing = _existing_image_artifacts(task_id)
    try:
        for path, target in destinations.items():
            if target in existing:
                try:
                    bucket.info(target)
                    continue
                except StorageApiError as exc:
                    if str(exc.status) != '404':
                        raise
                    existing.pop(target)
            bucket.info(path)
        for path, target in destinations.items():
            if target not in existing:
                try:
                    bucket.copy(path, target)
                except StorageApiError as exc:
                    if str(exc.status) == '409' or exc.code in ('Duplicate', 'ResourceAlreadyExists', 'KeyAlreadyExists'):
                        bucket.info(target)
                    else:
                        raise
                storage.add_artifact(task_id, 'image', 'cover_image' if path == cover else 'image', target,
                                     meta={'reused_from_task': source, 'source_image': path})
    except StorageApiError as exc:
        if str(exc.status) != '404':
            raise
        print('  [repost] 首发图片已缺失，改用正常生图流程', flush=True)
        return None

    index = []
    for shot, original in zip(shots, sources):
        item = {**shot, 'path': destinations[original['path']], 'reused_from_task': source,
                'cell_ratio': original.get('cell_ratio') or expected_ratio}
        if cover:
            item['cover_path'] = destinations[cover]
        index.append(item)
    path = f'{root}/images_index.json'
    storage.upload_bytes(path, json.dumps(index, ensure_ascii=False).encode(), 'application/json')
    storage.add_artifact(task_id, 'image', 'image_index', path,
                         meta={'total': len(index), 'narration_char_count': index[-1]['char_end'],
                               'reused_from_task': source, 'production_template': params.get('production_template')})
    print(f'  [repost] 复用首发图片 {len(index)} 张', flush=True)
    return path
