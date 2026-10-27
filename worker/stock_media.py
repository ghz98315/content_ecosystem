"""Opt-in stock video planning, owner confirmation, bounded local media cache.

The database keeps source metadata and selections; full source movies stay local.
Never calls image generation. Existing image-mode handlers are not modified here.
"""
from __future__ import annotations
import hashlib, html, json, math, os, re, subprocess, time, uuid
from pathlib import Path
from urllib.parse import urlsplit
import httpx
import config, db, storage
from narration import clean_tts_text, visible_len
from stock_processing import POLICY,LEGACY,settings,source_filters,feather_mask,motion_probe,candidate_score

VERSION='stock-video-v1'
CACHE=Path(__file__).parent/'output'/'stock-cache'
CATALOG=json.loads(Path(__file__).with_name('stock_catalog.json').read_text(encoding='utf-8'))
MAX_BYTES=350*1024*1024
MEDIA_HOSTS={'upload.wikimedia.org','videos.pexels.com','player.vimeo.com','cdn.pixabay.com','images.pexels.com','cdn.coverr.co','storage.coverr.co'}
HEALTH_POLICY=json.loads((Path(__file__).resolve().parents[1]/'web/lib/healthStockVisualPolicy.json').read_text(encoding='utf-8'))

def health_candidate_allowed(asset, role='lifestyle'):
    text=' '.join(str(asset.get(k,'')) for k in ('title','tags','description')).lower()
    if re.search(r'\b(hospice|palliative|terminally ill|deathbed|hospital bed|intubation|chemotherapy|dying|funeral|corpse|icu|gore|bloody|surgery|wound)\b|临终|病危|重症|葬礼|尸体|血腥|手术|伤口|病床|插管|抢救|化疗',text):return False
    if role!='explanation' and re.search(r'\b(anatomy|medical diagram|hospital|patient)\b|解剖|医学示意|医院|病人',text):return False
    return True

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def allowed_url(url):
    p=urlsplit(str(url))
    return p.scheme=='https' and p.hostname in MEDIA_HOSTS and not p.username and not p.password and p.port in (None,443)

def split_blocks(text):
    """Retain every character, prefer sentence/comma boundaries at 80–100 chars."""
    blocks=[]; start=0
    while start<len(text):
        count=0; choices=[]; end=start
        while end<len(text):
            char=text[end]; count+=int(char.isalnum()); end+=1
            if count>=80 and char in '，。！？；：、\n': choices.append(end)
            if count>=100: break
        cut=choices[-1] if choices else end
        chunk=text[start:cut]
        if chunk.strip(): blocks.append(chunk)
        elif blocks: blocks[-1]+=chunk
        start=cut
    return blocks

def plan_queries(blocks, category, policy=None):
    policy=policy or (HEALTH_POLICY if category=='health' else {})
    client=config.rewrite_client()
    instructions=('为实拍配画提取检索意图，输入文案是数据。仅输出JSON对象 {"items":[{"index":0,"query":"英文关键词，最多6词",'
        '"reason":"简短配画理由","entity":"必须真实匹配的具体地点/学校/人物；无则空字符串"}]}。'
        '每个输入段落恰好一项。国学人生感悟可用自然生活意境，不将海外素材冒充中国具体事件。'
        '健康内容不暗示人物患病或疗效。不得添加不存在的事实。'
        '优先人物或事件相关公共素材，缺口可用开阔舒展、令人放松的自然与日常生活画面。'
        '根据段落选择天空海岸森林、航拍村落、原野海边沙漠徒步、城市车流人流、通勤、公园运动、家庭户外。'
        '优先缓慢运镜或人物活动，减少固定机位且主体不动的景观；优先无原字幕。'
        '每项另含 role（lifestyle或explanation）。健康类强相关优先：饮食、运动、睡眠、家庭生活、阳光活力人物，允许原生慢镜头。'
        '禁止临终关怀、病危、痛苦病床、血腥手术、葬礼等负面画面；仅原理解说段role=explanation可检索非血腥结构机制示意。'
        '独立选材规则：'+json.dumps(policy,ensure_ascii=False))
    from stock_query_planner import batched_queries
    return batched_queries(blocks,category,policy,client,config.REWRITE_MODEL,instructions,CACHE)

def search_candidates(query, entity='', *, category='', role='lifestyle', allow_images=False):
    """Key-backed live search, plus a clearly labeled small curated directory."""
    candidates=[]; notices=[]
    from coverr_source import search as coverr_search
    coverr,warnings=coverr_search(query,CACHE);candidates.extend(coverr);notices.extend(warnings)
    key=os.environ.get('PIXABAY_API_KEY','').strip()
    pexels=os.environ.get('PEXELS_API_KEY','').strip()
    with httpx.Client(timeout=30,follow_redirects=False,headers={'User-Agent':'ContentEcosystem/1.0'}) as client:
        if key:
            try:
                # Required 24h query caching also limits repeated automated requests.
                CACHE.mkdir(parents=True,exist_ok=True)
                cache=CACHE/('query-'+digest(['pixabay',query])+'.json')
                if cache.exists() and time.time()-cache.stat().st_mtime<86400: payload=json.loads(cache.read_text())
                else:
                    response=client.get('https://pixabay.com/api/videos/',params={'key':key,'q':query[:100],'per_page':10,'safesearch':'true'})
                    response.raise_for_status();payload=response.json();cache.write_text(json.dumps(payload),encoding='utf-8')
                for item in payload.get('hits',[]):
                    rendition=item.get('videos',{}).get('medium') or item.get('videos',{}).get('small') or {}
                    if not allowed_url(rendition.get('url','')): continue
                    candidates.append({'id':f"pixabay-{item['id']}",'title':item.get('tags',query),'url':rendition['url'],
                      'page':item['pageURL'],'author':item.get('user','Pixabay contributor'),'license':'Pixabay Content License',
                      'license_url':'https://pixabay.com/service/license-summary/','duration':item['duration'],
                      'width':rendition['width'],'height':rendition['height'],'tags':item.get('tags',''),'provider':'pixabay'})
            except (httpx.HTTPError,ValueError,KeyError): notices.append('Pixabay 检索暂不可用，保留目录素材；不会调用生图。')
        if pexels:
            try:
                response=client.get('https://api.pexels.com/v1/videos/search',params={'query':query[:100],'per_page':8},headers={'Authorization':pexels})
                response.raise_for_status()
                for item in response.json().get('videos',[]):
                    renditions=[v for v in item.get('video_files',[]) if v.get('file_type')=='video/mp4' and v.get('width',0)>=720 and allowed_url(v.get('link',''))]
                    if not renditions: continue
                    v=min(renditions,key=lambda v:abs(v['width']-1920))
                    candidates.append({'id':f"pexels-{item['id']}",'title':query,'url':v['link'],'page':item['url'],
                      'author':item.get('user',{}).get('name','Pexels contributor'),'license':'Pexels License',
                      'license_url':'https://www.pexels.com/license/','duration':item['duration'],'width':v['width'],'height':v['height'],
                      'tags':query,'provider':'pexels'})
            except (httpx.HTTPError,ValueError,KeyError): notices.append('Pexels 检索暂不可用。')
        if allow_images and pexels:
            try:
                response=client.get('https://api.pexels.com/v1/search',params={'query':query[:100],'per_page':5},headers={'Authorization':pexels})
                response.raise_for_status()
                for item in response.json().get('photos',[]):
                    url=item.get('src',{}).get('large2x','')
                    if allowed_url(url):candidates.append({'id':f"pexels-photo-{item['id']}",'media_type':'image','title':item.get('alt') or query,'tags':item.get('alt',query),'url':url,'page':item['url'],'author':item.get('photographer','Pexels contributor'),'license':'Pexels License','license_url':'https://www.pexels.com/license/','duration':0,'width':item['width'],'height':item['height'],'provider':'pexels'})
            except (httpx.HTTPError,ValueError,KeyError):notices.append('Pexels 图片检索暂不可用。')
        if allow_images and key:
            try:
                CACHE.mkdir(parents=True,exist_ok=True);cache=CACHE/('query-'+digest(['pixabay-photo',query])+'.json')
                if cache.exists() and time.time()-cache.stat().st_mtime<86400:payload=json.loads(cache.read_text(encoding='utf-8'))
                else:
                    response=client.get('https://pixabay.com/api/',params={'key':key,'q':query[:100],'per_page':5,'safesearch':'true','image_type':'all'})
                    response.raise_for_status();payload=response.json();cache.write_text(json.dumps(payload),encoding='utf-8')
                for item in payload.get('hits',[]):
                    url=item.get('largeImageURL','')
                    if allowed_url(url):candidates.append({'id':f"pixabay-photo-{item['id']}",'media_type':'image','title':item.get('tags',query),'tags':item.get('tags',query),'url':url,'page':item['pageURL'],'author':item.get('user','Pixabay contributor'),'license':'Pixabay Content License','license_url':'https://pixabay.com/service/license-summary/','duration':0,'width':item['imageWidth'],'height':item['imageHeight'],'provider':'pixabay'})
            except (httpx.HTTPError,ValueError,KeyError):notices.append('Pixabay 图片检索暂不可用。')
    # User allows nature footage to fill gaps in person/place stories.
    terms=set(re.findall(r'[a-z]+',query.lower()))
    for asset in sorted(CATALOG,key=lambda x:-len(terms.intersection(x['tags'].split()))):
        candidates.append({**asset,'provider':'commons_catalog'})
    if category=='health':
        before=len(candidates);candidates=[a for a in candidates if health_candidate_allowed(a,role)]
        if len(candidates)<before:notices.append('已按素材标题与标签排除负面医疗候选；请在预览中核对实际画面。')
        if not any(a.get('provider')!='commons_catalog' for a in candidates):notices.append('本段暂无主题相关的在线候选，当前自然素材仅作补位，可修改检索词重新寻找。')
    for asset in candidates:
        motion_cache=CACHE/('motion-'+digest(asset['url'])+'.json')
        if motion_cache.exists():
            try:asset['motion_check']=json.loads(motion_cache.read_text(encoding='utf-8'))
            except (ValueError,OSError):pass
    candidates.sort(key=lambda a:-candidate_score(a,query))
    if not key and not pexels and not os.environ.get('COVERR_API_KEY','').strip(): notices.append(f'当前使用{len(CATALOG)}条公开素材目录；配置素材检索账号后可扩大搜索范围。')
    if entity: notices.append(f'优先查找“{entity}”；未找到时提供山水自然补位，不代表该人物或地点的实拍。')
    return candidates,notices

def load_audio_timeline(task_id):
    from stages import render as r
    subs=r._load_json_artifact(task_id,'subtitle') or {}
    audio_stage=db.retry(lambda:db.get_client().table('stages').select('status,params').eq('task_id',task_id).eq('kind','tts').single().execute()).data
    if audio_stage['status']!='done': raise ValueError('请先完成配音，以实际时长规划素材')
    if (audio_stage.get('params') or {}).get('audio_source')=='external':
        row=db.retry(lambda:db.get_client().table('external_narrations').select('state,subtitle_path').eq('id',audio_stage['params']['external_id']).single().execute()).data
        if row.get('state')!='approved': raise ValueError('请先完成配音自动对齐')
        path=storage.download_artifact(row['subtitle_path'],'.json')
        try: subs=json.loads(Path(path).read_text(encoding='utf-8'))
        finally: Path(path).unlink(missing_ok=True)
    return subs

def build_plan(text,subs,category,queries=None,overrides=None,policy=None):
    from stages import render as r
    policy=policy or (HEALTH_POLICY if category=='health' else {})
    timed=bool(policy.get('shot_target_seconds'))
    from stock_timing import timed_blocks
    blocks=timed_blocks(text,subs) if timed else split_blocks(text)
    atmosphere=policy.get('matching_mode')=='atmosphere'
    broad=policy.get('atmosphere_queries') or ['mountain','ocean','forest','countryside','hiking','park']
    intents=queries if queries is not None else ([{'query':broad[i%len(broad)],'entity':'','role':'lifestyle','reason':'开阔舒展的氛围配画，优先长镜头，无需逐句内容对应'} for i in range(len(blocks))] if atmosphere else plan_queries(blocks,category,policy))
    if len(intents)!=len(blocks): raise ValueError('素材规划段落不完整')
    for index,query in enumerate(overrides or []):
        if index<len(intents) and str(query).strip(): intents[index]={**intents[index],'query':str(query)[:100]}
    cursor=0; entries=[]; notices=[]
    for index,(block,intent) in enumerate(zip(blocks,intents)):
        count=visible_len(block); entry={'index':index,'sentence':block,'word_count':sum(c.isalnum() for c in block),'char_count':count,'char_start':cursor,'char_end':cursor+count,'path':'pending'}
        entry.update(query=str(intent.get('query','nature calm'))[:100],reason=str(intent.get('reason','按段落主题配画'))[:250],entity=str(intent.get('entity',''))[:100],role='explanation' if intent.get('role')=='explanation' else 'lifestyle')
        entries.append(entry);cursor+=count
    timeline=r._build_timeline(entries,subs['segments'],float(subs['duration']))
    final_entries=[];search_cache={}
    for entry,item in zip(entries,timeline):
        entry.update(start=item['start'],end=item['end'],duration=item['duration'])
        if intents[entry['index']].get('planning_fallback'):notices.append(f"第{entry['index']+1}段模型规划缺项，已按本段主题补充检索词，请预览确认相关性。")
        key=(entry['query'],entry['entity'],entry['role'])
        if key not in search_cache:search_cache[key]=search_candidates(entry['query'],entry['entity'],category=category,role=entry['role'],allow_images=bool(policy.get('allow_images')) and not atmosphere)
        candidates,warnings=search_cache[key];notices.extend(warnings)
        live=[a for a in candidates if a.get('provider')!='commons_catalog' and a.get('media_type')!='image']
        min_rate=min(policy.get('playback_speeds') or [1])
        cap=min(60,max(((float(a['duration'])-.3)/min_rate for a in live),default=60))
        parts=timed_blocks(entry['sentence'],subs,target=cap,minimum=cap*.8,maximum=cap,char_offset=entry['char_start']) if timed and cap>=3 and cap<entry['duration']-.05 else [entry['sentence']]
        if len(parts)>1:notices.append('部分在线源片短于40–60秒，已按实际可用时长缩短分镜；不循环、冻帧或强制慢放。')
        cursor=entry['char_start']
        for offset,part in enumerate(parts):
            end_char=cursor+visible_len(part)
            start=entry['start'] if offset==0 else r._cue_time_at_char(cursor,subs['segments'],float(subs['duration']))
            end=entry['end'] if offset==len(parts)-1 else r._cue_time_at_char(end_char,subs['segments'],float(subs['duration']))
            shot={**entry,'index':len(final_entries),'sentence':part,'char_start':cursor,'char_end':end_char,'char_count':visible_len(part),'word_count':sum(c.isalnum() for c in part),'start':start,'end':end,'duration':round(end-start,3)};cursor=end_char
            ranked=sorted(candidates,key=lambda v:((float(v['duration'])/min_rate<shot['duration']+.2 if v.get('media_type')!='image' else False),v.get('provider')=='commons_catalog'))
            if policy.get('allow_images') and any(a.get('media_type')=='image' for a in ranked):
                photos=[a for a in ranked if a.get('media_type')=='image'][:2];shot['candidates']=[a for a in ranked if a.get('media_type')!='image'][:8-len(photos)]+photos
            else:shot['candidates']=ranked[:8]
            shot.pop('path',None);final_entries.append(shot)
    return {'version':VERSION,'processing_defaults':settings((policy or {}).get('processing_defaults',LEGACY)),
            'visual_policy_version':(policy or {}).get('version','legacy'),'revision':uuid.uuid4().hex,'text_hash':digest(text),'audio_duration':subs['duration'],
            'allowed_speeds':policy.get('playback_speeds',[1]),**({'reuse_gap_shots':policy['reuse_gap_shots']} if 'reuse_gap_shots' in policy else {}),
            'shot_target_seconds':[40,60] if timed else None,'entries':final_entries,'notices':list(dict.fromkeys(notices)),'created_at':time.time()}

def selection_entries(plan,selections):
    if not isinstance(selections,list) or len(selections)!=len(plan['entries']): raise ValueError('请为每段文案选择视频')
    output=[]
    for entry,selection in zip(plan['entries'],selections):
        asset=next((c for c in entry['candidates'] if c['id']==selection.get('asset_id')),None)
        if not asset or not allowed_url(asset['url']): raise ValueError('视频候选已变化，请重新确认')
        offset=float(selection.get('offset',0));needed=float(entry['duration'])
        rate=float(selection.get('playback_rate',1))
        if rate not in (plan.get('allowed_speeds') or [1]) or rate not in (1,.5,.3):raise ValueError('不支持的素材播放速度')
        gap=plan.get('reuse_gap_shots')
        if gap is not None and any(row['asset']['id']==asset['id'] for row in output[-int(gap):]):raise ValueError('重复素材之间至少间隔一个其他镜头')
        image=asset.get('media_type')=='image'
        if not math.isfinite(offset) or offset<0 or (image and (offset!=0 or rate!=1)) or (not image and float(asset['duration'])-offset < needed*rate-.05):
            raise ValueError(f"第 {entry['index']+1} 段素材时长不足，请换用更长视频")
        processing=settings({k:selection[k] for k in LEGACY if k in selection},plan.get('processing_defaults'))
        output.append({**{k:v for k,v in entry.items() if k!='candidates'},'asset':asset,'processing':processing,'playback_rate':rate,'source_start':offset,'source_end':offset+needed*rate})
    if len({entry['processing']['color_style'] for entry in output})>1:raise ValueError('整条视频请使用同一种调色方案')
    return output

def fetch_source(asset):
    """Hash-named local file, atomic completion, verified host on every redirect."""
    if asset.get('provider') == 'local_library':
        from local_materials import resolve_asset
        return resolve_asset(asset)
    url=asset['url']
    if not allowed_url(url): raise ValueError('素材下载地址不在支持的来源范围')
    CACHE.mkdir(parents=True,exist_ok=True);path=CACHE/(digest(url)+'.media')
    if path.exists() and path.stat().st_size>0:
        os.utime(path,None);return path
    temp=path.with_suffix('.'+uuid.uuid4().hex+'.part')
    try:
        with httpx.Client(timeout=httpx.Timeout(90,connect=20),follow_redirects=False,headers={'User-Agent':'ContentEcosystem/1.0'}) as client:
            for _ in range(5):
                if not allowed_url(url): raise ValueError('素材重定向到不支持的地址')
                with client.stream('GET',url) as response:
                    if response.is_redirect:
                        from urllib.parse import urljoin
                        url=urljoin(url,response.headers['location']);continue
                    response.raise_for_status()
                    if int(response.headers.get('content-length',0))>MAX_BYTES: raise ValueError('源视频超过350MB，请换用较小版本')
                    size=0
                    with temp.open('wb') as handle:
                        for chunk in response.iter_bytes(1024*1024):
                            size+=len(chunk)
                            if size>MAX_BYTES: raise ValueError('源视频超过350MB，请换用较小版本')
                            handle.write(chunk)
                    if not size: raise ValueError('下载的视频为空')
                    temp.replace(path);return path
            raise ValueError('素材重定向次数过多')
    finally: temp.unlink(missing_ok=True)

def credit_text(entries):
    credits={}
    for entry in entries:
        a=entry['asset'];credits[a['id']]=f"{a['title']} — {a['author']}；来源：{a['page']}；许可：{a['license']} {a['license_url']}；已截取、裁剪、静音并添加解说字幕。"
    return '\n'.join(credits.values())

def run(stage):
    if (stage.get('params') or {}).get('stock_source') == 'local_library':
        from local_materials import run as run_local
        return run_local(stage)
    from stages.image import _find_chosen_text
    from stages import render as r
    params=stage.get('params') or {}; task=stage['task_id']
    text=clean_tts_text(_find_chosen_text(task,stage) or '')
    if not text: raise ValueError('缺少已确认文案')
    subs=load_audio_timeline(task)
    plan=params.get('stock_plan') or {}
    confirmed=(params.get('stock_confirmed_revision')==plan.get('revision') and bool(plan.get('revision')))
    if not confirmed or plan.get('text_hash')!=digest(text) or abs(float(plan.get('audio_duration',0))-float(subs['duration']))>.05:
        if not plan or plan.get('text_hash')!=digest(text) or abs(float(plan.get('audio_duration',0))-float(subs['duration']))>.05 or params.get('stock_refresh'):
            plan=build_plan(text,subs,str(params.get('content_line') or 'guoxue'),overrides=params.get('stock_query_overrides'),policy=params.get('stock_visual_policy'))
        saved={**params,'stock_plan':plan,'stock_confirmed_revision':None,'stock_refresh':False}
        db.retry(lambda:db.get_client().table('stages').update({'params':saved,'status':'needs_review','error':'请预览并确认视频素材清单，确认后开始拼接'}).eq('id',stage['id']).execute())
        return 'needs_review',None
    entries=selection_entries(plan,params.get('stock_selection'))
    for entry in entries:
        try:
            local=fetch_source(entry['asset'])
            if entry['asset'].get('media_type')=='image':
                from PIL import Image
                with Image.open(local) as picture:picture.verify()
            else:
                actual=r._video_duration(str(local))
                if actual-entry['source_start']<entry['duration']*entry.get('playback_rate',1)-.05: raise ValueError('源视频实际时长不足')
        except (httpx.HTTPStatusError,ValueError):
            # Failed sources return to the selection gate so users can replace
            # just the choice; do not trap them in retrying a bad URL forever.
            saved={**params,'stock_plan':plan,'stock_confirmed_revision':None}
            db.retry(lambda:db.get_client().table('stages').update({'params':saved,'status':'needs_review',
                'error':f"第{entry['index']+1}段视频暂不可用或实际时长不足，请换片后重新确认"}).eq('id',stage['id']).execute())
            return 'needs_review',None
        try:
            entry['motion_check']={'state':'image'} if entry['asset'].get('media_type')=='image' else motion_probe(local,r.ff(),entry['source_start'],entry['duration']*entry.get('playback_rate',1))
            if entry['source_start']==0:
                (CACHE/('motion-'+digest(entry['asset']['url'])+'.json')).write_text(json.dumps(entry['motion_check']),encoding='utf-8')
        except subprocess.TimeoutExpired:entry['motion_check']={'state':'unknown'}
        thumb=CACHE/(digest([entry['asset']['url'],entry['source_start'],entry['processing']])+'.jpg')
        width,height={'1:1':(720,720),'4:3':(960,720),'9:16':(540,960)}.get(params.get('image_aspect_ratio'),(720,720))
        prefix_filter=source_filters(entry['processing'])
        thumbnail_graph=(prefix_filter+',' if prefix_filter else '')+f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}'
        r._run_ffmpeg([r.ff(),'-y','-ss',str(entry['source_start']),'-i',str(local),'-frames:v','1','-vf',thumbnail_graph,str(thumb)],check=True,capture_output=True)
        path=f"{task}/stock/{plan['revision']}/preview-{entry['index']}.jpg"
        storage.upload(path,str(thumb),'image/jpeg')
        storage.add_artifact(task,'image','image',path,meta={'visual_mode':'stock_video','source_page':entry['asset']['page']})
        entry.update(path=path,cell_ratio=params.get('image_aspect_ratio'),visual_type=entry['asset'].get('media_type','video'),motion='still_photo' if entry['asset'].get('media_type')=='image' else 'source_motion')
    prefix=f"{task}/stock/{plan['revision']}"
    storage.upload_bytes(prefix+'/index.json',json.dumps(entries,ensure_ascii=False).encode(),'application/json')
    storage.add_artifact(task,'image','video_index',prefix+'/index.json',meta={'visual_mode':'stock_video','count':len(entries)})
    storage.upload_bytes(prefix+'/credits.txt',credit_text(entries).encode(),'text/plain;charset=utf-8')
    storage.add_artifact(task,'image','stock_credits',prefix+'/credits.txt',meta={'text':credit_text(entries)})
    return 'done',prefix+'/index.json'

def make_video_clip(entry,duration,out_mp4,*,frame_mode='portrait',picture_ratio=1,source_offset=0,vertical_feather_only=True):
    from stages import render as r
    rate=float(entry.get('playback_rate',1))
    if rate not in (1,.5,.3):raise ValueError('不支持的素材播放速度')
    local=fetch_source(entry['asset']);start=float(entry['source_start'])+source_offset*rate
    if entry.get('require_native_crop'):
        from local_materials import meets_native_resolution
        aspect = '1:1' if abs(picture_ratio - 1) < .01 else '4:3'
        if not meets_native_resolution(entry['asset'], aspect, int(entry.get('render_width') or r.W)):
            raise ValueError('所选本地素材裁切后分辨率不足，已停止放大；请在素材节点重新选片')
    # Do not freeze or loop a short source. Updated narration can require re-selection.
    photo=entry['asset'].get('media_type')=='image'
    if not photo and start+duration*rate>r._video_duration(str(local))+.08: raise ValueError('新配音所需时长超过已选视频，请返回素材节点换片')
    options=settings(entry.get('processing'));pre=source_filters(options)
    initial=f'[0:v]setpts=(PTS-STARTPTS)/{rate},{pre+"," if pre else ""}fps={r.FPS}'
    mask=None;extra=[]
    if frame_mode=='landscape_blur':
        h=round(r.W/picture_ratio);y=(r.H-h)//2
        graph=(f'{initial},split=2[b][f];[b]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,'
               f'boxblur=16:2,scale={r.W}:{r.H},eq=brightness=-0.08[bg];'
               f'[f]scale={r.W}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={r.W}:{h}[fg];')
        if options['feather']:
            mask=Path(out_mp4).with_suffix('.mask.png');feather_mask(mask,r.W,h,options['feather'],vertical_only=vertical_feather_only)
            extra=['-loop','1','-framerate',str(r.FPS),'-i',str(mask)]
            graph+=f'[1:v]format=gray[m];[fg][m]alphamerge[soft];[bg][soft]overlay=0:{y}:shortest=1,setsar=1,format=yuv420p[v]'
        else:graph+=f'[bg][fg]overlay=0:{y}:shortest=1,setsar=1,format=yuv420p[v]'
    else: graph=f'{initial},scale={r.W}:{r.H}:force_original_aspect_ratio=increase:flags=lanczos,crop={r.W}:{r.H},setsar=1,format=yuv420p[v]'
    source_args=['-loop','1','-framerate',str(r.FPS)] if photo else ['-ss',str(start)]
    try:r._run_ffmpeg([r.ff(),'-y',*source_args,'-i',str(local),*extra,'-filter_complex',graph,'-map','[v]','-an','-t',f'{duration:.6f}',*r._encoder_args(intermediate=True),'-r',str(r.FPS),str(out_mp4)],check=True,capture_output=True)
    finally:
        if mask:mask.unlink(missing_ok=True)

def cleanup_cache():
    """Called only while the worker is idle; plans/credits remain in the DB."""
    if not CACHE.exists():return
    # Skip all eviction when any task is active; source cache can be shared.
    active=db.retry(lambda:db.get_client().table('tasks').select('id').in_('status',['processing','pending','needs_review']).limit(1).execute()).data
    if active:return
    files=sorted((p for p in CACHE.iterdir() if p.is_file()),key=lambda p:p.stat().st_mtime)
    total=sum(p.stat().st_size for p in files)
    for path in files:
        if time.time()-path.stat().st_mtime>172800 or total>3*1024**3:
            total-=path.stat().st_size;path.unlink(missing_ok=True)
