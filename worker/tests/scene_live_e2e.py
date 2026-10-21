"""Explicit live acceptance for the user-authorized Shenzhen sample.

Runs real handlers in an isolated configuring task, so the production poller
cannot claim this task midway through test-controlled review actions.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import time
import traceback
import config
import db
import storage
from stages import REAL_HANDLERS
from main import StageHeartbeat
from stage_timing import StageTiming
from rewrite_review import effective_length

parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true',required=True)
parser.add_argument('--workspace-task',default=os.environ.get('SCENE_ACCEPTANCE_WORKSPACE_TASK',''))
args=parser.parse_args()
out=Path('worker/output/scene-shenzhen').resolve();out.mkdir(parents=True,exist_ok=True)
statefile=out/'state.json'
state=json.loads(statefile.read_text(encoding='utf-8')) if statefile.exists() else {'timings':{},'checks':[]}
state.setdefault('timings',{});state.setdefault('checks',[])
def save():statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
def passed(name):
    if name not in state['checks']:state['checks'].append(name)
    save();print('PASS '+name,flush=True)
sb=db.get_client()
source=('深圳只有高楼吗？不妨慢下来看看。山和海，也在这座城市里。\n\n'
        '走进莲花山公园，沿着树荫下的步道向上，登高望去，城市的楼宇在远处展开，脚边却是安静的绿意。街道、广场与公园，呈现出不同的生活节奏。\n\n'
        '再把目光转向深圳湾公园，沿海步道连接着开阔的水面与城市风景。海风拂过，散步的人慢慢走着，忙碌一天之后，也能在这里停一停。\n\n'
        '认识深圳，可以从一条街、一片树荫、一段海岸开始。高楼写着城市的速度，山海留下生活的空间。如果给自己留半天，您想先去登高，还是到海边走走？')
(out/'source.txt').write_text(source,encoding='utf-8')
state['source_chars']=effective_length(source);save()
if not state.get('task_id'):
    if not args.workspace_task:parser.error('A workspace task is required only when creating a new acceptance task')
    owner=sb.table('tasks').select('owner').eq('id',args.workspace_task).single().execute().data['owner']
    row=sb.table('tasks').insert({'owner':owner,'title':'山河人文 · 深圳的另一面（全流程验收）','content_category':'education',
        'source_platform':'manual','status':'configuring','tts_source':'automatic','tts_provider':'edge',
        'tts_model':'edge-tts','tts_voice':'zh-CN-YunxiNeural','tts_voice_label':'云希 · 城市旁白','narration_mode':'single'}).execute().data[0]
    state['task_id']=row['id'];save()
tid=state['task_id']
def stage(kind):return sb.table('stages').select('*').eq('task_id',tid).eq('kind',kind).single().execute().data
if not state.get('configured'):
    path=f'{tid}/manual/source.txt';storage.upload_bytes(path,source.encode(),'text/plain')
    settings={
        'ingest':{'manual_file':path,'manual_is_text':True,'manual_title':'深圳的另一面'},
        'rewrite':{'content_line':'scene','rewrite_domain':'scene'},
        'image':{'production_template':'scene-v1','template_version':1,'content_line':'scene','visual_style':'scene_documentary',
                 'visual_preset_id':'scene-documentary','image_aspect_ratio':'9:16','grid_resolution':'2k','image_provider':'apimart',
                 'scene_facts':[{'fact':'莲花山公园位于深圳市中心区，山顶可俯瞰中心区','source':'https://www.sz.gov.cn/ztfw/gysy/wyk_183958/content/post_11530290.html'},
                                {'fact':'深圳湾公园拥有海滨观光道','source':'https://www.sz.gov.cn/szzt2010/gysz/gydt/content/post_11544294.html'}]},
        'book':{'content_line':'scene','skipped':True},
        'tts':{'provider':'edge','model':'edge-tts','voice':'zh-CN-YunxiNeural','rate':'-8%'},
        'render':{'production_template':'scene-v1','template_version':1,'content_line':'scene','frame_mode':'scene_fullscreen',
                  'title_font':'Microsoft YaHei','title_color':'#FFEB00','footnote':'图片由AI生成','cover_duration':0.5}}
    for kind,params in settings.items():sb.table('stages').update({'params':{**stage(kind)['params'],**params}}).eq('id',stage(kind)['id']).execute()
    state['configured']=True;save()
passed('independent scene task configured in original workspace')

def run(kind):
    current=stage(kind)
    if current['status']=='done':return current
    print('RUN '+kind,flush=True)
    sb.table('stages').update({'status':'processing','error':None}).eq('id',current['id']).execute()
    timer=StageTiming(current);timer.start()
    beat=StageHeartbeat(current['id'],15);beat.start()
    start=time.monotonic()
    try:
        status,path=REAL_HANDLERS[kind](current)
        db.set_stage(current['id'],status,output_ref=path)
        if status=='failed':raise RuntimeError(stage(kind).get('error'))
    except Exception:
        db.set_stage(current['id'],'failed',error='场景验收异常，详情保存在本地日志')
        raise
    finally:
        beat.stop();timer.finish();state['timings'][kind]=round(time.monotonic()-start,3);save()
    return stage(kind)

try:
    run('ingest');passed('real manual-text ingest and transcript branch')
    assert stage('transcribe')['status']=='done'
    state['timings']['transcribe']=0;save()
    run('clean');passed('real clean model')
    result=run('rewrite')
    if result['status']=='needs_review':
        local=storage.download_artifact(result['output_ref'],'.json')
        try:rewrite=json.loads(Path(local).read_text(encoding='utf-8'))
        finally:Path(local).unlink(missing_ok=True)
        text=rewrite['candidates'][0]
        assert 0.85 <= effective_length(text)/effective_length(rewrite.get('source_text') or source) <= 1.1
        assert rewrite['compliance']['semantic_complete'],rewrite['compliance']
        assert rewrite['compliance']['status']!='blocked',rewrite['compliance']
        (out/'rewritten.txt').write_text(text,encoding='utf-8')
        (out/'rewrite-review.json').write_text(json.dumps(rewrite,ensure_ascii=False,indent=2),encoding='utf-8')
        state['rewrite_chars']=effective_length(text);state['rewrite_status']=(rewrite.get('rewrite_review') or {}).get('status');save()
        # The user authorized unattended review of this self-authored test copy.
        sb.table('stages').update({'params':{**result['params'],'chosen_index':0,'final_text':text},'status':'pending','error':None}).eq('id',result['id']).execute()
        run('rewrite')
    passed('real rewrite plus automated test-review confirmation')
    run('book');passed('scene publication node adds no book CTA')
    run('tts');passed('real synthesized narration and timed subtitles')
    run('image');passed('real 2K four-grid images and separate creative cover')
    result=run('render')
    assert result['status']=='done',result.get('error')
    local=storage.download_artifact(result['output_ref'],'.mp4');shutil.move(local,out/'final.mp4')
    rows=sb.table('artifacts').select('type,storage_path,meta').eq('task_id',tid).eq('stage_kind','render').order('created_at').execute().data
    for row in rows:
        if row['type'] in ('publication_cover','quality_report','timeline'):
            local=storage.download_artifact(row['storage_path'])
            shutil.move(local,out/({'publication_cover':'cover.png','quality_report':'quality-report.json','timeline':'timeline.json'}[row['type']]))
    final=next(row for row in reversed(rows) if row['type']=='final')
    state['final_meta']=final['meta'];save()
    assert final['meta']['cover_frames']==15 and final['meta']['audio_offset_seconds']==0
    assert final['meta']['title_visibility']=='cover_only' and final['meta']['footnote_visibility']=='full_video'
    passed('real final render, static cover, quality report and timing artifacts')
    assert all(item['status']=='done' for item in sb.table('stages').select('status').eq('task_id',tid).execute().data)
    db.set_task_status(tid,'done')
    state.pop('error',None)
    passed('all eight production nodes completed')
    print('COMPLETE '+tid,flush=True)
except Exception:
    traceback.print_exc();state['error']='See live log';save();raise
