"""Adapt an already approved script to the existing downstream rewrite contract."""
from __future__ import annotations

import hashlib
import json

import db
import storage


def build_payload(raw_text: str, category: str) -> dict:
    text = str(raw_text or '').strip()
    if not 20 <= len(text) <= 30000:
        raise ValueError('成稿须为 20–30000 字符，请检查新建项目时提交的文案')
    return {
        'candidates': [text], 'candidate_lengths': [len(text)], 'source_length': len(text),
        'source_text': text, 'source_formatted': text, 'complete': True, 'chosen': 0,
        'final_text': text, 'final_length': len(text), 'content_category': category,
        'input_mode': 'ready_script', 'imported_final_script': True,
    }


def materialize(stage: dict) -> str:
    task_id = stage['task_id']
    context = db.get_task_prompt_context(task_id)
    category = str(context.get('content_category') or 'health')
    payload = build_payload((stage.get('params') or {}).get('ready_script_text'), category)
    text = payload['final_text']
    path = f"{task_id}/rewrite/imported-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}.json"
    storage.upload_bytes(path, json.dumps(payload, ensure_ascii=False).encode('utf-8'), 'application/json')
    existing = db.get_client().table('artifacts').select('id').eq('task_id', task_id).eq('type', 'rewrite').eq('storage_path', path).limit(1).execute().data
    if not existing:
        storage.add_artifact(task_id, 'rewrite', 'rewrite', path, meta={
            'source': 'ready_script', 'candidate_count': 1, 'source_length': len(text),
            'content_category': category, 'complete': True,
        })
    for kind in ('transcribe', 'clean', 'rewrite'):
        result = db.get_client().table('stages').select('id,params').eq('task_id', task_id).eq('kind', kind).single().execute().data
        if not result:
            raise ValueError(f'成稿导入缺少 {kind} 节点')
        params = {**(result.get('params') or {}), 'input_mode': 'ready_script'}
        if kind == 'rewrite':
            params.update({'final_text': text, 'chosen_index': 0})
        else:
            params.update({'skipped': True, 'reason': '已直接导入确认成稿'})
        patch = {'status': 'done', 'params': params, 'error': None,
                 'output_ref': path if kind == 'rewrite' else None}
        db.get_client().table('stages').update(patch).eq('id', result['id']).execute()
    return path
