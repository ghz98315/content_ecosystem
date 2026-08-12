"""⑤ 配音 tts：改写选中稿 → edge-tts 合成 → 词级时间戳 JSON + 音频。"""
from __future__ import annotations
import asyncio
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
from narration import clean_tts_text, normalize_tts_numbers, split_semantic_units, visible_len
from tts_providers import get_tts_provider

# 默认音色，可通过 env 覆盖
_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
_CONCURRENCY = max(1, int(os.environ.get("TTS_CONCURRENCY", "3")))
_TARGET_SEGMENT_CHARS = max(40, int(os.environ.get("TTS_SEGMENT_CHARS", "90")))
_PART_TIMEOUT = max(15.0, float(os.environ.get("TTS_PART_TIMEOUT", "75")))
_PART_ATTEMPTS = max(1, int(os.environ.get("TTS_PART_ATTEMPTS", "3")))


_clean_tts_text = clean_tts_text


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


def _probe_audio_duration(path: str) -> float:
    """Measure decoded audio duration; TTS boundary events omit trailing silence."""
    result = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-i", path,
            "-map", "0:a:0", "-f", "null", "-", "-progress", "pipe:1", "-nostats",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    values = re.findall(r"out_time_us=(\d+)", result.stdout)
    if values:
        return round(int(values[-1]) / 1_000_000, 3)
    values = re.findall(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)", result.stdout)
    if values:
        hours, minutes, seconds = values[-1]
        return round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)
    raise ValueError("无法读取 TTS 分段音频时长")


async def _synthesize_part(text: str, voice: str) -> tuple[bytes, list[dict], float]:
    """Synthesize one part through the selected provider boundary."""
    return await get_tts_provider(config.TTS_PROVIDER).synthesize(text, voice)


async def _synthesize_part_via_provider(text: str, voice: str, provider: str | None = None, model: str | None = None) -> tuple[bytes, list[dict], float]:
    """Provider-aware boundary kept separate so older test doubles remain valid."""
    kwargs = {"model": model} if model else {}
    return await get_tts_provider(provider or config.TTS_PROVIDER, **kwargs).synthesize(text, voice)


async def _synthesize_part_with_retry(text: str, voice: str, provider: str | None = None, model: str | None = None) -> tuple[bytes, list[dict], float]:
    """Bound each provider request so one stalled segment cannot block the task."""
    last_error: Exception | None = None
    for attempt in range(_PART_ATTEMPTS):
        try:
            runner = _synthesize_part if provider in (None, "", config.TTS_PROVIDER) and not model else _synthesize_part_via_provider
            return await asyncio.wait_for(runner(text, voice) if runner is _synthesize_part else runner(text, voice, provider, model), timeout=_PART_TIMEOUT)
        except Exception as exc:  # edge-tts exposes several transport exception types
            last_error = exc
            if attempt == _PART_ATTEMPTS - 1:
                break
            await asyncio.sleep(min(6.0, 1.5 * (2 ** attempt)))
    preview = re.sub(r"\s+", "", text)[:24]
    raise RuntimeError(
        f"TTS 分段合成失败（{_PART_ATTEMPTS} 次尝试，文本：{preview}）：{last_error}"
    ) from last_error


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
        output = Path(tmpdir) / "combined.mp3"
        filters = "".join(f"[{index}:a]" for index in range(len(paths)))
        filters += f"concat=n={len(paths)}:v=0:a=1[a]"
        inputs: list[str] = []
        for path in paths:
            inputs.extend(["-i", str(path)])
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-y",
                *inputs, "-filter_complex", filters, "-map", "[a]",
                "-c:a", "libmp3lame", "-b:a", "96k", str(output),
            ],
            check=True,
            capture_output=True,
        )
        return output.read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _segment_char_ranges(part: str, segments: list[dict], base: int) -> list[dict]:
    """Align provider sentence boundaries to visible-character offsets."""
    compact = re.sub(r"\s+", "", part)
    cursor = 0
    aligned: list[dict] = []
    exact = True
    for segment in segments:
        needle = re.sub(r"\s+", "", str(segment.get("text", "")))
        found = compact.find(needle, cursor) if needle else cursor
        if found < 0:
            exact = False
            break
        aligned.append({**segment, "char_start": base + found, "char_end": base + found + len(needle)})
        cursor = found + len(needle)
    if exact and aligned:
        return aligned

    total = max(1, visible_len(part))
    weights = [max(1, visible_len(str(item.get("text", "")))) for item in segments]
    weight_total = sum(weights) or 1
    used = 0
    aligned = []
    for index, (segment, weight) in enumerate(zip(segments, weights)):
        start = round(total * used / weight_total)
        used += weight
        end = total if index == len(segments) - 1 else round(total * used / weight_total)
        aligned.append({**segment, "char_start": base + start, "char_end": base + max(start + 1, end)})
    return aligned


def _time_at_char(position: int, anchors: list[dict], total_chars: int, duration: float) -> float:
    if not anchors or total_chars <= 0:
        return duration * max(0, min(total_chars, position)) / max(1, total_chars)
    previous_char, previous_time = 0, 0.0
    for anchor in anchors:
        start_char = int(anchor.get("char_start", previous_char))
        end_char = max(start_char + 1, int(anchor.get("char_end", start_char + 1)))
        start_time = float(anchor.get("start", previous_time))
        end_time = max(start_time, float(anchor.get("end", start_time)))
        if position < start_char:
            span = max(1, start_char - previous_char)
            return previous_time + (start_time - previous_time) * (position - previous_char) / span
        if position <= end_char:
            return start_time + (end_time - start_time) * (position - start_char) / (end_char - start_char)
        previous_char, previous_time = end_char, end_time
    span = max(1, total_chars - previous_char)
    return previous_time + (duration - previous_time) * (position - previous_char) / span


def _book_title(book_name: str) -> str:
    return str(book_name or "").strip().strip("《》").strip()


def _format_book_title(text: str, book_name: str) -> str:
    title = _book_title(book_name)
    return text.replace(title, f"《{title}》") if title else text


def _build_subtitle_cues(
    text: str,
    anchors: list[dict],
    duration: float,
    max_chars: int = 12,
    book_name: str = "",
) -> list[dict]:
    title = _book_title(book_name)
    units = split_semantic_units(
        text,
        max_chars=max_chars,
        protected_terms=(title,) if title else (),
    )
    total_chars = visible_len(text)
    cues: list[dict] = []
    for unit in units:
        start = max(0.0, _time_at_char(unit["char_start"], anchors, total_chars, duration))
        boundary_end = min(duration, _time_at_char(unit["char_end"], anchors, total_chars, duration))
        if cues:
            start = max(start, float(cues[-1]["end"]))
        pause_after = float(unit.get("pause_after", 0.0))
        end = max(start + 0.08, boundary_end - pause_after)
        end = max(start + 0.08, end)
        if end > duration:
            end = duration
            start = max(0.0, end - 0.08)
            if cues:
                start = max(start, float(cues[-1]["end"]))
        cues.append({
            **unit,
            "text": _format_book_title(str(unit["text"]), title),
            "start": round(start, 3),
            "end": round(end, 3),
        })
    return cues


async def _synthesize_detailed(text: str, voice: str, provider: str | None = None, model: str | None = None) -> tuple[bytes, list[dict], list[dict]]:
    """Synthesize natural batches and retain each batch for UI and alignment."""
    parts = _split_tts_segments(text)
    spoken_parts = [normalize_tts_numbers(part) for part in parts]
    if not parts:
        return b"", [], []
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def synthesize_limited(part: str, spoken_part: str):
        async with semaphore:
            return await _synthesize_part_with_retry(spoken_part, voice, provider, model)

    results = await asyncio.gather(*(synthesize_limited(part, spoken) for part, spoken in zip(parts, spoken_parts)))
    merged_segments: list[dict] = []
    batches: list[dict] = []
    offset = 0.0
    char_offset = 0
    audio_parts: list[bytes] = []
    for index, (part, result) in enumerate(zip(parts, results)):
        if len(result) == 2:  # Backward-compatible test doubles.
            part_audio, local_segments = result
            part_duration = float(local_segments[-1].get("end", 0.0)) if local_segments else 0.0
        else:
            part_audio, local_segments, part_duration = result
        part_duration = max(float(part_duration), float(local_segments[-1].get("end", 0.0)) if local_segments else 0.0)
        ranged_segments = _segment_char_ranges(part, local_segments, char_offset)
        for segment in ranged_segments:
            merged_segments.append({
                **segment,
                "start": round(float(segment.get("start", 0.0)) + offset, 3),
                "end": round(float(segment.get("end", 0.0)) + offset, 3),
            })
        part_chars = visible_len(part)
        batches.append({
            "index": index,
            "text": part,
            "duration": round(part_duration, 3),
            "start": round(offset, 3),
            "end": round(offset + part_duration, 3),
            "char_start": char_offset,
            "char_end": char_offset + part_chars,
            "audio": part_audio,
        })
        audio_parts.append(part_audio)
        offset += part_duration
        char_offset += part_chars
    return _concat_mp3(audio_parts), merged_segments, batches


async def _synthesize(text: str, voice: str) -> tuple[bytes, list[dict]]:
    """Compatibility wrapper used by focused tests and existing callers."""
    audio, segments, _batches = await _synthesize_detailed(text, voice)
    return audio, segments


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


def _get_book_name(task_id: str) -> str:
    result = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "book")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return ""
    local = storage.download_artifact(result.data[0]["storage_path"], ".json")
    try:
        with open(local, encoding="utf-8") as handle:
            data = json.load(handle)
        return str(data.get("book_name") or "") if isinstance(data, dict) else ""
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
    book_name = _get_book_name(task_id)
    text = rewrite_text + ("\n\n" + cta if cta else "")
    tts_params = stage.get("params", {}) or {}
    provider = tts_params.get("provider") or config.TTS_PROVIDER
    voice = tts_params.get("voice") or (config.COSYVOICE2_VOICE if provider in {"cosyvoice2", "cosyvoice"} else _VOICE)
    model = tts_params.get("model") or None
    audio, sentence_segments, batches = asyncio.run(_synthesize_detailed(text, voice, provider, model))
    duration = round(sum(float(batch["duration"]) for batch in batches), 3)
    cues = _build_subtitle_cues(
        text,
        sentence_segments,
        duration,
        max_chars=14,
        book_name=book_name,
    )

    batch_data: list[dict] = []
    for batch in batches:
        batch_path = f"{task_id}/tts_parts/part_{batch['index']:03d}.mp3"
        storage.upload_bytes(batch_path, batch.pop("audio"), "audio/mpeg")
        storage.add_artifact(task_id, "tts", "audio_part", batch_path, meta={
            "index": batch["index"], "duration": batch["duration"], "voice": voice,
        })
        batch_data.append({**batch, "path": batch_path, "status": "done"})

    # 上传音频
    sp_audio = f"{task_id}/tts.mp3"
    storage.upload_bytes(sp_audio, audio, "audio/mpeg")
    storage.add_artifact(task_id, "tts", "audio", sp_audio, meta={
        "provider": provider,
        "model": model,
        "voice": voice,
        "duration": duration,
        "segment_count": len(cues),
        "synthesis_batches": len(batch_data),
        "input_format": "timeline_v3",
    })

    # 上传字幕时间戳
    sp_subs = f"{task_id}/tts_subtitles.json"
    subs_data = json.dumps(
        {
            "provider": provider,
            "voice": voice,
            "duration": duration,
            "segments": cues,
            "sentence_segments": sentence_segments,
            "batches": batch_data,
            "text": text,
            "narration_text": rewrite_text,
            "cta_text": cta,
            "input_format": "timeline_v3",
            "synthesis_batches": len(batch_data),
            "subtitle_max_chars": 14,
            "subtitle_format": "semantic_words_v2",
            "subtitle_segmenter": "jieba_compound_dp_v1",
            "pause_profile": "promote_tts_pause_v1",
        },
        ensure_ascii=False, indent=2,
    ).encode("utf-8")
    storage.upload_bytes(sp_subs, subs_data, "application/json")
    storage.add_artifact(task_id, "tts", "subtitle", sp_subs, meta={
        "duration": duration,
        "segment_count": len(cues),
        "synthesis_batches": len(batch_data),
        "input_format": "timeline_v3",
        "subtitle_max_chars": 14,
        "subtitle_format": "semantic_words_v2",
        "subtitle_segmenter": "jieba_compound_dp_v1",
        "pause_profile": "promote_tts_pause_v1",
    })

    return "done", sp_audio
