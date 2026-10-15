"""Explicit real production acceptance after script confirmation.

Uses one disposable account/task and the existing engineering narration.
Reuses existing images; never calls an image provider. State stays in ignored output.
"""
import argparse
import json
import secrets
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values
from supabase import create_client


def cleanup_task_objects(admin, task_id):
    # Old review generations are not artifacts yet; enumerate the entire
    # disposable UUID namespace so calibration leaves no orphan audio behind.
    assert str(uuid.UUID(task_id)) == task_id
    prefix=task_id+'/'
    pending=[task_id]
    paths=[]
    while pending:
        directory=pending.pop()
        rows=admin.storage.from_('artifacts').list(directory,{'limit':1000})
        assert len(rows)<1000, 'Unexpectedly large disposable test namespace'
        for row in rows:
            path=directory+'/'+row['name']
            assert path.startswith(prefix) and '..' not in path.split('/')
            if row.get('id'):
                paths.append(path)
            else:
                pending.append(path)
    if paths:
        admin.storage.from_('artifacts').remove(paths)
    assert not admin.storage.from_('artifacts').list(task_id,{'limit':1})
    return len(paths)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--reuse-existing-images', action='store_true', required=True)
    parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = root / 'worker/output/external-live-acceptance'
    output.mkdir(exist_ok=True)
    state_file = output / 'private-state.json'
    env = dotenv_values(root / 'worker/.env')
    public = dotenv_values(root / 'web/.env.local')
    base = env['SUPABASE_URL'].rstrip('/')
    admin = create_client(base, env['SUPABASE_SERVICE_KEY'])
    anon = public['NEXT_PUBLIC_SUPABASE_ANON_KEY']
    web = 'https://content-ecosystem.socra.cn'
    http = httpx.Client(timeout=120)
    source = root / 'worker/output/indextts25-history-reference-1013/20261015-0920-slow108-aligned/slow108-natural-pauses-v2.wav'
    script = json.loads((root / 'worker/output/external-narration-pilot/review.json').read_text(encoding='utf-8'))['source_text']
    def save():
        state_file.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding='utf-8'))
        if state.get('cleaned'):
            raise RuntimeError('This acceptance run is already complete; use its saved report.')
    else:
        state = {'email':'narration-e2e-' + uuid.uuid4().hex + '@example.invalid',
                 'password':secrets.token_urlsafe(32), 'checks':[], 'scope':'engineering_sample_not_user_final'}
        save()
        user = admin.auth.admin.create_user({'email':state['email'],'password':state['password'],'email_confirm':True}).user
        state['user_id'] = user.id
        save()
    session = create_client(base,anon).auth.sign_in_with_password({'email':state['email'],'password':state['password']}).session
    token = session.access_token
    headers = {'Authorization':'Bearer '+token}
    def api(method,path,body=None):
        response = http.request(method, web+path,headers=headers,json=body)
        assert response.is_success, (method,path,response.status_code,response.text[:400])
        return response.json()
    def record(name):
        if name not in state['checks']:
            state['checks'].append(name)
        save()
        print('PASS', name, flush=True)
    if not state.get('task_id'):
        task = admin.table('tasks').insert({'owner':state['user_id'],'title':'External narration engineering E2E (disposable)',
            'status':'release_test','tts_source':'external','content_category':'social_science','narration_mode':'single'}).execute().data[0]
        state['task_id'] = task['id']; save()
        for stage in admin.table('stages').select('*').eq('task_id',task['id']).execute().data:
            if stage['kind'] in ('ingest','transcribe','clean','rewrite','book'):
                params = {'final_text':script,'cover_title':'把心放慢','cover_subtitle':'道德经工程联调','cover_confirmed':True} if stage['kind']=='rewrite' else stage['params']
                admin.table('stages').update({'status':'done','params':params}).eq('id',stage['id']).execute()
            if stage['kind']=='image':
                admin.table('stages').update({'params':{**stage['params'],'visual_style':'history_ink_scroll','generation_mode':'prompt','reference_mode':'none'}}).eq('id',stage['id']).execute()
        rewrite = {'final_text':script,'cover_title':'把心放慢','cover_subtitle':'道德经工程联调','cover_confirmed':True}
        path=task['id']+'/rewrite.json'
        admin.storage.from_('artifacts').upload(path,json.dumps(rewrite,ensure_ascii=False).encode(),{'content-type':'application/json','upsert':'true'})
        admin.table('artifacts').insert({'task_id':task['id'],'stage_kind':'rewrite','type':'rewrite','storage_path':path}).execute()
    task_id = state['task_id']
    def stage(kind):
        return admin.table('stages').select('*').eq('task_id',task_id).eq('kind',kind).single().execute().data
    tts_id = stage('tts')['id']
    def action(name,data):
        return api('PATCH','/api/narration',{'stageId':tts_id,'action':name,'data':data})
    if not state.get('version_id'):
        ready = api('POST','/api/narration',{'stageId':tts_id,'name':'engineering-natural-pauses.wav','size':source.stat().st_size})
        state['version_id']=ready['id']; state['original_path']=ready['path']; save()
        create_client(base,anon).storage.from_('artifacts').upload_to_signed_url(ready['path'],ready['token'],source.read_bytes(),{'content-type':'audio/wav'})
        action('submit',{'id':ready['id']})
        record('production frontend signed upload and submit')
    import config
    import main as worker
    config.WORKER_TASK_ID=task_id
    def tick(kind):
        current=stage(kind)
        if current['status'] in ('failed','pending'):
            if current['status']=='failed':
                admin.table('stages').update({'status':'pending','error':None}).eq('id',current['id']).execute()
            admin.table('tasks').update({'status':'processing'}).eq('id',task_id).execute()
            config.WORKER_STAGE_KINDS=(kind,)
            assert worker.tick(), 'Expected scoped claim for '+kind
        result=stage(kind)
        assert result['status'] in ('done','needs_review'), (kind,result['status'],result.get('error'))
        return result
    tick('tts')
    payload=api('GET','/api/narration?stageId='+tts_id)
    review=payload['current']['review']
    record('real Worker ASR and versioned subtitle upload')
    if not review['alignment_ready']:
        cues=review['segments']
        for index,cue in enumerate(cues):
            if not cue.get('needs_timing_review'):
                continue
            if index==0 and cue['text']=='您有没有发现':
                cue['start']=review['words'][0]['start']
            elif cue['text']=='又催他尽快给个准话' and index+1<len(cues):
                cue['end']=cues[index+1]['start']
            else:
                raise RuntimeError('Unexpected unresolved cue; inspect audio before continuing: '+cue['text'])
        action('realign',{'id':state['version_id'],'text':script,'cues':cues})
        tick('tts')
        payload=api('GET','/api/narration?stageId='+tts_id)
        assert payload['current']['review']['alignment_ready']
        record('explicit cue calibration and cached recognition reuse')
    if payload['current']['state']!='approved':
        action('approve',{'id':state['version_id'],'subtitle_path':payload['current']['subtitle_path']})
    record('production frontend approval')
    if stage('image')['status']!='done':
        # Reuse existing project images under separate test paths. No paid call.
        from stages.image import _history_storyboard
        shots,_analysis=_history_storyboard(script)
        existing=sorted((root/'web/public/history-style-previews').glob('*.png'))
        assert existing, 'No existing project images are available for reuse'
        entries=[]
        for index,shot in enumerate(shots):
            path=task_id+f'/reused-visuals/img_{index:03d}.png'
            raw=existing[index%len(existing)].read_bytes()
            admin.storage.from_('artifacts').upload(path,raw,{'content-type':'image/png','upsert':'true'})
            admin.table('artifacts').insert({'task_id':task_id,'stage_kind':'image','type':'image','storage_path':path,
                'meta':{'source':'engineering_reuse_existing_image','index':index}}).execute()
            entries.append({**shot,'path':path,'sentence':shot['text']})
        index_path=task_id+'/images_index.json'
        admin.storage.from_('artifacts').upload(index_path,json.dumps(entries,ensure_ascii=False).encode(),{'content-type':'application/json','upsert':'true'})
        admin.table('artifacts').insert({'task_id':task_id,'stage_kind':'image','type':'image_index','storage_path':index_path}).execute()
        admin.table('stages').update({'status':'done','output_ref':index_path}).eq('id',stage('image')['id']).execute()
    record('existing images reused; no image generation request')
    render=tick('render')
    assert render['output_ref'], render
    (output/'final.mp4').write_bytes(admin.storage.from_('artifacts').download(render['output_ref']))
    quality=json.loads(admin.storage.from_('artifacts').download(task_id+'/quality_report.json'))
    (output/'quality_report.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
    assert quality['status']!='failed', quality['summary']
    record('real render and technical quality report')
    report={'scope':state['scope'],'task_id':task_id,'checks':state['checks'],
            'quality':quality,'production_web':web,'final_file':str(output/'final.mp4')}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    paths={state['original_path']}
    for row in admin.table('external_narrations').select('audio_path,subtitle_path').eq('task_id',task_id).execute().data:
        paths.update(p for p in row.values() if p)
    paths.update(row['storage_path'] for row in admin.table('artifacts').select('storage_path').eq('task_id',task_id).execute().data)
    assert all(path.startswith(task_id+'/') for path in paths)
    cleanup_task_objects(admin,task_id)
    admin.auth.admin.delete_user(state['user_id'])
    state={'scope':state['scope'],'task_id':task_id,'checks':state['checks'],'cleaned':True}
    save()
    print('SUCCESS: engineering E2E complete; disposable cloud data cleaned; local video retained.',flush=True)


if __name__=='__main__':
    main()
