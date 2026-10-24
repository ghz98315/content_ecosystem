"""Coverr adapter with private 24h search cache and a conservative hourly budget."""
import hashlib,json,os,time,math
from pathlib import Path
from urllib.parse import urlsplit
import httpx

HOSTS={'cdn.coverr.co','storage.coverr.co'}
def assets_from_payload(payload):
    result=[]
    for item in payload.get('hits',[]):
        if item.get('is_premium') or item.get('is_ai_generated'):continue
        urls=item.get('urls') or {};url=urls.get('mp4_download') or urls.get('mp4') or ''
        try:duration=float(item.get('duration',0));width=int(item.get('max_width',0));height=int(item.get('max_height',0))
        except (TypeError,ValueError):continue
        if not math.isfinite(duration) or duration<=0 or width<720 or height<=0 or urlsplit(url).scheme!='https' or urlsplit(url).hostname not in HOSTS:continue
        identifier=str(item.get('id',''));slug=item.get('slug') or identifier
        tags=item.get('tags') or []
        if isinstance(tags,list):tags=' '.join(str(x) for x in tags)
        result.append({'id':'coverr-'+identifier,'provider':'coverr','title':str(item.get('title','Coverr video')),'description':str(item.get('description','')),'tags':tags,'url':url,'preview_url':urls.get('mp4_preview') or urls.get('mp4') or url,'page':'https://coverr.co/videos/'+slug,'author':(item.get('contributor') or {}).get('name','Coverr contributor') if isinstance(item.get('contributor'),dict) else 'Coverr contributor','license':'Coverr License','license_url':'https://coverr.co/license','duration':duration,'width':width,'height':height})
    return result

def search(query,cache):
    key=os.environ.get('COVERR_API_KEY','').strip()
    if not key:return [],[]
    cache.mkdir(parents=True,exist_ok=True)
    signature=hashlib.sha256(key.encode()).hexdigest()[:16]
    path=cache/('coverr-'+hashlib.sha256((signature+query).encode()).hexdigest()+'.json')
    if path.exists() and time.time()-path.stat().st_mtime<86400:
        try:return assets_from_payload(json.loads(path.read_text(encoding='utf-8'))),[]
        except (ValueError,OSError):pass
    ledger=cache/('coverr-budget-'+signature+'.json');lock=ledger.with_suffix('.lock');handle=None
    try:
        # Cross-process guard: do not spend API quota concurrently on the same workstation.
        if lock.exists() and time.time()-lock.stat().st_mtime>60:lock.unlink(missing_ok=True)
        handle=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        try:data=json.loads(ledger.read_text(encoding='utf-8'))
        except (OSError,ValueError):data=[]
        now=time.time();data=[t for t in data if isinstance(t,(int,float)) and now-t<3600]
        if len(data)>=40:return [],['Coverr 本小时检索预算已用完，保留缓存素材；稍后可重新检索。']
        data.append(now);ledger.write_text(json.dumps(data),encoding='utf-8')
    except FileExistsError:return [],['Coverr 正在处理其他检索，暂用已有素材。']
    finally:
        if handle is not None:os.close(handle);lock.unlink(missing_ok=True)
    try:
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            response=client.get('https://api.coverr.co/videos',params={'query':query[:100],'page_size':40,'urls':'true'},headers={'Authorization':'Bearer '+key})
            if response.status_code==429:return [],['Coverr 免费额度暂时用完，保留缓存素材，稍后重试。']
            if response.status_code in (401,403):return [],['Coverr 认证或套餐权限不足，请检查密钥；不会自动升级或付费。']
            response.raise_for_status();payload=response.json()
        path.write_text(json.dumps(payload),encoding='utf-8');return assets_from_payload(payload),[]
    except (httpx.HTTPError,ValueError):return [],['Coverr 暂时无法检索，使用已有素材；不会调用生图。']
