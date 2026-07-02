"""⑤ 配音 tts：改写选中稿 → edge-tts 合成 → 词级时间戳 JSON + 音频。"""
from __future__ import annotations
import asyncio
import json
import os
import re
import tempfile

import config
import db
import storage

# 默认音色，可通过 env 覆盖
_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")

# 标点停顿规则（长模式优先）
_PAUSE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'……'),    '<break time="900ms"/>'),
    (re.compile(r'\.{4,}'), '<break time="900ms"/>'),
    (re.compile(r'——'),    '<break time="700ms"/>'),
    (re.compile(r'--'),    '<break time="700ms"/>'),
    (re.compile(r'[。]'),  '<break time="800ms"/>'),
    (re.compile(r'[！!]'), '<break time="900ms"/>'),
    (re.compile(r'[？?]'), '<break time="900ms"/>'),
    (re.compile(r'[；;]'), '<break time="450ms"/>'),
    (re.compile(r'[：:]'), '<break time="450ms"/>'),
    (re.compile(r'[，,]'), '<break time="300ms"/>'),
    (re.compile(r'"'),     '"<break time="150ms"/>'),
    (re.compile(r'"'),     '<break time="150ms"/>"'),
]


def _add_pauses(text: str) -> str:
    for pat, repl in _PAUSE_RULES:
        text = pat.sub(repl, text)
    return text


def _find_rewrite(task_id: str) -> str | None:
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "rewrite")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["storage_path"] if res.data else None


def _get_chosen_text(task_id: str, stage: dict) -> str | None:
    rw_path = _find_rewrite(task_id)
    if not rw_path:
        return None
    local = storage.download_artifact(rw_path, ".json")
    try:
        rw = json.load(open(local, encoding="utf-8"))
    finally:
        try:
            os.remove(local)
        except OSError:
            pass
    params = stage.get("params") or {}
    raw_idx = params.get("chosen_index")
    if raw_idx is None:
        raw_idx = rw.get("chosen")
    if raw_idx is None:
        # chosen_index is written to the rewrite stage's params by the frontend, not the tts stage
        res = (
            db.get_client().table("stages").select("params")
            .eq("task_id", task_id).eq("kind", "rewrite")
            .limit(1).execute()
        )
        if res.data:
            raw_idx = (res.data[0].get("params") or {}).get("chosen_index")
    candidates = rw.get("candidates", [])
    if raw_idx is None or not candidates:
        return None
    return candidates[int(raw_idx)] if int(raw_idx) < len(candidates) else None


async def _synthesize(text: str, voice: str) -> tuple[bytes, list[dict]]:
    """返回 (mp3_bytes, segments)。segments 是句级时间戳列表(SentenceBoundary)。

    edge-tts 7.x 中文只给 SentenceBoundary，不给 WordBoundary。
    句级时间戳对 V1 字幕对齐(整句显示)已完全够用。
    """
    import edge_tts
    fd_mp3, mp3_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd_mp3)
    segs: list[dict] = []

    comm = edge_tts.Communicate(_add_pauses(text), voice)
    with open(mp3_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                segs.append({
                    "text":  chunk.get("text", ""),
                    "start": round(chunk["offset"] / 1e7, 3),         # 100ns → s
                    "end":   round((chunk["offset"] + chunk["duration"]) / 1e7, 3),
                })
    with open(mp3_path, "rb") as f:
        audio = f.read()
    os.remove(mp3_path)
    return audio, segs


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    text = _get_chosen_text(task_id, stage)
    if not text:
        db.set_stage(stage["id"], "failed",
                     error="未找到选定的改写稿（请先在改写阶段确认选择）")
        return "failed", None

    voice = stage.get("params", {}).get("voice") or _VOICE
    audio, segs = asyncio.run(_synthesize(text, voice))

    duration = segs[-1]["end"] if segs else 0.0

    # 上传音频
    sp_audio = f"{task_id}/tts.mp3"
    storage.upload_bytes(sp_audio, audio, "audio/mpeg")
    storage.add_artifact(task_id, "tts", "audio", sp_audio, meta={
        "voice": voice,
        "duration": duration,
        "segment_count": len(segs),
    })

    # 上传字幕时间戳
    sp_subs = f"{task_id}/tts_subtitles.json"
    subs_data = json.dumps(
        {"voice": voice, "duration": duration, "segments": segs, "text": text},
        ensure_ascii=False, indent=2,
    ).encode("utf-8")
    storage.upload_bytes(sp_subs, subs_data, "application/json")
    storage.add_artifact(task_id, "tts", "subtitle", sp_subs, meta={
        "duration": duration,
        "segment_count": len(segs),
    })

    return "done", sp_audio
