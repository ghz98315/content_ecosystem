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
import jieba
from narration import clean_tts_text, normalize_tts_numbers, split_semantic_units, visible_len
from tts_providers import get_tts_provider

# 默认音色，可通过 env 覆盖
_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
_CONCURRENCY = max(1, int(os.environ.get("TTS_CONCURRENCY", "3")))
_COSYVOICE_CONCURRENCY = max(1, int(os.environ.get("COSYVOICE_TTS_CONCURRENCY", "1")))
_COSYVOICE_REQUEST_GAP = max(0.0, float(os.environ.get("COSYVOICE_TTS_REQUEST_GAP", "1.2")))
_TARGET_SEGMENT_CHARS = max(40, int(os.environ.get("TTS_SEGMENT_CHARS", "90")))
_PART_TIMEOUT = max(15.0, float(os.environ.get("TTS_PART_TIMEOUT", "75")))
_PART_ATTEMPTS = max(1, int(os.environ.get("TTS_PART_ATTEMPTS", "3")))
_INDEXTTS_TARGET_SEGMENT_CHARS = max(100, int(os.environ.get("INDEXTTS25_SEGMENT_CHARS", "220")))
_INDEXTTS_MAX_SEGMENT_CHARS = max(
    _INDEXTTS_TARGET_SEGMENT_CHARS,
    int(os.environ.get("INDEXTTS25_MAX_SEGMENT_CHARS", "280")),
)


_clean_tts_text = clean_tts_text
_COSY_WARM_NARRATIVE = "cosy_warm_narrative_v3"
_NARRATION_PAUSES = (
    (r"(……|\.\.\.)\s*", "900ms"), (r"(——|—)\s*", "700ms"),
    (r"([，、,])\s*", "300ms"), (r"([；：;:])\s*", "450ms"),
    (r"([。\.])\s*", "800ms"), (r"([！？!?])\s*", "900ms"),
    (r'([“”"‘’\'])', "150ms"),
)
_DIALOGUE_PAUSES = (
    (r"(……|\.\.\.)\s*", "450ms"), (r"(——|—)\s*", "250ms"),
    (r"([，、,])\s*", "160ms"), (r"([；：;:])\s*", "220ms"),
    (r"([。\.])\s*", "380ms"), (r"([！？!?])\s*", "420ms"),
)


def _cosyvoice_ssml(text: str, position: str, speaker: str | None = None) -> str:
    """Apply semantic and speaker-specific delivery without changing the spoken text."""
    plain_text = text.strip()
    tone = "plain"
    if re.search(r"(警惕|风险|危险|伤害|别再|千万|不要|当心|后果|代价)", plain_text):
        tone = "alert"
    elif re.search(r"(放下|释然|安心|慢一点|别着急|照顾好自己|不必|温柔|陪伴)", plain_text):
        tone = "comfort"
    elif re.search(r"(好消息|值得|终于|做到|改变|希望|收获|恭喜|可以)", plain_text):
        tone = "affirm"
    is_host = speaker == "主持人"
    host_presets = {
        "hook": ("1.03", "1.12", "56"),
        "alert": ("1.00", "1.03", "54"),
        "comfort": ("0.98", "1.05", "53"),
        "affirm": ("1.04", "1.09", "55"),
        "plain": ("1.02", "1.06", "54"),
        "close": ("0.98", "1.04", "53"),
    }
    guest_presets = {
        "hook": ("0.99", "1.05", "55"),
        "alert": ("0.96", "0.96", "53"),
        "comfort": ("0.94", "1.00", "52"),
        "affirm": ("0.99", "1.05", "54"),
        "plain": ("0.98", "1.01", "53"),
        "close": ("0.95", "1.01", "52"),
    }
    profile = "hook" if position == "hook" else "close" if position == "close" else tone
    presets = host_presets if is_host else guest_presets if speaker == "嘉宾" else {
        "hook": ("0.99", "1.06", "55"), "alert": ("0.98", "0.97", "53"),
        "comfort": ("0.96", "1.01", "51"), "affirm": ("1.01", "1.04", "54"),
        "plain": ("1.00", "1.00", "52"), "close": ("0.97", "1.01", "51"),
    }
    rate, pitch, volume = presets[profile]
    # Match the approved pause profile. Do not add mechanical pauses before
    # transition words: punctuation and the role-specific prosody already
    # provide the needed phrasing.
    markers: list[tuple[str, str]] = []

    def add_pause(match: re.Match[str], duration: str) -> str:
        marker = f"@@COSY_PAUSE_{len(markers)}@@"
        markers.append((marker, f'<break time="{duration}"/>'))
        # Do not retain punctuation in the SSML input. CosyVoice otherwise
        # applies its own punctuation pause before our explicit break, making
        # the audible stop longer than the approved duration.
        return marker

    spoken = text.strip()
    pause_profile = _DIALOGUE_PAUSES if speaker else _NARRATION_PAUSES
    for pattern, duration in pause_profile:
        spoken = re.sub(pattern, lambda match, d=duration: add_pause(match, d), spoken)
    escaped = html.escape(spoken, quote=False)
    for marker, tag in markers:
        escaped = escaped.replace(marker, tag)
    return f'<speak rate="{rate}" pitch="{pitch}" volume="{volume}">{escaped}</speak>'


def _split_tts_segments(
    text: str,
    target_chars: int = _TARGET_SEGMENT_CHARS,
    min_chars: int = 55,
    max_chars: int = 105,
    protected_terms: tuple[str, ...] = (),
) -> list[str]:
    """Split without changing content or cutting protected terms and Jieba words."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    protected_spans: list[tuple[int, int]] = []
    protected = {term.strip() for term in protected_terms if term and term.strip()}
    protected.update(
        match.group(1).strip()
        for match in re.finditer(r"《([^》]+)》", text)
        if match.group(1).strip()
    )
    for term in protected:
        cursor = 0
        while True:
            found = text.find(term, cursor)
            if found < 0:
                break
            protected_spans.append((found, found + len(term)))
            cursor = found + len(term)

    def allowed(point: int) -> bool:
        return not any(start < point < end for start, end in protected_spans)

    strong = {
        match.end() for match in re.finditer(r"(?:……|[。！？!?；;]|\n)", text)
        if allowed(match.end())
    }
    soft = {
        match.end() for match in re.finditer(r"[，、,：:]|\s+", text)
        if allowed(match.end())
    }
    word = {
        end for _token, _start, end in jieba.tokenize(text)
        if 0 < end < len(text) and allowed(end)
    }
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
        candidates = [point for point in strong if lower <= point <= upper]
        if not candidates:
            candidates = [point for point in soft if lower <= point <= upper]
        if not candidates:
            candidates = [point for point in word if lower <= point <= upper]
        if candidates:
            cut = min(candidates, key=lambda point: (abs(point - target), point > target))
        else:
            cut = upper
            containing = [end for begin, end in protected_spans if begin < cut < end]
            if containing:
                cut = max(containing)
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


def _get_final_delivery_plan(task_id: str) -> list[dict] | None:
    """Load a reviewed dialogue direction plan when it still belongs to final text."""
    rw_path = _find_rewrite(task_id)
    if not rw_path:
        return None
    local = storage.download_artifact(rw_path, ".json")
    try:
        with open(local, encoding="utf-8") as handle:
            payload = json.load(handle)
        plan = payload.get("final_delivery_plan") if isinstance(payload, dict) else None
        return plan if isinstance(plan, list) else None
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


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


async def _synthesize_part(text: str, voice: str, instruction: str | None = None) -> tuple[bytes, list[dict], float]:
    """Synthesize one part through the selected provider boundary."""
    client = get_tts_provider(config.TTS_PROVIDER)
    return await (client.synthesize(text, voice, instruction) if instruction else client.synthesize(text, voice))


async def _synthesize_part_via_provider(text: str, voice: str, provider: str | None = None, model: str | None = None, instruction: str | None = None, provider_options: dict | None = None) -> tuple[bytes, list[dict], float]:
    """Provider-aware boundary kept separate so older test doubles remain valid."""
    kwargs = {"model": model} if model else {}
    client = get_tts_provider(provider or config.TTS_PROVIDER, **kwargs)
    if provider_options:
        return await client.synthesize(text, voice, instruction, provider_options)
    return await (client.synthesize(text, voice, instruction) if instruction else client.synthesize(text, voice))


async def _synthesize_part_with_retry(text: str, voice: str, provider: str | None = None, model: str | None = None, instruction: str | None = None, provider_options: dict | None = None) -> tuple[bytes, list[dict], float]:
    """Bound each provider request so one stalled segment cannot block the task."""
    last_error: Exception | None = None
    for attempt in range(_PART_ATTEMPTS):
        try:
            runner = _synthesize_part if provider in (None, "", config.TTS_PROVIDER) and not model and not provider_options else _synthesize_part_via_provider
            call = (
                runner(text, voice, instruction) if instruction else runner(text, voice)
            ) if runner is _synthesize_part else (
                runner(text, voice, provider, model, instruction, provider_options)
            )
            return await asyncio.wait_for(call, timeout=_PART_TIMEOUT)
        except Exception as exc:  # edge-tts exposes several transport exception types
            last_error = exc
            if attempt == _PART_ATTEMPTS - 1:
                break
            # DashScope rate limits need materially longer spacing than network
            # retries; retrying immediately only extends the provider cooldown.
            delay = 10.0 * (attempt + 1) if "429" in str(exc) or "RateQuota" in str(exc) else min(6.0, 1.5 * (2 ** attempt))
            await asyncio.sleep(delay)
    preview = re.sub(r"\s+", "", text)[:24]
    raise RuntimeError(
        f"TTS 分段合成失败（{_PART_ATTEMPTS} 次尝试，文本：{preview}）：{last_error}"
    ) from last_error


def _concat_mp3(parts: list[bytes]) -> bytes:
    if not parts:
        return b""
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
        concat_list = Path(tmpdir) / "concat.txt"
        concat_list.write_text(
            "".join(f"file '{path.as_posix().replace(chr(39), chr(39) + chr(39))}'\n" for path in paths),
            encoding="utf-8",
        )
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_list),
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


async def _synthesize_detailed(
    text: str, voice: str, provider: str | None = None, model: str | None = None,
    emotion_profile: str | None = None, speaker: str | None = None,
    delivery_instruction: str | None = None, natural_dialogue: bool = False,
    protected_terms: tuple[str, ...] = (),
    provider_options: dict | None = None,
) -> tuple[bytes, list[dict], list[dict]]:
    """Synthesize natural batches and retain each batch for UI and alignment."""
    provider_name = str(provider or config.TTS_PROVIDER).lower()
    # The legacy compatibility wrapper deliberately leaves ``provider`` unset;
    # keep its historical short-batch behavior. Production calls always pass
    # the selected provider explicitly, so IndexTTS receives long-context
    # segmentation there.
    is_indextts = provider is not None and provider_name in {
        "indextts25", "index-tts-2.5", "indextts2.5"
    }
    if is_indextts:
        parts = _split_tts_segments(
            text,
            target_chars=_INDEXTTS_TARGET_SEGMENT_CHARS,
            min_chars=min(120, _INDEXTTS_TARGET_SEGMENT_CHARS),
            max_chars=_INDEXTTS_MAX_SEGMENT_CHARS,
            protected_terms=protected_terms,
        )
    else:
        parts = _split_tts_segments(text, protected_terms=protected_terms)
    spoken_parts = [normalize_tts_numbers(part) for part in parts]
    if not parts:
        return b"", [], []
    is_cosyvoice = provider_name in {"cosyvoice2", "cosyvoice"}
    serialized_provider = is_cosyvoice or is_indextts
    semaphore = asyncio.Semaphore(_COSYVOICE_CONCURRENCY if serialized_provider else _CONCURRENCY)

    async def synthesize_limited(index: int, part: str, spoken_part: str):
        async with semaphore:
            request_text = spoken_part
            if is_cosyvoice and emotion_profile == _COSY_WARM_NARRATIVE and not natural_dialogue:
                position = "hook" if index == 0 else "close" if index == len(parts) - 1 else "body"
                request_text = _cosyvoice_ssml(spoken_part, position, speaker)
            result = await _synthesize_part_with_retry(
                request_text, voice, provider, model, delivery_instruction, provider_options,
            )
            if is_cosyvoice and _COSYVOICE_REQUEST_GAP:
                await asyncio.sleep(_COSYVOICE_REQUEST_GAP)
            return result

    results = await asyncio.gather(*(synthesize_limited(index, part, spoken) for index, (part, spoken) in enumerate(zip(parts, spoken_parts))))
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


def _dialogue_turns(text: str) -> list[tuple[str, str]]:
    """Split a reviewed podcast script into explicitly labelled speaker turns."""
    turns: list[tuple[str, str]] = []
    for line in re.split(r"\n+", text or ""):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(主持人|嘉宾)\s*[：:]+\s*(.+)$", line)
        if not match:
            raise ValueError("双人口播稿每段必须以“主持人：”或“嘉宾：”开头")
        turns.append((match.group(1), match.group(2).strip()))
    if len(turns) < 2 or len({speaker for speaker, _ in turns}) < 2:
        raise ValueError("双人口播稿至少需要主持人和嘉宾各一段")
    return turns


def _dialogue_delivery_instruction(speaker: str, text: str) -> str:
    """Keep role direction specific but restrained for each podcast turn."""
    if speaker == "主持人":
        if "？" in text or "?" in text:
            role = "请像日常聊天时真心好奇地提问，语速平稳，问句自然轻微上扬。"
        elif re.search(r"(对|是啊|可不是|这话说得对|明白了)", text):
            role = "请像日常聊天时自然附和和承接，不抢戏，不刻意强调。"
        else:
            role = "请像有经验但不端着的播客男主持人一样自然承接，声音放松、有呼吸感，句子长短有变化；不要用刻板播音腔、新闻腔或每句同样的重音。"
    else:
        role = "请像耐心聊天的嘉宾一样平实拆解和解释，语速从容，用正常交流口吻。"
    return (
        f"{role} 语调只随语义自然起伏，不要播音腔、背书感或表演感。"
        "保留文本标点带来的自然停顿，短问短停，解释句在转折处略停；不要刻意拉长，不要把每句话读成完整口号。"
    )


def _aligned_dialogue_instructions(
    turns: list[tuple[str, str]], delivery_plan: list[dict] | None,
) -> list[str]:
    """Use the reviewed director plan only when it still matches the approved text."""
    if isinstance(delivery_plan, list) and len(delivery_plan) == len(turns):
        instructions: list[str] = []
        for (speaker, text), item in zip(turns, delivery_plan):
            if not isinstance(item, dict):
                break
            if str(item.get("speaker") or "").strip() != speaker:
                break
            if str(item.get("text") or "").strip() != text:
                break
            instruction = str(item.get("instruction") or "").strip()
            if not instruction:
                break
            instructions.append(instruction)
        if len(instructions) == len(turns):
            return instructions
    return [_dialogue_delivery_instruction(speaker, text) for speaker, text in turns]


def _dialogue_visual_timeline(batches: list[dict]) -> list[dict]:
    """Derive active-speaker states from measured turn boundaries, never volume."""
    timeline: list[dict] = []
    previous_end = 0.0
    for batch in batches:
        start = round(float(batch.get("start", 0.0)), 3)
        end = round(float(batch.get("end", start)), 3)
        speaker = str(batch.get("speaker") or "")
        if speaker not in {"主持人", "嘉宾"} or end < start:
            raise ValueError("双人播客轮次时间轴无效")
        if abs(start - previous_end) > 0.02:
            raise ValueError("双人播客轮次时间轴不连续")
        timeline.append({
            "turn_index": int(batch["index"]),
            "speaker": speaker,
            "active_speaker": speaker,
            "focus": "left" if speaker == "主持人" else "right",
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
        })
        previous_end = end
    return timeline


async def _synthesize_dialogue_detailed(
    text: str, primary_voice: str, secondary_voice: str,
    provider: str | None = None, model: str | None = None,
    secondary_provider: str | None = None, secondary_model: str | None = None,
    emotion_profile: str | None = None,
    delivery_plan: list[dict] | None = None,
    primary_provider_options: dict | None = None,
    secondary_provider_options: dict | None = None,
) -> tuple[bytes, list[dict], list[dict]]:
    audio_parts: list[bytes] = []
    merged_segments: list[dict] = []
    batches: list[dict] = []
    time_offset = 0.0
    char_offset = 0
    turns = _dialogue_turns(text)
    instructions = _aligned_dialogue_instructions(turns, delivery_plan)
    for index, ((speaker, turn), instruction) in enumerate(zip(turns, instructions)):
        use_secondary = speaker == "嘉宾"
        audio, segments, turn_batches = await _synthesize_detailed(
            turn,
            secondary_voice if use_secondary else primary_voice,
            secondary_provider if use_secondary else provider,
            secondary_model if use_secondary else model,
            emotion_profile,
            speaker,
            instruction,
            True,
            provider_options=(secondary_provider_options if use_secondary else primary_provider_options),
        )
        duration = sum(float(batch["duration"]) for batch in turn_batches)
        audio_parts.append(audio)
        for segment in segments:
            merged_segments.append({
                **segment,
                "speaker": speaker,
                "start": round(float(segment.get("start", 0)) + time_offset, 3),
                "end": round(float(segment.get("end", 0)) + time_offset, 3),
                "char_start": int(segment.get("char_start", 0)) + char_offset,
                "char_end": int(segment.get("char_end", 0)) + char_offset,
            })
        batches.append({
            "index": index,
            "speaker": speaker,
            "text": turn,
            "duration": round(duration, 3),
            "start": round(time_offset, 3),
            "end": round(time_offset + duration, 3),
            "voice": secondary_voice if use_secondary else primary_voice,
            "provider": secondary_provider if use_secondary else provider,
            "model": secondary_model if use_secondary else model,
            "audio": audio,
        })
        time_offset += duration
        char_offset += visible_len(turn)
    return _concat_mp3(audio_parts), merged_segments, batches


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


def _canonical_provider(provider: str | None) -> str:
    name = str(provider or "").strip().lower()
    if name in {"index-tts-2.5", "indextts2.5"}:
        return "indextts25"
    if name == "cosyvoice":
        return "cosyvoice2"
    if name == "edge-tts":
        return "edge"
    return name


def _single_narration_provider_chain(
    primary: str, fallback_providers: object = None,
) -> list[str]:
    """Return whole-script fallbacks; a finished audio never mixes providers.

    ``fallback_providers`` comes from the immutable task snapshot.  An explicit
    empty list is meaningful: it enables strict primary-provider mode and must
    not silently inherit a stale process-wide environment variable.
    """
    canonical = _canonical_provider(primary)
    if canonical != "indextts25":
        return [canonical]
    if fallback_providers is None:
        raw_items = os.environ.get("TTS_FALLBACK_PROVIDERS", "cosyvoice2,edge").split(",")
    elif isinstance(fallback_providers, str):
        raw_items = fallback_providers.split(",")
    elif isinstance(fallback_providers, (list, tuple)):
        raw_items = list(fallback_providers)
    else:
        raw_items = []
    chain = [canonical]
    for item in raw_items:
        candidate = _canonical_provider(item)
        if candidate and candidate not in chain:
            chain.append(candidate)
    return chain


def _provider_defaults(
    provider: str, primary_provider: str, primary_voice: str, primary_model: str | None,
) -> tuple[str, str | None]:
    if provider == _canonical_provider(primary_provider):
        return primary_voice, primary_model
    if provider == "cosyvoice2":
        voice = (
            os.environ.get("COSYVOICE2_FALLBACK_VOICE", "").strip()
            or config.COSYVOICE2_VOICE
        )
        model = os.environ.get("COSYVOICE2_FALLBACK_MODEL", "").strip() or None
        if not voice:
            raise ValueError("CosyVoice2 回退音色未配置")
        return voice, model
    if provider == "edge":
        return (
            os.environ.get("EDGE_TTS_FALLBACK_VOICE", "").strip()
            or config.TTS_VOICE,
            None,
        )
    raise ValueError(f"不支持的 TTS 回退 Provider: {provider}")


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
    requested_provider = _canonical_provider(tts_params.get("provider") or config.TTS_PROVIDER)
    provider = requested_provider
    voice = tts_params.get("voice") or (
        config.COSYVOICE2_VOICE if provider == "cosyvoice2"
        else config.INDEXTTS25_VOICE if provider == "indextts25"
        else _VOICE
    )
    model = tts_params.get("model") or None
    emotion_profile = str(tts_params.get("emotion_profile") or ( _COSY_WARM_NARRATIVE if str(provider).lower() in {"cosyvoice2", "cosyvoice"} else "")) or None
    narration_mode = str(tts_params.get("narration_mode") or "single")
    secondary_voice = str(tts_params.get("secondary_voice") or "").strip()
    primary_provider_options = tts_params.get("primary_provider_options") or {}
    secondary_provider_options = tts_params.get("secondary_provider_options") or {}
    if not isinstance(primary_provider_options, dict) or not isinstance(secondary_provider_options, dict):
        db.set_stage(stage["id"], "failed", error="TTS 任务参数格式错误：音色控制参数必须是对象")
        return "failed", None
    if narration_mode == "dual_dialogue" and not secondary_voice:
        db.set_stage(stage["id"], "failed", error="双人口播需要配置第二音色")
        return "failed", None
    if narration_mode == "dual_dialogue":
        cta = _clean_tts_text(_get_cta(task_id) or "")
        dialogue_text = rewrite_text + ("\n主持人：" + cta if cta else "")
        delivery_plan = _get_final_delivery_plan(task_id)
        audio, sentence_segments, batches = asyncio.run(_synthesize_dialogue_detailed(
            dialogue_text, voice, secondary_voice, provider, model,
            tts_params.get("secondary_provider") or provider,
            tts_params.get("secondary_model") or model,
            emotion_profile,
            delivery_plan,
            primary_provider_options,
            secondary_provider_options,
        ))
        text = "\n".join(turn for _speaker, turn in _dialogue_turns(dialogue_text))
    else:
        fallback_events: list[dict[str, str]] = []
        last_error: Exception | None = None
        # Task snapshots are authoritative.  Older snapshots do not contain a
        # fallback list, so keep them strict as well instead of inheriting the
        # environment of whichever Worker happens to claim the stage.
        snapshot_fallbacks = tts_params.get("fallback_providers", [])
        for candidate in _single_narration_provider_chain(provider, snapshot_fallbacks):
            try:
                candidate_voice, candidate_model = _provider_defaults(
                    candidate, provider, voice, model,
                )
                candidate_emotion = emotion_profile if candidate == "cosyvoice2" else None
                audio, sentence_segments, batches = asyncio.run(_synthesize_detailed(
                    text,
                    candidate_voice,
                    candidate,
                    candidate_model,
                    candidate_emotion,
                    protected_terms=(_book_title(book_name),) if _book_title(book_name) else (),
                ))
                provider, voice, model, emotion_profile = (
                    candidate, candidate_voice, candidate_model, candidate_emotion,
                )
                for batch in batches:
                    batch["provider"] = provider
                break
            except Exception as exc:
                last_error = exc
                fallback_events.append({
                    "provider": candidate,
                    "error": re.sub(r"\s+", " ", str(exc))[:500],
                })
        else:
            attempted = " -> ".join(item["provider"] for item in fallback_events)
            raise RuntimeError(
                f"TTS 整篇合成失败（已尝试 {attempted}）：{last_error}"
            ) from last_error
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
            "index": batch["index"], "duration": batch["duration"],
            "voice": batch.get("voice") or voice,
            "speaker": batch.get("speaker"),
            "provider": batch.get("provider") or provider,
            "model": batch.get("model") or model,
        })
        batch_data.append({**batch, "path": batch_path, "status": "done"})

    dialogue_timeline = _dialogue_visual_timeline(batch_data) if narration_mode == "dual_dialogue" else []

    # 上传音频
    sp_audio = f"{task_id}/tts.mp3"
    storage.upload_bytes(sp_audio, audio, "audio/mpeg")
    storage.add_artifact(task_id, "tts", "audio", sp_audio, meta={
        "provider": provider,
        "requested_provider": requested_provider,
        "fallback_used": provider != requested_provider,
        "fallback_events": fallback_events if narration_mode != "dual_dialogue" else [],
        "model": model,
        "voice": voice,
        "duration": duration,
        "segment_count": len(cues),
        "synthesis_batches": len(batch_data),
        "input_format": "timeline_v3",
        "narration_mode": narration_mode,
        "secondary_voice": secondary_voice or None,
        "emotion_profile": emotion_profile,
        "primary_provider_options": primary_provider_options or None,
        "secondary_provider_options": secondary_provider_options or None,
    })

    # 上传字幕时间戳
    sp_subs = f"{task_id}/tts_subtitles.json"
    subs_data = json.dumps(
        {
            "provider": provider,
            "requested_provider": requested_provider,
            "fallback_used": provider != requested_provider,
            "fallback_events": fallback_events if narration_mode != "dual_dialogue" else [],
            "voice": voice,
            "duration": duration,
            "segments": cues,
            "sentence_segments": sentence_segments,
            "batches": batch_data,
            "dialogue_timeline": dialogue_timeline,
            "text": text,
            "narration_text": rewrite_text,
            "cta_text": cta,
            "input_format": "timeline_v3",
            "synthesis_batches": len(batch_data),
            "subtitle_max_chars": 14,
            "subtitle_format": "semantic_words_v2",
            "subtitle_segmenter": "jieba_compound_dp_v1",
            "pause_profile": "promote_tts_pause_v1",
            "emotion_profile": emotion_profile,
            "primary_provider_options": primary_provider_options or None,
            "secondary_provider_options": secondary_provider_options or None,
            "ssml_enabled": bool(emotion_profile == _COSY_WARM_NARRATIVE and str(provider).lower() in {"cosyvoice2", "cosyvoice"}),
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
        "emotion_profile": emotion_profile,
    })

    return "done", sp_audio
