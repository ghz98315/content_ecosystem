"""② 逐字稿 transcribe：下载音频 → faster-whisper 出带词级时间戳的逐字稿 → 存产物。

- 词级时间戳（word_timestamps=True）供后续字幕对齐
- 模型只加载一次（module 级缓存）
- 产物：transcript.json（含 segments + words）
"""
from __future__ import annotations
import json
import os
import re
import hashlib
import subprocess
import time
from pathlib import Path
from functools import lru_cache

import config
import db
import storage


def _content_without_punctuation(text: str) -> str:
    return re.sub(r"[\s\.,，。！？!?；;：:、（）()【】\[\]「」『』“”\"'‘’…—\-_/\\·~@#$%^&*+=<>|`]", "", text or "")


def _punctuate_for_reading(text: str) -> str:
    """Create a display-only reading version without changing ASR source text."""
    source = (text or "").strip()
    if not source:
        return ""
    prompt = (
        "你是中文逐字稿排版助手。只允许按语义补充中文标点和自然分段，"
        "不得增删、替换、纠正、改写任何原文汉字、数字、英文或词语。"
        "不要标题、说明、Markdown 或 JSON；只输出排版后的逐字稿。\n\n原始逐字稿：\n"
        + source
    )
    try:
        response = config.clean_client().chat.completions.create(
            model=config.CLEAN_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        result = (response.choices[0].message.content or "").strip()
        if result and _content_without_punctuation(result) == _content_without_punctuation(source):
            return result
        return source
    except Exception:
        # Readability enhancement must never block the actual transcription artifact.
        return source


def _infer_book_signal(text: str) -> dict:
    """Extract only explicit book-title signals; never invent a title."""
    source = text or ""
    bracketed = re.search(r"《([^》]{2,80})》", source)
    if bracketed:
        return {"title": bracketed.group(1).strip(), "confidence": "medium", "evidence": "transcript_book_brackets"}
    labeled = re.search(r"(?:书名|这本书|本书)\s*(?:是|为|叫|：|:)\s*([^\n，。！？]{2,80})", source)
    if labeled:
        return {"title": labeled.group(1).strip("《》 \t"), "confidence": "low", "evidence": "transcript_title_label"}
    return {"title": None, "confidence": "low", "evidence": "no_explicit_title_signal"}


def _persist_book_signal(task_id: str, signal: dict) -> None:
    """Best-effort persistence; missing migration must not fail transcription."""
    try:
        db.get_client().table("task_book_signals").upsert({
            "task_id": task_id,
            "detected_title": signal.get("title"),
            "confidence": signal.get("confidence") or "low",
            "evidence": signal.get("evidence"),
            "source_stage": "transcribe",
        }, on_conflict="task_id").execute()
    except Exception:
        pass


@lru_cache(maxsize=2)
def _model(device=None, compute=None):
    from faster_whisper import WhisperModel
    return WhisperModel(
        config.WHISPER_MODEL,
        device=device or config.WHISPER_DEVICE,
        compute_type=compute or config.WHISPER_COMPUTE,
    )


def _transcribe_media(path: str):
    """Decode through the existing ffmpeg runtime, avoiding PyAV ABI conflicts."""
    import numpy as np
    import imageio_ffmpeg
    started = time.monotonic()
    decoded = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', path,
        '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-',
    ], check=True, capture_output=True, timeout=300)
    audio = np.frombuffer(decoded.stdout, dtype=np.float32)
    if not audio.size:
        raise ValueError('音频中没有可识别的采样')
    decode_seconds = time.monotonic() - started
    loaded = time.monotonic()
    device, compute = config.WHISPER_DEVICE, config.WHISPER_COMPUTE
    fallback_reason = None
    recognized = loaded
    try:
        model = _model()
        model_seconds = time.monotonic() - loaded
        recognized = time.monotonic()
        segments, info = model.transcribe(audio, language='zh', word_timestamps=True, vad_filter=True)
        segments = list(segments)  # Recognition is lazy; time it only after consumption.
    except RuntimeError as exc:
        if device != 'cuda' or not any(term in str(exc).lower() for term in ('cuda', 'cublas', 'cudnn', 'out of memory', 'gpu')):
            raise
        fallback_reason = str(exc)[:180]
        print('  [asr] 显卡暂不可用，自动回退 CPU：' + fallback_reason, flush=True)
        model = None
        _model.cache_clear()
        device, compute = 'cpu', 'int8'
        model = _model(device, compute)
        model_seconds = time.monotonic() - loaded
        recognized = time.monotonic()
        segments, info = model.transcribe(audio, language='zh', word_timestamps=True, vad_filter=True)
        segments = list(segments)
    metrics = {'decode_seconds': round(decode_seconds, 3), 'model_seconds': round(model_seconds, 3),
               'recognition_seconds': round(time.monotonic() - recognized, 3),
               'device': device, 'compute': compute, 'fallback_reason': fallback_reason}
    print('  [asr] ' + json.dumps(metrics, ensure_ascii=False), flush=True)
    return segments, info, metrics


def _find_audio(task_id: str) -> str | None:
    """找 ingest 产出的音频 artifact 的 storage_path。"""
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "audio")
        .eq("stage_kind", "ingest")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["storage_path"] if res.data else None


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    audio_path = _find_audio(task_id)
    if not audio_path:
        db.set_stage(stage["id"], "failed", error="未找到音频产物（ingest 未完成？）")
        return "failed", None

    started = time.monotonic()
    local = storage.download_artifact(audio_path, suffix=".mp3")
    download_seconds = time.monotonic() - started
    try:
        source_hash = hashlib.sha256(Path(local).read_bytes()).hexdigest()
        model_file = Path(config.WHISPER_MODEL) / 'model.bin'
        signature = hashlib.sha256(json.dumps({
            'model': config.WHISPER_MODEL,
            'model_revision': model_file.stat().st_mtime_ns if model_file.exists() else None,
            'device': config.WHISPER_DEVICE, 'compute': config.WHISPER_COMPUTE,
            'policy': 'zh-word-times-vad-pcm-v1',
        }, sort_keys=True).encode()).hexdigest()
        if not (stage.get('params') or {}).get('force_transcribe'):
            try:
                cached = db.get_client().table('artifacts').select('storage_path').eq('task_id', task_id).eq('stage_kind', 'transcribe').eq('type', 'transcript').eq('meta->>source_sha256', source_hash).eq('meta->>asr_signature', signature).limit(1).execute().data
                if cached:
                    # Confirm the cached object still exists before reusing its ref.
                    probe = storage.download_artifact(cached[0]['storage_path'], '.json')
                    try:
                        payload = json.loads(Path(probe).read_text(encoding='utf-8'))
                        if payload.get('text') and payload.get('segments'):
                            print('  [asr] 同一任务、音频和配置命中已有逐字稿', flush=True)
                            return 'done', cached[0]['storage_path']
                    finally:
                        Path(probe).unlink(missing_ok=True)
            except Exception:
                pass
        segments, info, metrics = _transcribe_media(local)
        seg_list = []
        full_text = []
        for s in segments:
            words = [
                {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
                for w in (s.words or [])
            ]
            seg_list.append({
                "id": s.id,
                "start": round(s.start, 3),
                "end": round(s.end, 3),
                "text": s.text,
                "words": words,
            })
            full_text.append(s.text)

        raw_text = "".join(full_text).strip()
        punctuate_started = time.monotonic()
        reading_text = _punctuate_for_reading(raw_text)
        metrics.update(download_seconds=round(download_seconds, 3), punctuation_seconds=round(time.monotonic() - punctuate_started, 3))
        transcript = {
            "language": info.language,
            "duration": round(info.duration, 3),
            "text": raw_text,
            "reading_text": reading_text,
            "segments": seg_list,
        }
        data = json.dumps(transcript, ensure_ascii=False, indent=2).encode("utf-8")
        sp = f"{task_id}/transcript.json"
        storage.upload_bytes(sp, data, "application/json")
        book_signal = _infer_book_signal(transcript["text"])
        storage.add_artifact(task_id, "transcribe", "transcript", sp, meta={
            "language": info.language,
            "duration": round(info.duration, 3),
            "segment_count": len(seg_list),
            "char_count": len(transcript["text"]),
            "book_signal": book_signal,
            "source_sha256": source_hash,
            "asr_signature": signature,
            "timings": metrics,
        })
        _persist_book_signal(task_id, book_signal)
        return "done", sp
    finally:
        try:
            os.remove(local)
        except OSError:
            pass
