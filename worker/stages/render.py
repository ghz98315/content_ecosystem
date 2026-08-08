"""⑧ 成片 render：固定信息版式 + 4:3 分镜 + 平滑 Zoom In + TTS 字幕。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import imageio_ffmpeg

import db
import storage
import config
from narration import strip_subtitle_punctuation, visible_len
from quality import inspect_render_quality

W, H = 1080, 1920
PHOTO_H = 810
PHOTO_Y = (H - PHOTO_H) // 2
FPS = 30
COVER_FRAMES = 15
INTRO_DUR = COVER_FRAMES / FPS
TRANSITION_DUR = 0.2
ZOOM_OVERSAMPLE = 4
ZOOM_AMOUNT = 0.14
DISCLAIMER_GAP_LINES = 4
TITLE_FONT_SIZE = 84
AUTHOR_FONT_SIZE = 52
SUBTITLE_FONT_SIZE = 72
DISCLAIMER_FONT_SIZE = 30
DISCLAIMER_OPACITY = 0.5
SUBTITLE_MARGIN_V = H - (PHOTO_Y + PHOTO_H - 42)
AUTHOR_TO_PHOTO_GAP = 58
TITLE_AUTHOR_GAP = 52

_ACTIVE_DEADLINE: float | None = None


class RenderTimeout(RuntimeError):
    """Raised when a render or one of its ffmpeg steps exceeds its deadline."""


def _check_deadline() -> float | None:
    if _ACTIVE_DEADLINE is None:
        return None
    remaining = _ACTIVE_DEADLINE - time.monotonic()
    if remaining <= 0:
        raise RenderTimeout(f"render 超过 {config.RENDER_TIMEOUT:.0f} 秒，已停止并保留旧成片")
    return remaining


def _run_ffmpeg(args: list[str], **kwargs):
    """Run ffmpeg with a bounded subprocess timeout during production renders."""
    remaining = _check_deadline()
    if remaining is not None:
        requested = float(config.RENDER_SUBPROCESS_TIMEOUT)
        kwargs["timeout"] = max(0.05, min(requested, remaining))
    try:
        return subprocess.run(args, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise RenderTimeout(
            f"ffmpeg 单步超过 {config.RENDER_SUBPROCESS_TIMEOUT:.0f} 秒，已停止并保留旧成片"
        ) from exc


def ff() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _load_json_artifact(task_id: str, artifact_type: str) -> dict | list | None:
    res = db.retry(
        lambda: db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", artifact_type)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    local = storage.download_artifact(res.data[0]["storage_path"], ".json")
    try:
        return json.load(open(local, encoding="utf-8"))
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def _load_audio(task_id: str) -> str | None:
    res = db.retry(
        lambda: db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("stage_kind", "tts")
        .eq("type", "audio")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return storage.download_artifact(res.data[0]["storage_path"], ".mp3")


def _fmt_ass_time(t: float) -> str:
    t = max(0.0, t + INTRO_DUR)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    cs = int((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _make_ass(segments: list[dict], out_path: str) -> None:
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,"
        "Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,"
        "Encoding\n"
        f"Style: Default,Microsoft YaHei,{SUBTITLE_FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,"
        f"-1,0,0,0,100,100,0,0,1,5,0,2,70,70,{SUBTITLE_MARGIN_V},1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = [header]
    for seg in segments:
        start = _fmt_ass_time(float(seg.get("start", 0)))
        end = _fmt_ass_time(float(seg.get("end", 0)))
        text = _escape_ass(str(seg.get("text", "")))
        if text:
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _find_cjk_font(bold: bool = False) -> str:
    candidates = ([
        r"C:\Windows\Fonts\msyhbd.ttc",
    ] if bold else [
        r"C:\Windows\Fonts\msyh.ttc",
    ]) + [
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\STZHONGS.TTF",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise FileNotFoundError("未找到中文字体，请确认 Windows Fonts 下有微软雅黑或黑体")


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(_find_cjk_font(bold), size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int, max_lines: int = 2) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = char
            if len(lines) >= max_lines - 1:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        consumed = sum(len(line) for line in lines)
        tail = text[consumed:]
        while tail and draw.textbbox((0, 0), tail, font=font)[2] > max_width:
            tail = tail[:-1]
        if consumed + len(tail) < len(text) and len(tail) > 1:
            tail = tail[:-1] + "…"
        lines.append(tail)
    return lines or [text]


def _draw_centered_lines(draw, lines: list[str], font, y: int, fill, spacing: int = 10) -> int:
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        width = box[2] - box[0]
        height = box[3] - box[1]
        draw.text(((W - width) // 2, y), line, font=font, fill=fill)
        y += height + spacing
    return y


def _disclaimer_text(book_name: str) -> str:
    title = book_name.strip("《》") or "本书"
    return f"本视频基于《{title}》及相关研究资料整理，\n仅用于科普分享，不构成任何建议或行为引导。"


def _disclaimer_fill() -> tuple[int, int, int]:
    background = (18, 20, 24)
    foreground = (210, 214, 220)
    return tuple(
        round(bg + (fg - bg) * DISCLAIMER_OPACITY)
        for bg, fg in zip(background, foreground)
    )


def _make_layout_frame(book_name: str, author: str, out_png: str) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (W, H), (18, 20, 24))
    draw = ImageDraw.Draw(image)
    title = f"《{book_name.strip('《》')}》"
    title_font = _font(TITLE_FONT_SIZE if len(title) <= 18 else 72, bold=True)
    author_font = _font(AUTHOR_FONT_SIZE)
    disclaimer_font = _font(DISCLAIMER_FONT_SIZE)

    title_lines = _wrap_text(draw, title, title_font, W - 120, max_lines=2)
    author_text = f"作者：{author}"
    author_box = draw.textbbox((0, 0), author_text, font=author_font)
    author_height = author_box[3] - author_box[1]
    author_y = PHOTO_Y - AUTHOR_TO_PHOTO_GAP - author_height
    title_heights = [draw.textbbox((0, 0), line, font=title_font)[3] for line in title_lines]
    title_block_height = sum(title_heights) + 10 * max(0, len(title_lines) - 1)
    title_y = author_y - TITLE_AUTHOR_GAP - title_block_height
    _draw_centered_lines(draw, title_lines, title_font, title_y, (255, 255, 255), spacing=10)
    draw.text(
        ((W - (author_box[2] - author_box[0])) // 2, author_y),
        author_text,
        font=author_font,
        fill=(224, 228, 234),
    )

    draw.line((0, PHOTO_Y - 1, W, PHOTO_Y - 1), fill=(55, 60, 68), width=1)
    draw.line((0, PHOTO_Y + PHOTO_H, W, PHOTO_Y + PHOTO_H), fill=(55, 60, 68), width=1)
    disclaimer_lines: list[str] = []
    for raw_line in _disclaimer_text(book_name).splitlines():
        disclaimer_lines.extend(_wrap_text(draw, raw_line, disclaimer_font, W - 120, max_lines=2))
    disclaimer_heights = [draw.textbbox((0, 0), line, font=disclaimer_font)[3] for line in disclaimer_lines]
    disclaimer_block_height = sum(disclaimer_heights) + 10 * max(0, len(disclaimer_lines) - 1)
    disclaimer_y = PHOTO_Y + PHOTO_H + DISCLAIMER_GAP_LINES * DISCLAIMER_FONT_SIZE
    if disclaimer_y + disclaimer_block_height > H - 30:
        disclaimer_y = H - 30 - disclaimer_block_height
    _draw_centered_lines(
        draw,
        disclaimer_lines,
        disclaimer_font,
        disclaimer_y,
        _disclaimer_fill(),
        spacing=10,
    )
    image.save(out_png, "PNG")


def _make_cover_clip(img_path: str, layout_path: str, duration: float, out_mp4: str) -> None:
    """Hold the first image frame as the short cover instead of a title card."""
    graph = (
        f"[0:v]scale={W}:{PHOTO_H}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={W}:{PHOTO_H}[photo];"
        f"[1:v][photo]overlay=0:{PHOTO_Y}:shortest=1,format=yuv420p[v]"
    )
    _run_ffmpeg([
        ff(), "-y",
        "-loop", "1", "-framerate", str(FPS), "-t", str(duration), "-i", img_path,
        "-loop", "1", "-framerate", str(FPS), "-t", str(duration), "-i", layout_path,
        "-filter_complex", graph, "-map", "[v]", "-frames:v", str(COVER_FRAMES),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", out_mp4,
    ], check=True, capture_output=True)


def _make_image_clip(img_path: str, layout_path: str, duration: float, out_mp4: str) -> None:
    frames = max(2, round(duration * FPS))
    zoom_denominator = frames - 1
    zoom_easing = (
        f"3*pow(on/{zoom_denominator},2)-2*pow(on/{zoom_denominator},3)"
    )
    work_w = W * ZOOM_OVERSAMPLE
    work_h = PHOTO_H * ZOOM_OVERSAMPLE
    graph = (
        f"[0:v]scale={work_w}:{work_h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={work_w}:{work_h},"
        f"zoompan=z='1+{ZOOM_AMOUNT}*({zoom_easing})':"
        "x='trunc((iw-iw/zoom)/4)*2':y='trunc((ih-ih/zoom)/4)*2':"
        f"d={frames}:s={W}x{PHOTO_H}:fps={FPS}[photo];"
        f"[1:v][photo]overlay=0:{PHOTO_Y}:shortest=1,format=yuv420p[v]"
    )
    _run_ffmpeg([
        ff(), "-y",
        "-i", img_path,
        "-loop", "1", "-framerate", str(FPS), "-t", str(duration), "-i", layout_path,
        "-filter_complex", graph, "-map", "[v]",
        "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-an", out_mp4,
    ], check=True, capture_output=True)


def _allocate_durations(images: list[dict], tts_duration: float) -> list[float]:
    overlap = TRANSITION_DUR * max(0, len(images) - 1)
    gross_duration = max(tts_duration + overlap, len(images) * 1.0)
    weights = [max(1, int(item.get("char_count") or len(str(item.get("sentence", ""))))) for item in images]
    total_weight = sum(weights) or len(images)
    return [round(gross_duration * weight / total_weight, 3) for weight in weights]


def _cue_time_at_char(position: int, cues: list[dict], duration: float) -> float:
    """Map a narration character offset onto the measured TTS timeline."""
    if not cues:
        return 0.0
    previous_char, previous_time = 0, 0.0
    for cue in cues:
        start_char = int(cue.get("char_start", previous_char))
        end_char = max(start_char + 1, int(cue.get("char_end", start_char + 1)))
        start_time = float(cue.get("start", previous_time))
        end_time = max(start_time, float(cue.get("end", start_time)))
        if position < start_char:
            span = max(1, start_char - previous_char)
            return previous_time + (start_time - previous_time) * (position - previous_char) / span
        if position <= end_char:
            return start_time + (end_time - start_time) * (position - start_char) / (end_char - start_char)
        previous_char, previous_time = end_char, end_time
    return min(duration, previous_time)


def _build_timeline(images: list[dict], cues: list[dict], tts_duration: float) -> list[dict]:
    """Use shared character ranges to align every image with audio and subtitles."""
    if not images:
        return []
    normalized: list[dict] = []
    char_cursor = 0
    for index, image in enumerate(images):
        char_count = max(1, int(image.get("char_count") or len(str(image.get("sentence", "")))))
        char_start = int(image.get("char_start", char_cursor))
        char_end = int(image.get("char_end", char_start + char_count))
        normalized.append({
            **image,
            "index": index,
            "char_start": char_start,
            "char_end": max(char_start + 1, char_end),
        })
        char_cursor = max(char_start + 1, char_end)

    starts = [0.0]
    for image in normalized[1:]:
        starts.append(_cue_time_at_char(int(image["char_start"]), cues, tts_duration))

    timeline: list[dict] = []
    for index, image in enumerate(normalized):
        start = starts[index]
        end = starts[index + 1] if index + 1 < len(starts) else tts_duration
        timeline.append({
            "index": index,
            "path": image.get("path"),
            "sentence": image.get("sentence", image.get("text", "")),
            "char_start": image["char_start"],
            "char_end": image["char_end"],
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
        })
    return timeline


def _validate_timeline(timeline: list[dict], cues: list[dict], tts_duration: float) -> None:
    if not timeline:
        raise ValueError("图片时间轴为空")
    if any(not item.get("path") for item in timeline):
        raise ValueError("图片时间轴存在缺失路径")
    if any(float(item["duration"]) < 0.35 for item in timeline):
        raise ValueError("图片分镜过密，存在不足 0.35 秒的画面")
    if abs(float(timeline[0]["start"])) > 0.01 or abs(float(timeline[-1]["end"]) - tts_duration) > 0.02:
        raise ValueError("图片时间轴未完整覆盖配音")
    for previous, current in zip(timeline, timeline[1:]):
        if abs(float(previous["end"]) - float(current["start"])) > 0.02:
            raise ValueError("图片时间轴不连续")
    for cue in cues:
        text = str(cue.get("text", ""))
        if visible_len(text) > 14:
            raise ValueError("字幕存在超过 14 字的片段")
        if text != strip_subtitle_punctuation(text):
            raise ValueError("字幕存在标点符号，必须在标点处断句且不显示标点")
        start = float(cue.get("start", 0.0))
        end = float(cue.get("end", start))
        if end < start:
            raise ValueError("字幕时间轴存在结束时间早于开始时间")


def _timeline_clip_durations(timeline: list[dict]) -> list[float]:
    """Add dissolve overlap while preserving exact final content duration."""
    return [
        round(float(item["duration"]) + (TRANSITION_DUR if index < len(timeline) - 1 else 0.0), 3)
        for index, item in enumerate(timeline)
    ]


def _exact_timeline_durations(timeline: list[dict]) -> list[float]:
    """Timeline v3 uses hard visual boundaries so audio and images never drift."""
    return [round(float(item["duration"]), 3) for item in timeline]


def _video_duration(path: str) -> float:
    result = _run_ffmpeg([ff(), "-i", path], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise ValueError("无法读取中间视频时长")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _concat_clips_exact(clips: list[str], expected_duration: float, out_mp4: str, tmpdir: str) -> None:
    """Concatenate all timeline clips deterministically instead of a fragile large xfade graph."""
    manifest = Path(tmpdir) / "content_concat.txt"
    manifest.write_text(
        "".join(f"file '{Path(clip).as_posix()}'\n" for clip in clips),
        encoding="utf-8",
    )
    _run_ffmpeg([
        ff(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), out_mp4,
    ], check=True, capture_output=True)
    actual_duration = _video_duration(out_mp4)
    if abs(actual_duration - expected_duration) > 0.2:
        raise ValueError(
            f"图片拼接时长异常：实际 {actual_duration:.3f}s，期望 {expected_duration:.3f}s"
        )


def _compose_with_dissolve(clips: list[str], durations: list[float], out_mp4: str) -> None:
    if len(clips) == 1:
        shutil.copyfile(clips[0], out_mp4)
        return
    workdir = str(Path(out_mp4).parent)
    nodes = [(clip, float(duration)) for clip, duration in zip(clips, durations)]
    round_index = 0
    while len(nodes) > 1:
        merged: list[tuple[str, float]] = []
        for pair_index in range(0, len(nodes), 2):
            if pair_index + 1 >= len(nodes):
                merged.append(nodes[pair_index])
                continue
            left_path, left_duration = nodes[pair_index]
            right_path, right_duration = nodes[pair_index + 1]
            transition = min(TRANSITION_DUR, left_duration / 2, right_duration / 2)
            expected = left_duration + right_duration - transition
            output = os.path.join(workdir, f"merge_{round_index:02d}_{pair_index // 2:03d}.mp4")
            _run_ffmpeg([
                ff(), "-y", "-i", left_path, "-i", right_path,
                "-filter_complex",
                f"[0:v][1:v]xfade=transition=fade:duration={transition:.3f}:offset={left_duration - transition:.3f}[v]",
                "-map", "[v]", "-t", f"{expected:.3f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", output,
            ], check=True, capture_output=True)
            merged.append((output, expected))
        nodes = merged
        round_index += 1
    shutil.copyfile(nodes[0][0], out_mp4)


def _concat_intro(intro: str, content: str, out_mp4: str, tmpdir: str) -> None:
    _run_ffmpeg([
        ff(), "-y", "-i", intro, "-i", content,
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), out_mp4,
    ], check=True, capture_output=True)


def run(stage: dict) -> tuple[str, str | None]:
    global _ACTIVE_DEADLINE
    task_id = stage["task_id"]
    _ACTIVE_DEADLINE = time.monotonic() + max(1.0, float(config.RENDER_TIMEOUT))
    print("  [render] 读取图片索引", flush=True)
    images_data = _load_json_artifact(task_id, "image_index")
    print("  [render] 读取字幕时间轴", flush=True)
    subs_data = _load_json_artifact(task_id, "subtitle")
    print("  [render] 读取书籍信息", flush=True)
    book_data = _load_json_artifact(task_id, "book")
    print("  [render] 下载完整配音", flush=True)
    audio_path = _load_audio(task_id)

    if not images_data or not audio_path:
        db.set_stage(stage["id"], "failed", error="缺少图片或音频产物（请确认 image/tts 阶段已完成）")
        return "failed", None

    images: list[dict] = images_data if isinstance(images_data, list) else []
    segments: list[dict] = subs_data.get("segments", []) if isinstance(subs_data, dict) else []
    tts_duration = float(subs_data.get("duration", 0.0) if isinstance(subs_data, dict) else 0.0) or 1.0
    book_name = str(book_data.get("book_name", "") if isinstance(book_data, dict) else "") or "本书"
    author = str(book_data.get("author", "") if isinstance(book_data, dict) else "") or "作者"

    tmpdir = tempfile.mkdtemp(prefix="render_")
    try:
        if not os.path.exists(audio_path):
            raise ValueError("配音临时文件不存在，已停止渲染")
        audio_local = os.path.join(tmpdir, "tts.mp3")
        shutil.copyfile(audio_path, audio_local)
        if not images:
            db.set_stage(stage["id"], "failed", error="图片列表为空")
            return "failed", None
        layout_png = os.path.join(tmpdir, "layout.png")
        _make_layout_frame(book_name, author, layout_png)
        cover_local = storage.download_artifact(images[0]["path"], ".png")
        cover_mp4 = os.path.join(tmpdir, "cover.mp4")
        try:
            _make_cover_clip(cover_local, layout_png, INTRO_DUR, cover_mp4)
        finally:
            try:
                os.remove(cover_local)
            except OSError:
                pass
        print(f"  [render] 布局就绪，开始编码 {len(images)} 个镜头", flush=True)
        is_timeline_v3 = isinstance(subs_data, dict) and subs_data.get("input_format") == "timeline_v3"
        timeline = _build_timeline(images, segments, tts_duration) if is_timeline_v3 else []
        if timeline:
            _validate_timeline(timeline, segments, tts_duration)
            durations = _timeline_clip_durations(timeline)
            if len(images) > config.RENDER_DISSOLVE_MAX_CLIPS:
                durations = _exact_timeline_durations(timeline)
        else:
            durations = _allocate_durations(images, tts_duration)
            timeline = [
                {"index": index, "path": item.get("path"), "duration": duration}
                for index, (item, duration) in enumerate(zip(images, durations))
            ]

        clip_paths: list[str] = []
        for i, (item, duration) in enumerate(zip(images, durations)):
            _check_deadline()
            image_local = storage.download_artifact(item["path"], ".png")
            clip = os.path.join(tmpdir, f"clip_{i:03d}.mp4")
            try:
                _make_image_clip(image_local, layout_png, duration, clip)
            finally:
                try:
                    os.remove(image_local)
                except OSError:
                    pass
            clip_paths.append(clip)
            if (i + 1) % 10 == 0 or i + 1 == len(images):
                print(f"  [render] 镜头编码 {i + 1}/{len(images)}", flush=True)

        content_mp4 = os.path.join(tmpdir, "content.mp4")
        transition_mode = "dissolve"
        if is_timeline_v3:
            if len(clip_paths) <= config.RENDER_DISSOLVE_MAX_CLIPS:
                # Merge transitions in a balanced tree. This keeps the measured
                # timeline exact without the truncation seen in one large xfade chain.
                _compose_with_dissolve(clip_paths, durations, content_mp4)
            else:
                # Many short clips make pairwise xfade disproportionately slow.
                # Keep the zoom motion and exact audio alignment with hard cuts.
                transition_mode = "hard_cut_long_timeline"
                _concat_clips_exact(clip_paths, tts_duration, content_mp4, tmpdir)
            actual_duration = _video_duration(content_mp4)
            if abs(actual_duration - tts_duration) > 0.2:
                raise ValueError(
                    f"短叠化后成片时长异常：实际 {actual_duration:.3f}s，期望 {tts_duration:.3f}s"
                )
            print("  [render] 镜头短叠化合成完成", flush=True)
        else:
            if len(clip_paths) <= config.RENDER_DISSOLVE_MAX_CLIPS:
                _compose_with_dissolve(clip_paths, durations, content_mp4)
            else:
                transition_mode = "hard_cut_long_timeline"
                cut_durations = [
                    round(float(duration) - (TRANSITION_DUR if i < len(clip_paths) - 1 else 0.0), 3)
                    for i, duration in enumerate(durations)
                ]
                _concat_clips_exact(clip_paths, sum(cut_durations), content_mp4, tmpdir)

        video_only = os.path.join(tmpdir, "video_only.mp4")
        _concat_intro(cover_mp4, content_mp4, video_only, tmpdir)

        _make_ass(segments, os.path.join(tmpdir, "subs.ass"))
        print("  [render] 合成字幕与完整配音", flush=True)
        final = os.path.join(tmpdir, "final.mp4")
        _run_ffmpeg([
            ff(), "-y", "-i", video_only,
            "-itsoffset", str(INTRO_DUR), "-i", audio_local,
            "-vf", "ass=subs.ass",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", final,
        ], check=True, capture_output=True, cwd=tmpdir)

        stage_rows = db.retry(
            lambda: db.get_client().table("stages")
            .select("kind,status,error")
            .eq("task_id", task_id)
            .order("seq")
            .execute()
        ).data or []
        quality_timeline = timeline
        if not is_timeline_v3:
            quality_timeline = []
            cursor = 0.0
            for index, (item, duration) in enumerate(zip(images, durations)):
                content_duration = duration - (TRANSITION_DUR if index < len(images) - 1 else 0.0)
                quality_timeline.append({
                    "index": index,
                    "path": item.get("path"),
                    "start": round(cursor, 3),
                    "end": round(cursor + content_duration, 3),
                    "duration": round(content_duration, 3),
                })
                cursor += content_duration
        print("  [render] 执行成片自动质检", flush=True)
        quality_report = inspect_render_quality(
            final,
            ff(),
            stage_rows=stage_rows,
            images=images,
            cues=segments,
            timeline=quality_timeline,
            tts_duration=tts_duration,
            width=W,
            height=H,
            fps=FPS,
            intro_duration=INTRO_DUR,
        )
        quality_path = f"{task_id}/quality_report.json"
        storage.upload_bytes(
            quality_path,
            json.dumps(quality_report, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json",
        )
        storage.add_artifact(task_id, "render", "quality_report", quality_path, meta={
            "status": quality_report["status"],
            **quality_report["summary"],
            **quality_report["metrics"],
        })
        if quality_report["status"] == "failed":
            failed_labels = [
                check["label"] for check in quality_report["checks"]
                if check["status"] == "failed"
            ]
            raise ValueError(f"自动质检未通过：{'、'.join(failed_labels)}")

        timeline_path = f"{task_id}/render_timeline.json"
        storage.upload_bytes(
            timeline_path,
            json.dumps(timeline, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json",
        )
        storage.add_artifact(task_id, "render", "timeline", timeline_path, meta={
            "image_count": len(timeline), "duration": tts_duration, "version": 3 if is_timeline_v3 else 2,
        })

        sp = f"{task_id}/final.mp4"
        storage.upload(sp, final, "video/mp4")
        storage.add_artifact(task_id, "render", "final", sp, meta={
            "width": W,
            "height": H,
            "tts_duration": tts_duration,
            "image_count": len(images),
            "intro_duration": INTRO_DUR,
            "cover": "first_image_frame",
            "cover_frames": COVER_FRAMES,
            "motion": "zoom_in",
            "zoom_amount": ZOOM_AMOUNT,
            "zoom_oversample": ZOOM_OVERSAMPLE,
            "transition": transition_mode,
            "transition_duration": TRANSITION_DUR,
            "timeline_version": 3 if is_timeline_v3 else 2,
            "layout": "book_header_photo_subtitles_disclaimer",
            "disclaimer_font_size": DISCLAIMER_FONT_SIZE,
            "disclaimer_opacity": DISCLAIMER_OPACITY,
            "quality_status": quality_report["status"],
            "quality_report": quality_path,
        })
        return "done", sp
    except RenderTimeout as exc:
        db.set_stage(stage["id"], "failed", error=str(exc))
        return "failed", None
    except ValueError as exc:
        db.set_stage(stage["id"], "failed", error=f"成片校验失败: {exc}")
        return "failed", None
    except subprocess.CalledProcessError as exc:
        error = (exc.stderr or b"").decode("utf-8", errors="ignore")[-800:]
        db.set_stage(stage["id"], "failed", error=f"ffmpeg 失败: {error}")
        return "failed", None
    finally:
        _ACTIVE_DEADLINE = None
        shutil.rmtree(tmpdir, ignore_errors=True)
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass
