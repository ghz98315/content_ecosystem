"""Explicit production contract check using disposable accounts/task/audio only.

Run with --execute. This checks real Auth/RLS/Storage/RPC, not real ASR.
"""
import argparse
import io
import json
import secrets
import uuid
import wave
from pathlib import Path

import httpx
from dotenv import dotenv_values
from supabase import create_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--web-origin', help='Also verify the deployed authenticated narration API')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    env = dotenv_values(root / 'worker/.env')
    public = dotenv_values(root / 'web/.env.local')
    base, key = env['SUPABASE_URL'].rstrip('/'), env['SUPABASE_SERVICE_KEY']
    anon = public['NEXT_PUBLIC_SUPABASE_ANON_KEY']
    admin = create_client(base, key)
    accounts, objects, checks = [], [], []
    task_id = None
    client = httpx.Client(base_url=base, timeout=40)
    def request(method, path, body=None, token=key, expected=200):
        response = client.request(method, path, json=body, headers={
            'apikey': key if token == key else anon,
            'Authorization': 'Bearer ' + token,
            'Prefer': 'return=representation',
        })
        if expected == 'error':
            assert response.status_code >= 400, (path, response.status_code)
            return response.json()
        assert response.status_code == expected, (path, response.status_code, response.text[:300])
        return response.json() if response.content else None
    def passed(name):
        checks.append(name)
        print('PASS', name, flush=True)
    try:
        users = []
        for _ in range(2):
            email = 'release-narration-' + uuid.uuid4().hex + '@example.invalid'
            password = secrets.token_urlsafe(32)
            account = request('POST', '/auth/v1/admin/users', {
                'email': email, 'password': password, 'email_confirm': True,
            })
            accounts.append(account['id'])
            session = request('POST', '/auth/v1/token?grant_type=password', {
                'email': email, 'password': password,
            }, token=anon)
            users.append(session['access_token'])
        owner, other = users
        task = request('POST', '/rest/v1/tasks', {
            'owner': accounts[0], 'title': 'External narration release contract test (disposable)',
            'status': 'release_test', 'tts_source': 'external',
        }, expected=201)[0]
        task_id = task['id']
        stages = request('GET', '/rest/v1/stages?task_id=eq.' + task_id)
        tts = next(s for s in stages if s['kind'] == 'tts')
        image = next(s for s in stages if s['kind'] == 'image')
        assert tts['params']['audio_source'] == 'external'
        passed('task source is copied to TTS stage')
        for stage in stages:
            if stage['kind'] in ('ingest', 'transcribe', 'clean', 'rewrite', 'book'):
                request('PATCH', '/rest/v1/stages?id=eq.' + stage['id'], {
                    'status': 'done', **({'params': {'final_text': '读经典。'}} if stage['kind'] == 'rewrite' else {}),
                })
        def action(name, data=None, token=owner, expected=200):
            if args.web_origin and token == owner and expected == 200:
                response = client.request('POST' if name == 'prepare' else 'PATCH', args.web_origin.rstrip('/') + '/api/narration',
                    headers={'Authorization': 'Bearer '+owner}, json=(
                        {'stageId':tts['id'],'name':data['name'],'size':data['size']} if name == 'prepare' else
                        {'stageId':tts['id'],'action':name,'data':data or {}}))
                assert response.is_success, (name,response.status_code,response.text[:300])
                result=response.json()
                if name=='prepare':
                    result['original_path']=result['path']
                return result
            return request('POST', '/rest/v1/rpc/narration_action', {
                'p_stage_id': tts['id'], 'p_action': name, 'p_data': data or {},
            }, token=token, expected=expected)
        action('source', {'source': 'automatic'}, token=other, expected='error')
        passed('another user cannot mutate the task')
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0' * 16000 * 4)
        data = audio.getvalue()
        version = action('prepare', {'name': 'engineering-silence.wav', 'extension': 'wav', 'size': len(data)})
        action('submit', {'id': version['id']}, expected='error')
        passed('missing upload is rejected')
        signed = admin.storage.from_('artifacts').create_signed_upload_url(version['original_path'])
        upload_client = create_client(base, anon)
        upload_client.storage.from_('artifacts').upload_to_signed_url(
            signed['path'], signed['token'], data, {'content-type': 'audio/wav'})
        objects.append(version['original_path'])
        action('submit', {'id': version['id']})
        action('submit', {'id': version['id']})
        passed('real signed Storage upload and idempotent submit')
        foreign = request('GET', '/rest/v1/external_narrations?task_id=eq.' + task_id, token=other)
        assert foreign == []
        passed('version RLS hides data from another user')
        assert request('POST', '/rest/v1/rpc/claim_media_stage', {'p_stage_id': image['id']}) == []
        claim = request('POST', '/rest/v1/rpc/claim_media_stage', {'p_stage_id': tts['id']})[0]
        passed('images are gated until approved audio')
        action('source', {'source': 'automatic'}, expected='error')
        subtitle = version['original_path'].rsplit('/', 1)[0] + '/engineering-subtitles.json'
        admin.storage.from_('artifacts').upload(subtitle, json.dumps({
            'input_format': 'timeline_v3', 'duration': 4, 'text': '读经典。',
            'segments': [{'text': '读经典', 'start': .5, 'end': 2.5, 'char_start': 0, 'char_end': 3}],
        }).encode(), {'content-type': 'application/json'})
        objects.append(subtitle)
        finish = {'p_stage_id': tts['id'], 'p_job': 'stale-job', 'p_state': 'review',
                  'p_review': {'alignment_ready': True, 'duration': 4, 'scope': 'contract_fixture_not_real_asr'},
                  'p_audio': version['original_path'], 'p_subtitle': subtitle}
        assert request('POST', '/rest/v1/rpc/finish_external_narration', finish) is False
        finish['p_job'] = claim['params']['external_job']
        assert request('POST', '/rest/v1/rpc/finish_external_narration', finish) is True
        passed('stale worker result rejected; current job accepted')
        action('approve', {'id': version['id'], 'subtitle_path': 'stale.json'}, expected='error')
        action('approve', {'id': version['id'], 'subtitle_path': subtitle})
        action('approve', {'id': version['id'], 'subtitle_path': subtitle})
        passed('approval requires reviewed version and is idempotent')
        request('POST', '/rest/v1/rpc/regenerate_image_stage', {'p_stage_id': image['id']}, token=owner)
        latest = request('GET', '/rest/v1/stages?id=eq.' + tts['id'])[0]
        assert latest['status'] == 'done' and latest['output_ref'] == version['original_path']
        passed('full image regeneration preserves approved narration')
    finally:
        errors = []
        if objects:
            try:
                admin.storage.from_('artifacts').remove(objects)
            except Exception as exc:
                errors.append(type(exc).__name__ + ': storage cleanup')
        for account in reversed(accounts):
            try:
                request('DELETE', '/auth/v1/admin/users/' + account)
            except Exception as exc:
                errors.append(type(exc).__name__ + ': disposable user cleanup')
        report = {'scope': 'production_contract_check_not_real_asr', 'checks': checks,
                  'test_task_id': task_id, 'cleanup_errors': errors}
        output = root / 'worker/output/external-production-contract.json'
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        client.close()
        assert not errors, errors
    print(f'{len(checks)} production contract checks passed; disposable records cleaned up.')


if __name__ == '__main__':
    main()
