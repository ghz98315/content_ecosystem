"""Scene-only fullscreen rendering. Cover replaces the first 15 frames."""
from __future__ import annotations
import json
import math
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import config
import db
import storage

W,H,FPS=1080,1920,30
COVER_SECONDS=0.5


def ass_time(seconds: float) -> str:
    ticks=max(0,round(seconds*100))
    return f'{ticks//360000}:{ticks//6000%60:02d}:{ticks//100%60:02d}.{ticks%100:02d}'


def write_ass(cues: list[dict], duration: float, footnote: str, path: str):
    from stages.render import _escape_ass
    if len(footnote)>60 or '\n' in footnote or '\r' in footnote:
        raise ValueError('脚注须为60字以内的单行文字')
    lines=['[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n',
           '[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n',
           'Style: Narration,Microsoft YaHei,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,80,80,410,1\n',
           'Style: Footnote,Microsoft YaHei,28,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,3,80,80,150,1\n\n',
           '[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n']
    if footnote:
        lines.append(f'Dialogue: 2,0:00:00.00,{ass_time(duration)},Footnote,,0,0,0,,{_escape_ass(footnote)}\n')
    for cue in cues:
        start=max(COVER_SECONDS,float(cue['start']))
        end=min(duration,float(cue['end']))
        if end>start and str(cue.get('text','')).strip():
            lines.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Narration,,0,0,0,,{_escape_ass(cue['text'])}\n")
    Path(path).write_text(''.join(lines),encoding='utf-8-sig')


def make_cover(source: str, output: str, title: str, subtitle: str, footnote: str = ''):
    from stages.render import _find_cjk_font, _wrap_text
    if len(title)>32 or len(subtitle)>48:
        raise ValueError('封面主副标题过长')
    with Image.open(source) as original:
        image=ImageOps.fit(original.convert('RGB'),(W,H),method=Image.Resampling.LANCZOS)
    draw=ImageDraw.Draw(image)
    font_path=_find_cjk_font(bold=True)
    for text,base_size,y,fill,outline,stroke in (
        (title,156,610,'#FFEB00','#E31314',12),
        (subtitle,92,1100,'#FFFFFF','#111111',8)):
        if not text:
            continue
        size=base_size
        while True:
            font=ImageFont.truetype(font_path,size)
            lines=_wrap_text(draw,text,font,W-170,max_lines=4)
            # The shared helper can clip excess lines; never silently truncate.
            if ''.join(lines)==text.replace('\n','') and len(lines)<=2:
                break
            size-=4
            if size<40:
                raise ValueError('封面文字无法完整排版')
        for line in lines:
            draw.text((W//2,y),line,font=font,anchor='mt',fill=fill,stroke_width=stroke,stroke_fill=outline)
            y+=size+28
    if footnote:
        draw.text((W-80,H-150),footnote,font=ImageFont.truetype(font_path,28),anchor='rs',fill='white',stroke_width=2,stroke_fill='black')
    image.save(output,'PNG')


def make_clip(source: str, frames: int, output: str, index: int | None):
    from stages import render as r
    if frames<1:
        raise ValueError('分镜帧数无效')
    if index is None:
        graph=f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1,format=yuv420p'
        args=[r.ff(),'-y','-loop','1','-framerate',str(FPS),'-i',source,'-vf',graph]
    else:
        progress=f'on/{max(1,frames-1)}'
        easing=f'(3*pow({progress},2)-2*pow({progress},3))'
        amount=easing if index%2==0 else f'(1-{easing})'
        graph=(f'scale={W*2}:{H*2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W*2}:{H*2},'
               f"zoompan=z='1+0.12*{amount}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={frames}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p")
        args=[r.ff(),'-y','-i',source,'-vf',graph]
    r._run_ffmpeg([*args,'-frames:v',str(frames),*r._encoder_args(intermediate=True),'-r',str(FPS),'-an',output],check=True,capture_output=True)


def run(stage: dict):
    from stages import render as r
    task_id=stage['task_id']
    params=stage.get('params') or {}
    started=time.monotonic()
    previous_deadline=r._ACTIVE_DEADLINE
    r._ACTIVE_DEADLINE=started+config.RENDER_TIMEOUT
    audio=None
    try:
        images=r._apply_image_replacements(task_id,r._load_json_artifact(task_id,'image_index') or [])
        subs=r._load_json_artifact(task_id,'subtitle') or {}
        audio_stage=db.get_client().table('stages').select('status,params,output_ref').eq('task_id',task_id).eq('kind','tts').single().execute().data or {}
        if (audio_stage.get('params') or {}).get('audio_source')=='external':
            row=db.get_client().table('external_narrations').select('state,audio_path,subtitle_path').eq('id',audio_stage['params']['external_id']).single().execute().data or {}
            if audio_stage.get('status')!='done' or row.get('state')!='approved' or row.get('audio_path')!=audio_stage.get('output_ref'):
                raise ValueError('外部配音尚未完成自动对齐')
            audio=storage.download_artifact(row['audio_path'])
            local=storage.download_artifact(row['subtitle_path'],'.json')
            try: subs=json.loads(Path(local).read_text(encoding='utf-8'))
            finally: Path(local).unlink(missing_ok=True)
        else:
            audio=r._load_audio(task_id)
        if not images or not audio:
            raise ValueError('缺少场景图片或配音')
        if any(image.get('cell_ratio')!='9:16' for image in images):
            raise ValueError('山河人文图片必须使用9:16模板')
        duration=float(subs.get('duration') or 0)
        cues=subs.get('segments') or []
        if duration<=COVER_SECONDS or not cues:
            raise ValueError('配音时长或字幕时间轴无效')
        timeline=r._build_timeline(images,cues,duration)
        r._validate_timeline(timeline,cues,duration)
        options=images[0].get('cover_options') or []
        defaults=options[0] if options else {'title':'山河人文','subtitle':''}
        saved=params.get('video_text') or {}
        title=str(saved.get('title',params.get('main_title') or defaults['title'])).strip()
        subtitle=str(saved.get('subtitle',params.get('subtitle') or defaults['subtitle'])).strip()
        footnote=str(saved.get('footnote',params.get('footnote','图片由AI生成'))).strip()
        phase={}
        with tempfile.TemporaryDirectory(prefix='scene-render-') as temp:
            temp=Path(temp)
            cover=storage.download_artifact(images[0]['cover_path'],'.png')
            try:
                make_cover(cover,str(temp/'cover.png'),title,subtitle)
                make_cover(cover,str(temp/'publication-cover.png'),title,subtitle,footnote)
            finally: Path(cover).unlink(missing_ok=True)
            make_clip(str(temp/'cover.png'),15,str(temp/'cover.mp4'),None)
            clips=[temp/'cover.mp4']
            total_frames=math.ceil(duration*FPS)
            for index,item in enumerate(timeline):
                frame_start=15 if index==0 else round(item['start']*FPS)
                frame_end=total_frames if index==len(timeline)-1 else round(item['end']*FPS)
                frames=frame_end-frame_start
                if frames<=0:
                    continue
                source=storage.download_artifact(item['path'],'.png')
                clip=temp/f'body_{index:03d}.mp4'
                try: make_clip(source,frames,str(clip),index)
                finally: Path(source).unlink(missing_ok=True)
                clips.append(clip)
            phase['picture_seconds']=round(time.monotonic()-started,3)
            (temp/'concat.txt').write_text(''.join(f"file '{path.as_posix()}'\n" for path in clips),encoding='utf-8')
            r._run_ffmpeg([r.ff(),'-y','-f','concat','-safe','0','-i',str(temp/'concat.txt'),'-c','copy',str(temp/'pictures.mp4')],check=True,capture_output=True)
            write_ass(cues,duration,footnote,str(temp/'subs.ass'))
            r._prepare_title_font('Microsoft YaHei',str(temp/'fonts'),use_configured=False)
            bgm,bgm_volume,narration_volume=r._load_bgm_config(task_id)
            args=[r.ff(),'-y','-i',str(temp/'pictures.mp4'),'-i',audio]
            if bgm:
                local=storage.download_artifact(bgm)
                shutil.move(local,temp/'music.mp3')
                args+=['-stream_loop','-1','-i',str(temp/'music.mp3')]
            target=r._storage_safe_video_bitrate(duration,max_bytes=storage.upload_limit_bytes())
            args+=['-filter_complex',r._audio_mix_filter(bool(bgm),bgm_volume,narration_volume,duration),
                   '-vf','ass=subs.ass:fontsdir=fonts',*r._encoder_args(target_kbps=target),'-map','0:v:0',
                   '-map','[audio]' if bgm else '[narration]','-c:a','aac','-b:a','64k','-t',str(duration),'-movflags','+faststart',str(temp/'final.mp4')]
            encoded_at=time.monotonic()
            r._run_ffmpeg(args,check=True,capture_output=True,cwd=str(temp))
            phase['text_audio_seconds']=round(time.monotonic()-encoded_at,3)
            if (temp/'final.mp4').stat().st_size>storage.upload_limit_bytes():
                raise ValueError('场景成片超过存储安全上限，旧成片已保留')
            rows=db.get_client().table('stages').select('kind,status,error').eq('task_id',task_id).order('seq').execute().data or []
            quality=r.inspect_render_quality(str(temp/'final.mp4'),r.ff(),stage_rows=rows,images=images,cues=cues,
                        timeline=timeline,tts_duration=duration,width=W,height=H,fps=FPS,intro_duration=0)
            prefix=f'{task_id}/renders/{uuid.uuid4()}'
            final_path=prefix+'/final.mp4'
            cover_path=prefix+'/cover.png'
            quality_path=prefix+'/quality-report.json'
            timeline_path=prefix+'/timeline.json'
            storage.upload(cover_path,str(temp/'publication-cover.png'),'image/png')
            storage.upload(final_path,str(temp/'final.mp4'),'video/mp4')
            storage.upload_bytes(quality_path,json.dumps(quality,ensure_ascii=False,indent=2).encode(),'application/json')
            storage.upload_bytes(timeline_path,json.dumps(timeline,ensure_ascii=False,indent=2).encode(),'application/json')
            storage.add_artifact(task_id,'render','publication_cover',cover_path,meta={'width':W,'height':H,'title':title,'subtitle':subtitle})
            storage.add_artifact(task_id,'render','quality_report',quality_path,meta={'status':quality['status'],**quality['summary'],**quality['metrics']})
            storage.add_artifact(task_id,'render','timeline',timeline_path,meta={'duration':duration,'version':3})
            storage.add_artifact(task_id,'render','final',final_path,meta={
                'production_template':'scene-v1','width':W,'height':H,'tts_duration':duration,'image_count':len(images),
                'cover_frames':15,'cover_duration':0.5,'intro_duration':0,'audio_offset_seconds':0,
                'cover':'independent_cover','publication_cover':cover_path,'title_visibility':'cover_only',
                'footnote_visibility':'full_video','text_layout':{'title':title,'subtitle':subtitle,'footnote':footnote},
                'motion':'alternating_zoom_in_out','zoom_amount':0.12,'layout':'scene_fullscreen',
                'quality_status':quality['status'],'quality_report':quality_path,'phase_seconds':phase,
                'processing_seconds':round(time.monotonic()-started,3),'file_size_bytes':(temp/'final.mp4').stat().st_size,
                'bgm_enabled':bool(bgm),'bgm_volume':bgm_volume if bgm else None,'narration_volume':narration_volume})
            if quality['status']=='failed':
                db.set_stage(stage['id'],'needs_review',output_ref=final_path,error='场景成片自动质检发现问题，请查看报告')
                return 'needs_review',final_path
            return 'done',final_path
    finally:
        r._ACTIVE_DEADLINE=previous_deadline
        if audio:
            Path(audio).unlink(missing_ok=True)
