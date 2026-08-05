"""⑧ 成片 render：固定信息版式 + 4:3 分镜 + Zoom In + 叠化 + TTS 字幕。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

import db
import storage

W, H = 1080, 1920
PHOTO_Y = 330
PHOTO_H = 810
FPS = 30
INTRO_DUR = 1.5
TRANSITION_DUR = 0.5
DISCLAIMER = "内容基于书籍及相关资料整理，仅供参考，不构成专业建议。"


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
        "Style: Default,微软雅黑,54,&H00FFFFFF,&H000000FF,&H00111111,&H90000000,"
        "-1,0,0,0,100,100,0,0,1,4,1,2,70,70,350,1\n\n"
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


def _find_cjk_font() -> str:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\STZHONGS.TTF",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise FileNotFoundError("未找到中文字体，请确认 Windows Fonts 下有微软雅黑或黑体")


def _font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(_find_cjk_font(), size)
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


def _make_layout_frame(book_name: str, author: str, out_png: str) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (W, H), (18, 20, 24))
    draw = ImageDraw.Draw(image)
    title = f"《{book_name.strip('《》')}》"
    title_font = _font(50 if len(title) <= 18 else 42)
    author_font = _font(32)
    disclaimer_font = _font(26)

    title_lines = _wrap_text(draw, title, title_font, W - 120, max_lines=2)
    title_end = _draw_centered_lines(draw, title_lines, title_font, 62, (250, 250, 250), spacing=8)
    author_text = f"作者：{author}"
    author_box = draw.textbbox((0, 0), author_text, font=author_font)
    draw.text(((W - (author_box[2] - author_box[0])) // 2, min(270, title_end + 16)), author_text, font=author_font, fill=(176, 182, 190))

    draw.line((0, PHOTO_Y - 1, W, PHOTO_Y - 1), fill=(55, 60, 68), width=1)
    draw.line((0, PHOTO_Y + PHOTO_H, W, PHOTO_Y + PHOTO_H), fill=(55, 60, 68), width=1)
    disclaimer_lines = _wrap_text(draw, DISCLAIMER, disclaimer_font, W - 120, max_lines=2)
    _draw_centered_lines(draw, disclaimer_lines, disclaimer_font, 1740, (150, 156, 165), spacing=8)
    image.save(out_png, "PNG")


def _make_text_card(text: str, duration: float, out_mp4: str) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (W, H), color=(10, 11, 14))
    draw = ImageDraw.Draw(image)
    font = _font(52)
    lines = text.replace("\\n", "\n").split("\n")
    line_heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    y = (H - sum(line_heights) - 20 * (len(lines) - 1)) // 2
    _draw_centered_lines(draw, lines, font, y, (255, 255, 255), spacing=20)

    tmp_png = out_mp4.replace(".mp4", "_card.png")
    image.save(tmp_png, "PNG")
    try:
        subprocess.run([
            ff(), "-y", "-loop", "1", "-t", str(duration), "-i", tmp_png,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", out_mp4,
        ], check=True, capture_output=True)
    finally:
        try:
            os.remove(tmp_png)
        except OSError:
            pass


def _make_image_clip(img_path: str, layout_path: str, duration: float, out_mp4: str) -> None:
    increment = 0.08 / max(1, duration * FPS)
    graph = (
        f"[0:v]scale={W}:{PHOTO_H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{PHOTO_H},"
        f"zoompan=z='min(zoom+{increment:.8f},1.08)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s={W}x{PHOTO_H}:fps={FPS}[photo];"
        f"[1:v][photo]overlay=0:{PHOTO_Y}:shortest=1,format=yuv420p[v]"
    )
    subprocess.run([
        ff(), "-y",
        "-loop", "1", "-t", str(duration), "-i", img_path,
        "-loop", "1", "-t", str(duration), "-i", layout_path,
        "-filter_complex", graph, "-map", "[v]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", out_mp4,
    ], check=True, capture_output=True)


def _allocate_durations(images: list[dict], tts_duration: float) -> list[float]:
    overlap = TRANSITION_DUR * max(0, len(images) - 1)
    gross_duration = max(tts_duration + overlap, len(images) * 1.0)
    weights = [max(1, int(item.get("char_count") or len(str(item.get("sentence", ""))))) for item in images]
    total_weight = sum(weights) or len(images)
    return [round(gross_duration * weight / total_weight, 3) for weight in weights]


def _compose_with_dissolve(clips: list[str], durations: list[float], out_mp4: str) -> None:
    if len(clips) == 1:
        shutil.copyfile(clips[0], out_mp4)
        return
    inputs: list[str] = []
    for clip in clips:
        inputs.extend(["-i", clip])
    filters: list[str] = []
    previous = "[0:v]"
    for i in range(1, len(clips)):
        output = f"[x{i}]"
        offset = sum(durations[:i]) - TRANSITION_DUR * i
        filters.append(
            f"{previous}[{i}:v]xfade=transition=fade:duration={TRANSITION_DUR}:offset={offset:.3f}{output}"
        )
        previous = output
    subprocess.run([
        ff(), "-y", *inputs,
        "-filter_complex", ";".join(filters), "-map", previous,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", out_mp4,
    ], check=True, capture_output=True)


def _concat_intro(intro: str, content: str, out_mp4: str, tmpdir: str) -> None:
    concat_txt = os.path.join(tmpdir, "concat.txt")
    Path(concat_txt).write_text(f"file '{intro}'\nfile '{content}'\n", encoding="utf-8")
    subprocess.run([
        ff(), "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c", "copy", out_mp4,
    ], check=True, capture_output=True)


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    images_data = _load_json_artifact(task_id, "image_index")
    subs_data = _load_json_artifact(task_id, "subtitle")
    book_data = _load_json_artifact(task_id, "book")
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
        layout_png = os.path.join(tmpdir, "layout.png")
        _make_layout_frame(book_name, author, layout_png)
        durations = _allocate_durations(images, tts_duration)

        clip_paths: list[str] = []
        for i, (item, duration) in enumerate(zip(images, durations)):
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

        if not clip_paths:
            db.set_stage(stage["id"], "failed", error="图片列表为空")
            return "failed", None

        content_mp4 = os.path.join(tmpdir, "content.mp4")
        _compose_with_dissolve(clip_paths, durations, content_mp4)

        intro_mp4 = os.path.join(tmpdir, "intro.mp4")
        _make_text_card(f"《{book_name.strip('《》')}》\\n{author}", INTRO_DUR, intro_mp4)
        video_only = os.path.join(tmpdir, "video_only.mp4")
        _concat_intro(intro_mp4, content_mp4, video_only, tmpdir)

        _make_ass(segments, os.path.join(tmpdir, "subs.ass"))
        final = os.path.join(tmpdir, "final.mp4")
        subprocess.run([
            ff(), "-y", "-i", video_only,
            "-itsoffset", str(INTRO_DUR), "-i", audio_path,
            "-vf", "ass=subs.ass",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", final,
        ], check=True, capture_output=True, cwd=tmpdir)

        sp = f"{task_id}/final.mp4"
        storage.upload(sp, final, "video/mp4")
        storage.add_artifact(task_id, "render", "final", sp, meta={
            "width": W,
            "height": H,
            "tts_duration": tts_duration,
            "image_count": len(images),
            "intro_duration": INTRO_DUR,
            "motion": "zoom_in",
            "transition": "dissolve",
            "transition_duration": TRANSITION_DUR,
            "layout": "book_header_photo_subtitles_disclaimer",
        })
        return "done", sp
    except subprocess.CalledProcessError as exc:
        error = (exc.stderr or b"").decode("utf-8", errors="ignore")[-800:]
        db.set_stage(stage["id"], "failed", error=f"ffmpeg 失败: {error}")
        return "failed", None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass
