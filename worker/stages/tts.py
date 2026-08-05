"""⑤ 配音 tts：改写选中稿 → edge-tts 合成 → 词级时间戳 JSON + 音频。"""
from __future__ import annotations
import asyncio
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import config
import db
import storage
import imageio_ffmpeg

# 默认音色，可通过 env 覆盖
_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
_CONCURRENCY = max(1, int(os.environ.get("TTS_CONCURRENCY", "3")))
_TARGET_SEGMENT_CHARS = max(40, int(os.environ.get("TTS_SEGMENT_CHARS", "90")))


def _clean_tts_text(text: str) -> str:
    """Return plain narration, excluding screenplay and formatting instructions."""
    if not text:
        return ""
    source = str(text).strip()
    unfenced = re.sub(r"^```(?:json|text|markdown)?\s*|\s*```$", "", source, flags=re.I | re.S).strip()
    try:
        payload = json.loads(unfenced)
        if isinstance(payload, str):
            source = payload
        elif isinstance(payload, dict):
            for key in ("final_text", "text", "narration", "voiceover", "script", "content"):
                if str(payload.get(key) or "").strip():
                    source = str(payload[key])
                    break
    except (json.JSONDecodeError, TypeError, ValueError):
        source = unfenced

    lines: list[str] = []
    for raw in source.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("```") or re.fullmatch(r"[-_=*~#]{3,}", line):
            continue
        if re.match(r"^#{1,6}\s+", line):
            continue
        if re.fullmatch(r"(?:\[?\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:[-~]\s*\d{1,2}:\d{2}(?::\d{2})?)?\s*\]?)", line):
            continue
        line = re.sub(r"^\s*\[?\d{1,2}:\d{2}(?::\d{2})?\s*(?:[-~]\s*\d{1,2}:\d{2}(?::\d{2})?)?\]?\s*", "", line)
        narration = re.search(r"(?:旁白|画外音|口播|文案)\s*[:：]\s*(.+)$", line)
        if narration:
            line = narration.group(1).strip()
        elif re.match(r"^[【\[]?(?:画面|镜头|场景|时间|时间点|时长|字幕|转场|音效|配乐|分镜)[】\]]?\s*[:：-]", line):
            continue
        else:
            line = re.sub(r"^[【\[]?(?:正文|开头钩子|中间内容|结尾收束|结尾)[】\]]?\s*[:：-]\s*", "", line)
        line = re.sub(r"^(?:[-+*•]\s+|\d+[.、]\s*)", "", line)
        line = re.sub(r"^\s*(?:[-_=*~]){2,}\s*", "", line).strip()
        line = html.unescape(line)
        line = re.sub(r"</?(?:speak|voice)\b[^>]*>|<break\b[^>]*/?>", "", line, flags=re.I)
        line = re.sub(r"[*_`]+", "", line).strip()
        if line and not re.fullmatch(r"[\d\s:：,，.。-]+", line):
            lines.append(line)
    return "\n".join(lines).strip()


def _split_tts_segments(
    text: str,
    target_chars: int = _TARGET_SEGMENT_CHARS,
    min_chars: int = 55,
    max_chars: int = 105,
) -> list[str]:
    """Split without changing content, preferring natural punctuation near 26 seconds."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    boundaries = {match.end() for match in re.finditer(r"(?:……|[。！？!?；;]|\n)", text)}
    segments: list[str] = []
    start = 0
    while start < len(text):
        remaining = len(text) - start
        if remaining <= max_chars:
            segments.append(text[start:])
            break

        lower = min(len(text), start + min_chars)
        upper = min(len(text), start + max_chars)
        target = min(len(text), start + target_chars)
        candidates = [point for point in boundaries if lower <= point <= upper]
        cut = min(candidates, key=lambda point: (abs(point - target), point > target)) if candidates else upper
        segments.append(text[start:cut])
        start = cut
    return [segment for segment in segments if segment]


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
    if rw.get("final_text"):
        return str(rw["final_text"])
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


async def _synthesize_part(text: str, voice: str) -> tuple[bytes, list[dict]]:
    """Synthesize one plain-text part and return local timestamps."""
    import edge_tts
    fd_mp3, mp3_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd_mp3)
    segs: list[dict] = []

    try:
        # edge-tts builds and escapes its own SSML. Passing custom SSML here makes
        # tags such as <break> audible, so only plain narration is allowed.
        comm = edge_tts.Communicate(text, voice, boundary="SentenceBoundary")
        with open(mp3_path, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                    segs.append({
                        "text": chunk.get("text", ""),
                        "start": round(chunk["offset"] / 1e7, 3),
                        "end": round((chunk["offset"] + chunk["duration"]) / 1e7, 3),
                    })
        with open(mp3_path, "rb") as f:
            return f.read(), segs
    finally:
        try:
            os.remove(mp3_path)
        except OSError:
            pass


def _concat_mp3(parts: list[bytes]) -> bytes:
    if len(parts) == 1:
        return parts[0]
    tmpdir = tempfile.mkdtemp(prefix="tts_concat_")
    try:
        paths: list[Path] = []
        for index, data in enumerate(parts):
            path = Path(tmpdir) / f"part_{index:03d}.mp3"
            path.write_bytes(data)
            paths.append(path)
        manifest = Path(tmpdir) / "concat.txt"
        manifest.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in paths),
            encoding="utf-8",
        )
        output = Path(tmpdir) / "combined.mp3"
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-y",
                "-f", "concat", "-safe", "0", "-i", str(manifest),
                "-c", "copy", str(output),
            ],
            check=True,
            capture_output=True,
        )
        return output.read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


async def _synthesize(text: str, voice: str) -> tuple[bytes, list[dict]]:
    """Synthesize natural parts concurrently and merge audio/timestamps in order."""
    parts = _split_tts_segments(text)
    if not parts:
        return b"", []
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def synthesize_limited(part: str) -> tuple[bytes, list[dict]]:
        async with semaphore:
            return await _synthesize_part(part, voice)

    results = await asyncio.gather(*(synthesize_limited(part) for part in parts))
    merged_segments: list[dict] = []
    offset = 0.0
    for _audio, local_segments in results:
        for segment in local_segments:
            merged_segments.append({
                **segment,
                "start": round(float(segment.get("start", 0.0)) + offset, 3),
                "end": round(float(segment.get("end", 0.0)) + offset, 3),
            })
        if local_segments:
            offset += float(local_segments[-1].get("end", 0.0))
    return _concat_mp3([audio for audio, _segments in results]), merged_segments


def _get_cta(task_id: str) -> str | None:
    """从 book.json 读取 CTA 文案（book 阶段在 tts 之前完成）。"""
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "book")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    local = storage.download_artifact(res.data[0]["storage_path"], ".json")
    try:
        data = json.load(open(local, encoding="utf-8"))
        return data.get("cta_text") or None
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    rewrite_text = _get_chosen_text(task_id, stage)
    if not rewrite_text:
        db.set_stage(stage["id"], "failed",
                     error="未找到选定的改写稿（请先在改写阶段确认选择）")
        return "failed", None

    # 追加 CTA（book 阶段已在 tts 之前完成）
    rewrite_text = _clean_tts_text(rewrite_text)
    cta = _clean_tts_text(_get_cta(task_id) or "")
    text = rewrite_text + ("\n\n" + cta if cta else "")
    synthesis_batches = len(_split_tts_segments(text))

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
        "synthesis_batches": synthesis_batches,
        "input_format": "plain_text_v2",
    })

    # 上传字幕时间戳
    sp_subs = f"{task_id}/tts_subtitles.json"
    subs_data = json.dumps(
        {
            "voice": voice,
            "duration": duration,
            "segments": segs,
            "text": text,
            "narration_text": rewrite_text,
            "cta_text": cta,
            "input_format": "plain_text_v2",
            "synthesis_batches": synthesis_batches,
        },
        ensure_ascii=False, indent=2,
    ).encode("utf-8")
    storage.upload_bytes(sp_subs, subs_data, "application/json")
    storage.add_artifact(task_id, "tts", "subtitle", sp_subs, meta={
        "duration": duration,
        "segment_count": len(segs),
        "synthesis_batches": synthesis_batches,
        "input_format": "plain_text_v2",
    })

    return "done", sp_audio
