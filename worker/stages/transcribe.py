"""② 逐字稿 transcribe：下载音频 → faster-whisper 出带词级时间戳的逐字稿 → 存产物。

- 词级时间戳（word_timestamps=True）供后续字幕对齐
- 模型只加载一次（module 级缓存）
- 产物：transcript.json（含 segments + words）
"""
from __future__ import annotations
import json
import os
import re
from functools import lru_cache

import config
import db
import storage


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


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel
    return WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE,
    )


def _find_audio(task_id: str) -> str | None:
    """找 ingest 产出的音频 artifact 的 storage_path。"""
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "audio")
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

    local = storage.download_artifact(audio_path, suffix=".mp3")
    try:
        segments, info = _model().transcribe(
            local,
            language="zh",
            word_timestamps=True,
            vad_filter=True,     # 去静音，减少幻听
        )
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

        transcript = {
            "language": info.language,
            "duration": round(info.duration, 3),
            "text": "".join(full_text).strip(),
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
        })
        _persist_book_signal(task_id, book_signal)
        return "done", sp
    finally:
        try:
            os.remove(local)
        except OSError:
            pass
