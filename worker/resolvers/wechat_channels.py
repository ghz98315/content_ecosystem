"""Video Channels acquisition via the user's Yuanbao session; no system proxy changes."""
from __future__ import annotations
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urljoin
import httpx
from dotenv import dotenv_values
from . import ResolveResult

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36'
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
ENV_FILE = Path(__file__).resolve().parents[1] / '.env'

class ChannelsError(ValueError):
    """Safe user-facing error; never include a provider URL, token, or raw response."""

def cookie_value():
    # Read on each request so replacing the exported session does not require restart.
    values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    return str(values.get('YUANBAO_COOKIE', os.environ.get('YUANBAO_COOKIE', '')) or '').strip()

def normalize_url(value):
    match = re.search(r'https://[^\s<>"，。\[\]()（）]+', str(value or ''))
    url = (match.group(0) if match else str(value or '')).rstrip(')）]')
    parsed = urlparse(url)
    valid = parsed.scheme == 'https' and parsed.hostname in ('weixin.qq.com', 'channels.weixin.qq.com')
    if not valid or parsed.username or parsed.password or parsed.port not in (None,443) or len(url)>4000:
        raise ChannelsError('请输入腾讯视频号 HTTPS 分享链接，或上传原视频/音频。')
    if parsed.hostname == 'weixin.qq.com' and not parsed.path.startswith(('/sph/','/channels/')):
        raise ChannelsError('该链接不是支持的视频号分享链接，请使用 weixin.qq.com/sph/ 分享链接。')
    return url

def _media_url(url):
    parsed=urlparse(str(url or ''));host=parsed.hostname or ''
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not (host.endswith('.video.qq.com') or host.endswith('.tc.qq.com')):
        raise ChannelsError('视频号返回了非预期媒体地址，已停止下载；可上传原视频或音频。')
    return url

def _post(client,url,**kwargs):
    try:
        response=client.post(url,**kwargs)
        if response.status_code in (401,403):
            raise ChannelsError('视频号解析登录态失效或访问受限，请重新登录元宝并更新 worker/.env 的 YUANBAO_COOKIE，然后重跑采集；也可上传视频/音频。')
        if not response.is_success:
            raise ChannelsError('视频号解析服务暂不可用，请稍后重跑采集或上传原视频/音频。')
        data=response.json()
        if not isinstance(data,dict):raise ValueError('shape')
        return data
    except ChannelsError:raise
    except (httpx.HTTPError,ValueError):
        raise ChannelsError('视频号解析连接或响应异常，请稍后重试；登录态无效时更新 YUANBAO_COOKIE。') from None

def _engagement(feed):
    """Preserve platform display counts and exact integer counts separately."""
    fields={
        'likes':('likeCountFmt','likeCount','like_count'),
        'comments':('commentCountFmt','commentCount','comment_count'),
        'shares':('forwardCountFmt','forwardCount','shareCount','share_count'),
        'saves':('favCountFmt','favCount','favoriteCount','collectCount'),
    }
    display={};exact={};estimated={}
    for name,keys in fields.items():
        for key in keys:
            value=feed.get(key)
            if value is None or value=='':continue
            if isinstance(value,int) and not isinstance(value,bool) and value>=0:
                exact[name]=value
                display.setdefault(name,str(value))
                continue
            if isinstance(value,str):
                value=value.strip()
                approximate=re.fullmatch(r'(\d+(?:\.\d+)?)万',value)
                if approximate:
                    display.setdefault(name,value)
                    estimated[name]=round(float(approximate.group(1))*10000)
                elif '\ufffd' not in value:
                    display.setdefault(name,value)
                    if value.isdigit():exact[name]=int(value)
    return display,exact,estimated

def resolve(source_url):
    url=normalize_url(source_url);cookie=cookie_value()
    if not cookie or '\r' in cookie or '\n' in cookie:
        raise ChannelsError('未配置有效的元宝登录态，请在 worker/.env 设置 YUANBAO_COOKIE，或上传视频/音频。')
    # Cookie is attached only to this fixed Yuanbao host; redirects are disabled.
    with httpx.Client(verify=True,trust_env=False,timeout=30,follow_redirects=False) as client:
        parsed=_post(client,'https://yuanbao.tencent.com/api/weixin/get_parse_result',
            json={'type':'video_channel_url','url':url,'scene':1},
            headers={'Cookie':cookie,'Origin':'https://yuanbao.tencent.com','Referer':'https://yuanbao.tencent.com/','User-Agent':UA})
        profile=parsed.get('data') or {}
        if not isinstance(profile,dict) or not profile.get('wx_export_id'):
            raise ChannelsError('元宝未返回视频信息，请确认链接可播放；若登录态失效，更新 YUANBAO_COOKIE 后重试。')
        playable=urlparse(str(profile.get('playable_url') or ''))
        if playable.scheme!='https' or playable.hostname!='channels.weixin.qq.com':
            raise ChannelsError('未拿到有效的视频号播放信息，请稍后重试或上传视频。')
        parts=parse_qs(playable.query);token=parts.get('token',[''])[0];eid=parts.get('eid',[''])[0]
        if not token or not eid:raise ChannelsError('视频号播放凭据不完整，请更新元宝登录态后重试。')
        detail=_post(client,'https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info',
            params={'_rid':format(int(time.time()),'x'), '_pageUrl':'https://channels.weixin.qq.com/finder-preview/pages/feed'},
            json={'baseReq':{'generalToken':token},'exportId':eid},
            headers={'Origin':'https://channels.weixin.qq.com','Referer':playable.geturl(),'User-Agent':UA})
    payload=detail.get('data') or {}
    problem=payload.get('errMsg') if isinstance(payload,dict) else None
    if detail.get('errCode') or not isinstance(payload,dict) or (isinstance(problem,dict) and problem.get('type')):
        raise ChannelsError('视频号暂未允许读取该内容，请确认微信可播放并稍后重试，或上传视频/音频。')
    feed=payload.get('feedInfo') or {}
    if not isinstance(feed,dict):raise ChannelsError('视频号返回了异常的视频信息，请稍后重试或上传视频。')
    h264=feed.get('h264VideoInfo') or {}
    if not isinstance(h264,dict):h264={}
    media=_media_url(h264.get('videoUrl') or feed.get('videoUrl'))
    # Persist only descriptive metadata. Session cookie, playback tokens and signed URLs stay in memory.
    stats,exact,estimated=_engagement(feed)
    return ResolveResult(ok=True,title=str(profile.get('desc') or feed.get('description') or ''),
        author={'name':str(profile.get('author') or '')},video_url=media,
        raw={'resolver':'wechat_channels_yuanbao','source_platform':'wechat_channels',
             'stats_display':stats,'stats_exact':exact,'stats_estimated':estimated,
             'stats_collected_at':int(time.time())})

def download(url):
    """Bounded download with each redirect validated; never attaches Yuanbao cookies."""
    fd,path=tempfile.mkstemp(suffix='.mp4');os.close(fd);started=time.monotonic()
    try:
        with httpx.Client(verify=True,trust_env=False,timeout=httpx.Timeout(30,read=30),follow_redirects=False) as client:
            for _ in range(5):
                _media_url(url)
                with client.stream('GET',url,headers={'User-Agent':UA,'Referer':'https://channels.weixin.qq.com/'}) as response:
                    if response.status_code in (301,302,303,307,308):
                        url=urljoin(url,response.headers.get('location',''));continue
                    if not response.is_success:raise ChannelsError('视频号媒体地址已失效，请重跑采集获取新地址。')
                    size=0
                    with open(path,'wb') as out:
                        for chunk in response.iter_bytes(1024*1024):
                            size+=len(chunk)
                            if size>MAX_DOWNLOAD_BYTES or time.monotonic()-started>300:
                                raise ChannelsError('视频号下载超过本机测试容量或时间限制，请上传压缩后的视频或音频。')
                            out.write(chunk)
                    if not size:raise ChannelsError('视频号下载文件为空，请重试或上传原视频。')
                    return path
            raise ChannelsError('视频号媒体跳转过多，已停止下载，请稍后重试。')
    except BaseException as exc:
        Path(path).unlink(missing_ok=True)
        if isinstance(exc,httpx.HTTPError):raise ChannelsError('视频号下载连接异常，请稍后重试或上传原视频/音频。') from None
        raise
