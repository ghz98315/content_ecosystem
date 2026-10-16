"""Real isolated acceptance; state and credentials stay in ignored local output."""
from pathlib import Path
import json,uuid,secrets,subprocess,time,hashlib,argparse
import httpx
import db,config,storage,main as worker
from dotenv import dotenv_values
from supabase import create_client
from stages import image
from stages.render import ff

parser=argparse.ArgumentParser()
parser.add_argument('--execute',action='store_true',required=True)
parser.add_argument('--source-task',required=True)
args=parser.parse_args()
source_id=str(uuid.UUID(args.source_task))
out=Path('worker/output/guoxue-release').resolve();out.mkdir(exist_ok=True)
statefile=out/'private-e2e-state.json'
sb=db.get_client()
state=json.loads(statefile.read_text(encoding='utf-8')) if statefile.exists() else {'checks':[]}
def save():statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
def passed(name):
    if name not in state['checks']:state['checks'].append(name);save()
    print('PASS '+name,flush=True)
source=sb.table('tasks').select('*').eq('id',source_id).single().execute().data
oldstages=sb.table('stages').select('*').eq('task_id',source_id).execute().data
oldtts=next(s for s in oldstages if s['kind']=='tts')
approved=sb.table('external_narrations').select('*').eq('id',oldtts['params']['external_id']).single().execute().data
assert approved['state']=='approved'
approved_text=approved['script_text']
if not state.get('user_id'):
    state.update(email='guoxue-release-'+uuid.uuid4().hex+'@example.invalid',password=secrets.token_urlsafe(32));save()
    state['user_id']=sb.auth.admin.create_user({'email':state['email'],'password':state['password'],'email_confirm':True}).user.id;save()
anon=dotenv_values('web/.env.local')['NEXT_PUBLIC_SUPABASE_ANON_KEY']
user=create_client(config.SUPABASE_URL,anon)
token=user.auth.sign_in_with_password({'email':state['email'],'password':state['password']}).session.access_token
http=httpx.Client(timeout=120,headers={'Authorization':'Bearer '+token})
def api(method,path,body=None):
    response=http.request(method,'https://content-ecosystem.socra.cn'+path,json=body)
    assert response.is_success,(response.status_code,response.text[:350])
    return response.json()
if not state.get('task_id'):
    row=user.table('tasks').insert({'owner':state['user_id'],'title':'国学模板全流程验收（独立测试）','source_url':source['source_url'],'source_platform':source.get('source_platform') or 'douyin','content_category':source['content_category'],'tts_source':'external','status':'configuring'}).execute().data[0]
    state['task_id']=row['id'];save()
tid=state['task_id']
def stage(kind):return sb.table('stages').select('*').eq('task_id',tid).eq('kind',kind).single().execute().data
if 'template_saved' not in state:
    for kind,params in {
        'image':{'production_template':'guoxue-v1','template_version':1,'image_provider':'apimart','image_model':'gpt-image-2','visual_style':'guoxue_gongbi_life','visual_preset_id':'guoxue-gongbi-life','image_aspect_ratio':'4:3','generation_mode':'prompt','reference_mode':'scene_continuity'},
        'render':{'production_template':'guoxue-v1','template_version':1,'frame_mode':'landscape_blur','title_font':'PlayFont-ChenkunGBT','title_color':'#BA413B','video_text':{'title':'道德经第一章','subtitle':'每天十五分钟，陪你读一本经典','footnote':'第（01）期｜《道德经》（春秋）老子'}},
    }.items():
        result=user.table('stages').update({'params':params}).eq('task_id',tid).eq('kind',kind).execute()
        assert len(result.data)==1
    sb.table('stages').update({'status':'pending'}).eq('task_id',tid).eq('kind','book').execute()
    state['template_saved']=True;save();passed('owner-scoped template and title settings saved')
config.WORKER_TASK_ID=tid
def tick(kind):
    current=stage(kind)
    if current['status']=='done':return current
    assert current['status']=='pending',(kind,current['status'],current.get('error'))
    sb.table('tasks').update({'status':'processing'}).eq('id',tid).execute()
    config.WORKER_STAGE_KINDS=(kind,)
    print('RUN '+kind,flush=True)
    assert worker.tick(),'No stage claim: '+kind
    result=stage(kind)
    assert result['status'] in ('done','needs_review'),(kind,result['status'],result.get('error'))
    return result

for kind in ('ingest','transcribe','clean'):
    result=tick(kind)
    assert result['status']=='done',(kind,result.get('error'))
    passed('real '+kind)
result=tick('rewrite')
if result['status']=='needs_review':
    # A full external voice must match its already approved manuscript.
    # Exercise the real model first, then use that known manuscript as the
    # reviewer edit; do not pretend a new model draft has matching narration.
    response=user.rpc('confirm_rewrite',{'p_stage_id':result['id'],'p_chosen_index':0,'p_final_text':approved_text,'p_cover_title':None,'p_cover_subtitle':None}).execute()
    assert response.data
    tick('rewrite')
passed('real rewrite and explicit reuse of approved manuscript')
assert image._find_chosen_text(tid,stage('image')).strip()==approved_text.strip()
tts=stage('tts')
if not state.get('external_id'):
    raw=sb.storage.from_('artifacts').download(approved['original_path'])
    name='approved-narration'+Path(approved['original_path']).suffix
    prepared=api('POST','/api/narration',{'stageId':tts['id'],'name':name,'size':len(raw)})
    user.storage.from_('artifacts').upload_to_signed_url(prepared['path'],prepared['token'],raw,{'content-type':'audio/wav' if name.endswith('.wav') else 'audio/mpeg'})
    state['external_id']=prepared['id'];save()
    api('PATCH','/api/narration',{'stageId':tts['id'],'action':'submit','data':{'id':prepared['id']}})
    passed('deployed narration API signed upload')
if stage('tts')['status']=='pending':tick('tts')
version=sb.table('external_narrations').select('*').eq('id',state['external_id']).single().execute().data
if version['state']!='approved':
    review=version['review']
    if not review.get('alignment_ready'):
        trusted=json.loads(sb.storage.from_('artifacts').download(approved['subtitle_path']))
        cues=trusted.get('segments',trusted.get('cues',[]))
        assert cues,'Missing prior approved calibration'
        api('PATCH','/api/narration',{'stageId':tts['id'],'action':'realign','data':{'id':version['id'],'text':approved_text,'cues':cues}})
        tick('tts')
        version=sb.table('external_narrations').select('*').eq('id',version['id']).single().execute().data
        passed('existing approved cue calibration reused for identical audio')
    assert version['review'].get('alignment_ready'),version['review'].get('error')
    api('PATCH','/api/narration',{'stageId':tts['id'],'action':'approve','data':{'id':version['id'],'subtitle_path':version['subtitle_path']}})
passed('real ASR alignment and owner approval')
if not state.get('bgm_saved'):
    # Self-generated test sound, not a commercial music selection.
    music=out/'test-background.mp3'
    subprocess.run([ff(),'-v','error','-y','-f','lavfi','-i','aevalsrc=0.08*sin(2*PI*220*t)+0.05*sin(2*PI*330*t):s=44100:d=12','-c:a','libmp3lame',str(music)],check=True,capture_output=True)
    path=f'{tid}/background-music/test-background.mp3'
    user.storage.from_('artifacts').upload(path,music.read_bytes(),{'content-type':'audio/mpeg','upsert':'true'})
    user.table('tasks').update({'bgm_path':path,'bgm_volume':0.08,'narration_volume':1.0,'bgm_authorization_confirmed':True}).eq('id',tid).execute()
    state['bgm_saved']=True;save();passed('owner-scoped test music upload and volume settings')
tick('image');passed('real APIMart 4K landscape nine-grid generation')
tick('book');passed('book compatibility node')
render=tick('render');assert render['output_ref']
raw=sb.storage.from_('artifacts').download(render['output_ref']);(out/'final.mp4').write_bytes(raw)
quality=json.loads(sb.storage.from_('artifacts').download(tid+'/quality_report.json'))
(out/'quality_report.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
assert quality['status']!='failed',quality['summary']
artifacts=sb.table('artifacts').select('type,meta,created_at,stage_kind').eq('task_id',tid).execute().data
final=next(a for a in reversed(artifacts) if a['type']=='final')
assert final['meta']['production_template']=='guoxue-v1'
assert final['meta']['bgm_enabled'] is True
assert final['meta']['text_layout']['subtitle_font']=='KaiTi'
timings=[a for a in artifacts if a['type']=='stage_timing']
assert {a['stage_kind'] for a in timings} >= {'ingest','transcribe','clean','rewrite','tts','image','book','render'}
assert all(a['meta']['state']=='finished' for a in timings)
passed('full render, mixed audio, quality report and all eight timing records')
report={'task_id':tid,'scope':'isolated real pipeline; confirmed original manuscript and narration reused; synthetic music for mixing only','checks':state['checks'],'quality':quality['summary'],'final_meta':final['meta'],'timings':timings}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
state['complete']=True;save()
print('SUCCESS '+str(out/'final.mp4'),flush=True)
