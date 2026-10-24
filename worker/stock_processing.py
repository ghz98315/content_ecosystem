"""Versioned, lightweight processing for selected stock footage only."""
from __future__ import annotations
import json,math,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageStat

POLICY=json.loads((Path(__file__).resolve().parents[1]/'web/lib/stockVisualPolicy.json').read_text(encoding='utf-8'))
LEGACY={'crop_top':0,'crop_bottom':0,'color_style':'none','feather':0}

def settings(value=None,defaults=None):
    result={**LEGACY,**(defaults or {}),**(value or {})}
    for key,maximum in [('crop_top',.25),('crop_bottom',.25),('feather',72)]:
        result[key]=float(result[key])
        if not math.isfinite(result[key]) or not 0<=result[key]<=maximum:raise ValueError('视频裁切或羽化参数超出范围')
    if result['crop_top']+result['crop_bottom']>.4:raise ValueError('上下裁切总量不能超过40%，请保留人物与主体')
    if result['color_style'] not in {'none','natural_warm_v1'}:raise ValueError('未知调色方案')
    return result

def source_filters(options):
    options=settings(options);filters=[]
    top,bottom=options['crop_top'],options['crop_bottom']
    if top or bottom:
        filters.append(f'crop=iw:trunc(ih*{1-top-bottom:.6f}/2)*2:0:trunc(ih*{top:.6f}/2)*2')
    if options['color_style']=='natural_warm_v1':
        filters+=['eq=contrast=1.015:brightness=0.006:saturation=0.94','colorbalance=rs=0.012:bs=-0.008']
    return ','.join(filters)

def feather_mask(path,width,height,feather):
    # Static mask, decoded once and reused; avoids a per-pixel geq per video frame.
    amount=min(round(feather*width/1080),min(width,height)//4)
    mask=Image.new('L',(width,height),255);draw=ImageDraw.Draw(mask)
    for inset in range(amount):
        draw.rectangle((inset,inset,width-1-inset,height-1-inset),outline=round(255*inset/max(1,amount)))
    mask.save(path)

def motion_probe(path,ffmpeg,start=0,duration=8):
    """Conservative freeze hint, not person detection or camera-motion proof."""
    command=[ffmpeg,'-v','error','-ss',str(start),'-i',str(path),'-t',str(min(8,duration)),
             '-vf','fps=2,scale=96:54','-an','-pix_fmt','gray','-f','rawvideo','-']
    process=subprocess.run(command,capture_output=True,timeout=35)
    if process.returncode:return {'state':'unknown'}
    size=96*54;data=process.stdout;frames=[Image.frombytes('L',(96,54),data[i:i+size]) for i in range(0,len(data)-size+1,size)]
    if len(frames)<3:return {'state':'unknown'}
    differences=[ImageStat.Stat(ImageChops.difference(a,b)).mean[0] for a,b in zip(frames,frames[1:])]
    mean=sum(differences)/len(differences)
    return {'state':'nearly_static' if max(differences)<.65 else 'changing','mean_frame_difference':round(mean,3),'sample_seconds':min(8,duration)}

def candidate_score(asset,query=''):
    text=' '.join(str(asset.get(key,'')) for key in ('title','tags','motion_hint')).lower()
    words=set(query.lower().split());score=len(words.intersection(text.split()))*2
    if asset.get('provider') and asset['provider']!='commons_catalog':score+=20
    if any(w in text for w in ['drone','aerial','tracking','walking','hiking','commute','running','family','航拍','漫步','徒步','通勤','运动']):score+=5
    if any(w in text for w in ['static_scenery','still image','静景','静止']):score-=8
    if any(w in text for w in ['subtitles','captioned','字幕','watermark','水印']):score-=10
    if (asset.get('motion_check') or {}).get('state')=='nearly_static':score-=12
    return score
