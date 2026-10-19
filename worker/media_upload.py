"""Bounded pre-upload preparation. Sources are never overwritten."""
import math,os,re,subprocess,tempfile,time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import db

DEFAULT_LIMIT=50_000_000
def upload_limit_bytes():
    return _cached_upload_limit(int(time.monotonic()//300))

@lru_cache(maxsize=1)
def _cached_upload_limit(window):
    configured=int(os.environ.get('STORAGE_FILE_LIMIT_BYTES',str(DEFAULT_LIMIT)))
    bucket=db.retry(lambda:db.get_client().storage.get_bucket(os.environ.get('SUPABASE_BUCKET','artifacts')))
    limit=getattr(bucket,'file_size_limit',None)
    cap=min(configured,limit) if isinstance(limit,int) and limit>0 else configured
    if cap<=0:raise ValueError('存储文件上限配置无效')
    return math.floor(cap*.96)

def _ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def duration(path):
    try:probe=subprocess.run([_ffmpeg(),'-hide_banner','-i',str(path)],capture_output=True,timeout=30)
    except subprocess.TimeoutExpired as exc:raise ValueError('媒体时长读取超时，已停止上传') from exc
    match=re.search(rb'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',probe.stderr)
    if not match:raise ValueError('无法读取媒体时长，已停止上传')
    h,m,s=map(float,match.groups());value=h*3600+m*60+s
    if not value>0:raise ValueError('媒体时长无效，已停止上传')
    return value

@contextmanager
def prepared_file(source,content_type,limit=None):
    limit=upload_limit_bytes() if limit is None else limit
    size=Path(source).stat().st_size
    if size<=0:raise ValueError('文件为空，已停止上传')
    if size<=limit:
        yield str(source);return
    target=int(limit*.9)
    with tempfile.TemporaryDirectory(prefix='upload-prepare-') as tmp:
        output=Path(tmp)/('prepared'+Path(source).suffix)
        if content_type.startswith(('audio/','video/')):
            before=duration(source);base=[_ffmpeg(),'-v','error','-y','-i',str(source)]
            if content_type in ('audio/mpeg','audio/mp3'):
                budget=target*8/before/1000;rates=[r for r in (48,64,80,96,112,128,160,192) if r<=budget]
                if not rates:raise ValueError('音频过长，无法安全压到存储上限，请分段')
                args=['-map','0:a:0','-vn','-c:a','libmp3lame','-b:a',f'{max(rates)}k','-ar','44100','-ac','2','-f','mp3']
            elif content_type in ('audio/wav','audio/x-wav'):
                codec,rate=('pcm_s16le',16000) if before*32000+8192<=target else ('adpcm_ima_wav',22050)
                if codec=='adpcm_ima_wav' and before*11025*1.05>target:raise ValueError('WAV过长，请先转为MP3或分段')
                args=['-map','0:a:0','-vn','-c:a',codec,'-ar',str(rate),'-ac','1','-f','wav']
            elif content_type=='video/mp4':
                bitrate=int((target*8/before-96000)/1000)
                if bitrate<80:raise ValueError('视频过长，无法在存储上限内保留可用画质，请分段')
                args=['-map','0:v:0','-map','0:a:0?','-c:v','libx264','-preset','veryfast','-b:v',f'{bitrate}k','-maxrate',f'{bitrate}k','-bufsize',f'{bitrate*2}k','-pix_fmt','yuv420p','-c:a','aac','-b:a','64k','-movflags','+faststart','-f','mp4']
            else:raise ValueError('该媒体格式超过存储限制，请先转成MP3或MP4')
            try:result=subprocess.run([*base,*args,str(output)],capture_output=True,timeout=300)
            except subprocess.TimeoutExpired as exc:raise ValueError('上传前处理超过5分钟，原文件已保留，请导出较小文件') from exc
            if result.returncode:raise ValueError('上传前媒体处理失败，原文件已保留')
            after=duration(output)
            if abs(after-before)>max(.2,before*.001):raise ValueError('处理后的媒体时长不一致，已停止上传')
        elif content_type.startswith('image/'):
            from PIL import Image
            with Image.open(source) as image:
                if content_type=='image/png':image.save(output,format='PNG',optimize=True)
                elif content_type=='image/jpeg':image.convert('RGB').save(output,format='JPEG',quality=85,optimize=True)
                else:raise ValueError('图片超过存储限制，请先压缩')
        else:raise ValueError('文件超过存储上限，已在上传前拦截，请拆分文件')
        if not output.exists() or not 0<output.stat().st_size<=limit:
            raise ValueError('自动处理后仍超过存储限制，原文件已保留，请进一步压缩或分段')
        print(f'  [upload] 已处理超限媒体：{size/1_000_000:.1f} → {output.stat().st_size/1_000_000:.1f} MB',flush=True)
        yield str(output)
