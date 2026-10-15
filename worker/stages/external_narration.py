"""External audio inspection, review and subtitle generation; never calls TTS."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import db
import storage
import imageio_ffmpeg
from external_alignment import align, comparable, differences, validate_cues


def _finish(stage: dict, state: str, review: dict, audio: str | None = None, subtitle: str | None = None):
    return db.retry(lambda: db.get_client().rpc('finish_external_narration', {
        'p_stage_id':stage['id'], 'p_job':stage['params']['external_job'],
        'p_state':state,'p_review':review,'p_audio':audio,'p_subtitle':subtitle,
    }).execute())


def run(stage: dict) -> tuple[str, None]:
    params = stage.get('params') or {}
    if not params.get('external_id'):
        _finish(stage,'waiting',{})
        return 'managed', None
    original = None
    previous: dict = {}
    row: dict = {}
    try:
        row = db.retry(lambda: db.get_client().table('external_narrations').select('*').eq('id',params['external_id']).eq('stage_id',stage['id']).single().execute()).data
        if not row:
            raise ValueError('配音版本不存在')
        text = row['subtitle_text']
        previous = row.get('review') or {}
        original = storage.download_artifact(row['original_path'], Path(row['original_path']).suffix)
        if Path(original).stat().st_size != row['size_bytes']:
            raise ValueError('实际文件大小与上传记录不一致')
        with open(original,'rb') as handle:
            header=handle.read(12)
        is_wav=header[:4] in (b'RIFF',b'RF64') and header[8:12]==b'WAVE'
        is_mp3=header[:3]==b'ID3' or (len(header)>1 and header[0]==255 and header[1]&224==224)
        if not (is_wav or is_mp3):
            raise ValueError('音频无法解码：文件内容不是 WAV 或 MP3')
        source_hash = hashlib.sha256(Path(original).read_bytes()).hexdigest()
        job_path = f"{stage['task_id']}/external/{row['id']}/{uuid.uuid4()}"
        with tempfile.TemporaryDirectory(prefix='external-narration-') as tmp:
            decoded = Path(tmp)/'narration.wav'
            # PCM avoids any re-encoding joins; original upload is retained.
            process = subprocess.run([
                imageio_ffmpeg.get_ffmpeg_exe(), '-v','error','-y','-i',original,
                '-map','0:a:0','-vn','-t','3601','-acodec','pcm_s16le',str(decoded),
            ],capture_output=True,timeout=300)
            if process.returncode:
                raise ValueError('音频无法解码，请上传有效 WAV 或 MP3')
            from stages.tts import _probe_audio_duration
            duration = _probe_audio_duration(str(decoded))
            if not 0.1 <= duration <= 3600:
                raise ValueError('配音时长须在 0.1 秒至 60 分钟之间')
            if previous.get('source_sha256') == source_hash and previous.get('words'):
                words=previous['words']
                recognized=previous['recognized_text']
            else:
                from stages.transcribe import _model
                segments, _info = _model().transcribe(str(decoded),language='zh',word_timestamps=True,vad_filter=True)
                words=[]
                recognized_parts=[]
                for segment in segments:
                    recognized_parts.append(segment.text)
                    words.extend({'word':w.word,'start':round(w.start,3),'end':round(w.end,3),
                                  'probability':round(w.probability,4)} for w in (segment.words or []))
                recognized=''.join(recognized_parts).strip()
            if not comparable(recognized):
                raise ValueError('未识别到可对齐的人声，请检查音频')
            cues,coverage=align(text,words,duration)
            manual=previous.get('requested_cues')
            if manual is not None:
                cues=validate_cues(text,manual,duration)
            ready=False
            if not any(c.get('needs_timing_review') for c in cues):
                try:
                    cues=validate_cues(text,cues,duration)
                    ready=True
                except (ValueError,TypeError):
                    pass
            audio_path=job_path+'/narration.wav'
            subtitle_path=job_path+'/subtitles.json'
            payload={'provider':'external','external_id':row['id'],'duration':duration,'text':text,
                     'narration_text':text,'segments':cues,'sentence_segments':words,'batches':[],
                     'input_format':'timeline_v3','subtitle_max_chars':14,'segment_count':len(cues),
                     'audio_path':audio_path,'alignment_ready':ready}
            storage.upload(audio_path,str(decoded),'audio/wav')
            storage.upload_bytes(subtitle_path,json.dumps(payload,ensure_ascii=False).encode(),'application/json')
        review={**payload,'source_sha256':source_hash,'recognized_text':recognized,'words':words,
                'script_text':row['script_text'],'subtitle_text':text,'coverage':coverage,
                'differences':differences(row['script_text'],recognized),
                'subtitle_differences':differences(text,recognized)}
        _finish(stage,'review',review,audio_path,subtitle_path)
    except Exception as exc:
        _finish(stage,'failed',{**previous,'error':str(exc)[:1000], 'alignment_ready':False},
                row.get('audio_path'),row.get('subtitle_path'))
    finally:
        if original:
            Path(original).unlink(missing_ok=True)
    # Completion is atomically recorded with a generation token by the RPC.
    return 'managed',None
