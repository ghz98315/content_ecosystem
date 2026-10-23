"""⑧ 成片 render：竖版 9:16 分镜 + 平滑 Zoom In + TTS 字幕。"""
from __future__ import annotations

import json
import uuid
import hashlib
import picture_cache
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

import imageio_ffmpeg

import db
import storage
import config
from production_templates import validate_template, validate_task_template
from quality import inspect_render_quality

W, H = 1080, 1920
# Source images are portrait 9:16 and must fill the final portrait canvas.
PHOTO_H = H
PHOTO_Y = 0
FPS = 30
COVER_FRAMES = 15
INTRO_DUR = COVER_FRAMES / FPS
TRANSITION_DUR = 0.2
ZOOM_OVERSAMPLE = 4
ZOOM_AMOUNT = 0.10
LANDSCAPE_ZOOM_AMOUNT = 0.16
LANDSCAPE_WORK_SCALE = 2
LANDSCAPE_RENDER_SCALE = 2
DISCLAIMER_GAP_LINES = 4
TITLE_FONT_SIZE = 84
AUTHOR_FONT_SIZE = 52
SUBTITLE_FONT_SIZE = 72
DISCLAIMER_FONT_SIZE = 30
DISCLAIMER_OPACITY = 0.5
SUBTITLE_MARGIN_V = round(H / 3)
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


@lru_cache(maxsize=1)
def _nvenc_available() -> bool:
    if config.RENDER_ENCODER == 'cpu':
        return False
    try:
        result = subprocess.run([
            ff(), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
            '-i', 'color=c=black:s=320x320:r=1:d=1', '-frames:v', '1',
            '-c:v', 'h264_nvenc', '-f', 'null', '-',
        ], capture_output=True, timeout=10)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _encoder_args(*, intermediate: bool = False, target_kbps: int | None = None) -> list[str]:
    if _nvenc_available():
        args = ['-c:v', 'h264_nvenc', '-preset', 'p4']
        if target_kbps:
            args += ['-rc', 'vbr', '-b:v', f'{target_kbps}k', '-maxrate', f'{target_kbps}k',
                     '-bufsize', f'{target_kbps * 2}k']
        else:
            args += ['-cq', '16' if intermediate else '17', '-b:v', '0']
        return args + ['-pix_fmt', 'yuv420p']
    args = ['-c:v', 'libx264', '-preset', config.RENDER_ENCODER_PRESET]
    if target_kbps:
        args += ['-b:v', f'{target_kbps}k', '-maxrate', f'{target_kbps}k',
                 '-bufsize', f'{target_kbps * 2}k']
    else:
        args += ['-crf', str(config.RENDER_CRF)]
    return args + ['-pix_fmt', 'yuv420p']


def _storage_safe_video_bitrate(duration: float, target_megabytes: float = 42, max_bytes: int = 48_000_000) -> int:
    """Leave room for 64-kbps AAC and MP4 overhead below Supabase's 50-MB cap."""
    available_bits = min(target_megabytes * 1024 * 1024, max_bytes * .9) * 8
    return max(180, min(2500, int((available_bits / max(duration, 1) - 96_000) / 1000)))


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


def _apply_image_replacements(task_id: str, images: list[dict]) -> list[dict]:
    rows = db.retry(
        lambda: db.get_client().table("image_replacement_requests")
        .select("image_index,replacement_path,status,requested_at")
        .eq("task_id", task_id)
        .eq("status", "done")
        .is_("invalidated_at", "null")
        .order("requested_at", desc=True)
        .execute()
    ).data or []
    latest: dict[int, str] = {}
    for row in rows:
        image_index = int(row.get("image_index", -1))
        if image_index >= 0 and image_index not in latest and row.get("replacement_path"):
            latest[image_index] = str(row["replacement_path"])
    if not latest:
        return images
    return [({**image, "path": latest[index], "replacement_path": latest[index]} if index in latest else image) for index, image in enumerate(images)]


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


def _load_bgm_config(task_id: str) -> tuple[str | None, float, float]:
    """Load task-scoped BGM only when the owner confirmed usage rights."""
    task = db.retry(
        lambda: db.get_client().table("tasks")
        .select("bgm_path,bgm_volume,narration_volume,bgm_authorization_confirmed")
        .eq("id", task_id).single().execute()
    ).data or {}
    bgm_path = str(task.get("bgm_path") or "").strip()
    approved = bool(task.get("bgm_authorization_confirmed"))
    from music_presets import PRESET_PATHS
    if bgm_path and approved and (bgm_path not in PRESET_PATHS and not bgm_path.startswith(f'{task_id}/background-music/')
                                 or '\\' in bgm_path or '%' in bgm_path
                                 or any(part in ('', '.', '..') for part in bgm_path.split('/'))):
        raise ValueError('背景音乐路径不属于当前任务')
    bgm_volume = min(0.30, max(0.02, float(task.get("bgm_volume") or 0.08)))
    narration_volume = min(1.50, max(0.50, float(task.get("narration_volume") or 1.0)))
    return (bgm_path if bgm_path and approved else None, bgm_volume, narration_volume)


def _audio_mix_filter(
    bgm_enabled: bool, bgm_volume: float, narration_volume: float, duration: float = 0.0
) -> str:
    narration = f"[1:a]volume={narration_volume:.3f}[narration]"
    if not bgm_enabled:
        return narration
    fade_start = max(0.0, duration - 0.8)
    return (
        f"[1:a]volume={narration_volume:.3f}[narration];"
        f"[2:a]volume={bgm_volume:.3f},afade=t=in:st=0:d=0.8,"
        f"afade=t=out:st={fade_start:.3f}:d=0.8[bgm];"
        "[narration][bgm]amix=inputs=2:duration=first:dropout_transition=0:weights='1 1'[audio]"
    )


def _fmt_ass_time(t: float) -> str:
    t = max(0.0, t + INTRO_DUR)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    cs = int((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _make_ass(
    segments: list[dict], out_path: str, *, title: str = "", subtitle: str = "",
    footnote: str = "", title_font: str = "KaiTi", duration: float = 0,
    subtitle_y: float = 2 / 3,
    landscape_layout: bool = False,
    subtitle_font: str | None = None, title_color: str = "#BA413B",
    narration_font: str | None = None, footnote_font: str | None = None,
    picture_ratio: float = 4/3,
) -> None:
    subtitle_font = subtitle_font or 'KaiTi'
    narration_font = narration_font or (title_font if landscape_layout else 'Microsoft YaHei')
    footnote_font = footnote_font or ('KaiTi' if landscape_layout else 'Microsoft YaHei')
    for font_name in (title_font, subtitle_font, narration_font, footnote_font):
        if not font_name or len(font_name) > 64 or re.search(r"[,\r\n{}\\/]", font_name):
            raise ValueError("不支持的标题字体")
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', title_color):
        raise ValueError('主标题颜色须为六位十六进制颜色')
    ass_title_color = '&H00' + title_color[5:7] + title_color[3:5] + title_color[1:3]
    if not 0.55 <= float(subtitle_y) <= 0.82:
        raise ValueError("字幕位置须在画面高度的55%至82%之间")
    if any(len(value) > limit for value, limit in ((title, 32), (subtitle, 48), (footnote, 60))):
        raise ValueError("标题、副标题或脚注过长")
    title, subtitle, footnote = (value.replace('\n', ' ').replace('\r', ' ') for value in (title, subtitle, footnote))
    heading_outline = '&H00F1F3F5' if landscape_layout else '&H00202020'
    sub_fill = '&H001A1D20' if landscape_layout else '&H00F4F4F4'
    sub_outline = '&H00FFFFFF' if landscape_layout else '&H00202020'
    foot_fill = '&H001A1D20' if landscape_layout else '&H00E9E9E9'
    foot_outline = '&H00FFFFFF' if landscape_layout else '&H00202020'
    narration_bold = 0 if landscape_layout else -1
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,"
        "Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,"
        "Encoding\n"
        f"Style: Default,{narration_font},{SUBTITLE_FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,"
        f"{narration_bold},0,0,0,100,100,0,0,1,4,1,5,70,70,{SUBTITLE_MARGIN_V},1\n"
        f"Style: Heading,{title_font},{92 if landscape_layout else 88},{ass_title_color},&H000000FF,{heading_outline},&H80000000,0,0,0,0,100,100,2,0,1,{6 if landscape_layout else 3},1,8,80,80,120,1\n"
        f"Style: Subheading,{subtitle_font},{56 if landscape_layout else 52},{sub_fill},&H000000FF,{sub_outline},&H80000000,0,0,0,0,100,100,{0 if landscape_layout else 1},0,1,2,{0 if landscape_layout else 1},8,90,90,238,1\n"
        f"Style: Footnote,{footnote_font},{32 if landscape_layout else 28},{foot_fill},&H000000FF,{foot_outline},&H80000000,0,0,0,0,100,100,0,0,1,{2 if landscape_layout else 1.5},0,3,70,70,110,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = [header]
    # Anchor text to the actual picture edges, rather than the video edges.
    picture_top = (H - round(W / picture_ratio)) // 2
    picture_bottom = H - picture_top
    positions = {
        'Heading': (2, W // 2, picture_top - 56 - 56 - 24),
        'Subheading': (2, W // 2, picture_top - 56),
        'Footnote': (9, W - 70, picture_bottom + 28),
    }
    overlay_end = _fmt_ass_time(max(duration, max((float(s.get('end', 0)) for s in segments), default=0)))
    for style, value in (("Heading", title), ("Subheading", subtitle), ("Footnote", footnote)):
        if value:
            placement = ''
            if landscape_layout:
                alignment, x, y = positions[style]
                base_size = {'Heading': 92, 'Subheading': 56, 'Footnote': 32}[style]
                units = sum(1 if unicodedata.east_asian_width(c) in 'WF' else 0.6 for c in value)
                spacing = 2 if style == 'Heading' else 0
                size = min(base_size, int((W - 160 - spacing * len(value)) / max(1, units)))
                placement = rf'{{\an{alignment}\pos({x},{y})\fs{size}\q2}}'
            lines.append(f"Dialogue: 1,0:00:00.00,{overlay_end},{style},,0,0,0,,{placement}{_escape_ass(value)}\n")
    for seg in segments:
        start = _fmt_ass_time(float(seg.get("start", 0)))
        end = _fmt_ass_time(float(seg.get("end", 0)))
        text = _escape_ass(str(seg.get("text", "")))
        if text:
            pos = r"{\an5\pos(540," + str(round(H * subtitle_y)) + ")}"
            lines.append(f"Dialogue: 2,{start},{end},Default,,0,0,0,,{pos}{text}\n")
    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _prepare_title_font(requested: str, fonts_dir: str, *, use_configured: bool = True) -> tuple[str, bool]:
    """Load only installed fonts or the operator-configured title font file."""
    from PIL import ImageFont
    configured = os.environ.get('RENDER_TITLE_FONT_FILE', '').strip() if use_configured else ''
    aliases = {
        'KaiTi': r'C:\Windows\Fonts\simkai.ttf',
        'Microsoft YaHei': r'C:\Windows\Fonts\msyhbd.ttc',
        'SimSun': r'C:\Windows\Fonts\simsun.ttc',
        'SimHei': r'C:\Windows\Fonts\simhei.ttf',
    }
    source = configured or aliases.get(requested, '')
    fallback = not source or not Path(source).is_file()
    if fallback:
        source = _find_cjk_font(calligraphy=True)
    if Path(source).suffix.lower() not in {'.ttf', '.otf', '.ttc'}:
        raise ValueError('标题字体文件须为 TTF、OTF 或 TTC')
    family = ImageFont.truetype(source, 32).getname()[0]
    Path(fonts_dir).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, Path(fonts_dir) / Path(source).name)
    return family, fallback


def _render_text_settings(stage: dict, book: dict, rewrite: dict) -> dict:
    params = stage.get('params') or {}
    is_guoxue = params.get('production_template') == 'guoxue-v1'
    configured = params.get('video_text')
    configured = configured if isinstance(configured, dict) else {}
    main = str(params.get('main_title') or (
        rewrite.get('cover_title') if rewrite.get('cover_confirmed') else ''
    ) or book.get('publish_title') or book.get('title_short') or book.get('book_name') or '').strip()
    sub = str(params.get('subtitle') or (
        rewrite.get('cover_subtitle') if rewrite.get('cover_confirmed') else ''
    ) or '').strip()
    return {
        'title': str(configured.get('title', main)).strip(),
        'subtitle': str(configured.get('subtitle', sub)).strip(),
        'footnote': str(configured.get('footnote', params.get('footnote', '读书分享'))).strip(),
        'title_font': str(params.get('title_font') or (os.environ.get('RENDER_TITLE_FONT', 'PlayFont-ChenkunGBT') if is_guoxue else 'KaiTi')),
        'title_color': str(params.get('title_color') or (os.environ.get('RENDER_TITLE_COLOR', '#BA413B') if is_guoxue else '#FFF4D9')),
        'subtitle_y': float(params.get('subtitle_y', 2 / 3)),
    }


def _history_cover_text(stage: dict, rewrite: dict) -> tuple[str, str]:
    """The confirmed cover and body share the same explicitly saved text."""
    if rewrite.get('cover_confirmed') is not True:
        return '', ''
    settings = _render_text_settings(stage, {}, rewrite)
    return settings['title'], settings['subtitle']


def _find_cjk_font(bold: bool = False, calligraphy: bool = False) -> str:
    if calligraphy:
        for path in (r"C:\Windows\Fonts\STKAITI.TTF", r"C:\Windows\Fonts\simkai.ttf"):
            if Path(path).exists():
                return path
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


def _font(size: int, bold: bool = False, calligraphy: bool = False):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(_find_cjk_font(bold, calligraphy), size)
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


def _make_layout_frame(
    book_name: str,
    author: str,
    out_png: str,
    *,
    show_book_metadata: bool = True,
    show_disclaimer: bool = True,
    cover_title: str = "",
    cover_subtitle: str = "",
) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (W, H), (18, 20, 24))
    draw = ImageDraw.Draw(image)
    title = f"《{book_name.strip('《》')}》" if book_name.strip("《》") else ""
    title_font = _font(TITLE_FONT_SIZE if len(title) <= 18 else 72, bold=True)
    author_font = _font(AUTHOR_FONT_SIZE)
    disclaimer_font = _font(DISCLAIMER_FONT_SIZE)

    if show_book_metadata and (title or author.strip()):
        title_lines = _wrap_text(draw, title, title_font, W - 120, max_lines=2) if title else []
        author_text = f"作者：{author}" if author.strip() else ""
        author_box = draw.textbbox((0, 0), author_text, font=author_font) if author_text else (0, 0, 0, 0)
        author_height = author_box[3] - author_box[1]
        author_y = 120 if PHOTO_Y <= 0 else PHOTO_Y - AUTHOR_TO_PHOTO_GAP - author_height
        title_heights = [draw.textbbox((0, 0), line, font=title_font)[3] for line in title_lines]
        title_block_height = sum(title_heights) + 10 * max(0, len(title_lines) - 1)
        title_y = 40 if PHOTO_Y <= 0 else author_y - TITLE_AUTHOR_GAP - title_block_height
        if title_lines:
            _draw_centered_lines(draw, title_lines, title_font, title_y, (255, 255, 255), spacing=10)
        if author_text:
            draw.text(
                ((W - (author_box[2] - author_box[0])) // 2, author_y),
                author_text,
                font=author_font,
                fill=(224, 228, 234),
            )

    draw.line((0, PHOTO_Y - 1, W, PHOTO_Y - 1), fill=(55, 60, 68), width=1)
    draw.line((0, PHOTO_Y + PHOTO_H, W, PHOTO_Y + PHOTO_H), fill=(55, 60, 68), width=1)
    if show_disclaimer:
        disclaimer_lines: list[str] = []
        disclaimer_source = _disclaimer_text(book_name) if show_book_metadata and book_name.strip() else "本视频内容基于公开资料整理，仅用于科普分享。"
        for raw_line in disclaimer_source.splitlines():
            disclaimer_lines.extend(_wrap_text(draw, raw_line, disclaimer_font, W - 120, max_lines=2))
        disclaimer_heights = [draw.textbbox((0, 0), line, font=disclaimer_font)[3] for line in disclaimer_lines]
        disclaimer_block_height = sum(disclaimer_heights) + 10 * max(0, len(disclaimer_lines) - 1)
        disclaimer_y = PHOTO_Y + PHOTO_H + DISCLAIMER_GAP_LINES * DISCLAIMER_FONT_SIZE
        if disclaimer_y + disclaimer_block_height > H - 30:
            disclaimer_y = H - 30 - disclaimer_block_height
        _draw_centered_lines(draw, disclaimer_lines, disclaimer_font, disclaimer_y, _disclaimer_fill(), spacing=10)
    if cover_title.strip() or cover_subtitle.strip():
        cover_font = _font(88, calligraphy=True)
        sub_font = _font(52, calligraphy=True)
        yellow = (248, 211, 72)
        if cover_title.strip():
            lines = _wrap_text(draw, cover_title.strip(), cover_font, W - 160, max_lines=2)
            y = 150
            for line in lines:
                box = draw.textbbox((0, 0), line, font=cover_font, stroke_width=2)
                draw.text(((W - (box[2] - box[0])) // 2, y), line, font=cover_font, fill=yellow, stroke_width=2, stroke_fill=(8, 8, 8))
                y += box[3] - box[1] + 12
        if cover_subtitle.strip():
            lines = _wrap_text(draw, cover_subtitle.strip(), sub_font, W - 180, max_lines=2)
            y = 330
            for line in lines:
                box = draw.textbbox((0, 0), line, font=sub_font, stroke_width=2)
                draw.text(((W - (box[2] - box[0])) // 2, y), line, font=sub_font, fill=yellow, stroke_width=2, stroke_fill=(8, 8, 8))
                y += box[3] - box[1] + 10
    image.save(out_png, "PNG")


def _is_landscape_art(img_path: str) -> bool:
    from PIL import Image
    with Image.open(img_path) as source:
        return any(abs(source.width / source.height - ratio) < 0.02 for ratio in (1, 4 / 3))


def _landscape_composition_graph(picture_ratio: float = 4/3) -> str:
    """Keep the complete landscape artwork; only the backdrop is cropped/blurred."""
    foreground_h = round(W / picture_ratio)
    foreground_y = (H - foreground_h) // 2
    return (
        '[0:v]split=2[bgsource][fgsource];'
        f'[bgsource]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,'
        f'crop={W}:{H},gblur=sigma=36:steps=2,eq=brightness=-0.08[blurred];'
        f'[fgsource]scale={W}:{foreground_h}:force_original_aspect_ratio=decrease:flags=lanczos,'
        f'pad={W}:{foreground_h}:(ow-iw)/2:(oh-ih)/2:color=0xe4dfd3[foreground];'
        f'[blurred][foreground]overlay=0:{foreground_y}:shortest=1,setsar=1,format=yuv420p[v]'
    )


def _make_landscape_clip(img_path: str, duration: float, out_mp4: str, *, motion: str | None = None, picture_ratio: float = 4/3) -> None:
    # Bake the blurred backdrop once; animate only the foreground viewport.
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    foreground_h = round(W / picture_ratio)
    foreground_y = (H - foreground_h) // 2
    still_path = str(Path(out_mp4).with_suffix('.png'))
    with Image.open(img_path) as source:
        source = source.convert('RGB')
        background = ImageOps.fit(source, (W, H), method=Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(36))
        background = ImageEnhance.Brightness(background).enhance(0.92)
        foreground = ImageOps.contain(source, (W, foreground_h), method=Image.Resampling.LANCZOS)
        panel = Image.new('RGB', (W, foreground_h), '#e4dfd3')
        panel.paste(foreground, ((W - foreground.width) // 2, (foreground_h - foreground.height) // 2))
        if motion is None:
            background.paste(panel, (0, foreground_y))
        background.save(still_path, format='PNG')
    try:
        if motion is not None:
            if motion not in ('zoom_in', 'zoom_out'):
                raise ValueError(f'Unsupported landscape motion: {motion}')
            frames = max(2, round(duration * FPS))
            # Constant speed stays perceptible during 25-40 second shots.
            easing = f'(on/{frames - 1})'
            progress = easing if motion == 'zoom_in' else f'(1-{easing})'
            graph = (
                f'[1:v]scale={W * LANDSCAPE_WORK_SCALE}:{foreground_h * LANDSCAPE_WORK_SCALE}:force_original_aspect_ratio=increase:flags=lanczos,'
                f'crop={W * LANDSCAPE_WORK_SCALE}:{foreground_h * LANDSCAPE_WORK_SCALE},format=yuv444p,'
                f"zoompan=z='1+{LANDSCAPE_ZOOM_AMOUNT}*{progress}':"
                "x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
                f'd={frames}:s={W * LANDSCAPE_RENDER_SCALE}x{foreground_h * LANDSCAPE_RENDER_SCALE}:fps={FPS},'
                f'scale={W}:{foreground_h}:flags=lanczos[photo];'
                f'[0:v][photo]overlay=0:{foreground_y}:shortest=1,setsar=1,format=yuv420p[v]'
            )
            _run_ffmpeg([
                ff(), '-y', '-loop', '1', '-framerate', str(FPS), '-i', still_path,
                '-i', img_path, '-filter_complex', graph, '-map', '[v]',
                '-frames:v', str(frames), *_encoder_args(intermediate=True),
                '-r', str(FPS), '-an', out_mp4,
            ], check=True, capture_output=True)
            return
        _run_ffmpeg([
            ff(), '-y', '-loop', '1', '-framerate', str(FPS), '-i', still_path,
            '-frames:v', str(max(1, round(duration * FPS))),
            *_encoder_args(intermediate=True), '-r', str(FPS), '-an', out_mp4,
        ], check=True, capture_output=True)
    finally:
        Path(still_path).unlink(missing_ok=True)


def _make_cover_clip(img_path: str, layout_path: str, duration: float, out_mp4: str, *, frame_mode: str | None = None, picture_ratio: float = 4/3) -> None:
    """Hold the first image frame as the short cover instead of a title card."""
    if frame_mode == 'landscape_blur' or (frame_mode is None and _is_landscape_art(img_path)):
        return _make_landscape_clip(img_path, duration, out_mp4, picture_ratio=picture_ratio)
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
        *_encoder_args(intermediate=True), "-r", str(FPS), "-an", out_mp4,
    ], check=True, capture_output=True)


def _make_image_clip(img_path: str, layout_path: str, duration: float, out_mp4: str, *, frame_mode: str | None = None, shot_index: int = 0, picture_ratio: float = 4/3) -> None:
    if frame_mode == 'landscape_blur' or (frame_mode is None and _is_landscape_art(img_path)):
        return _make_landscape_clip(img_path, duration, out_mp4, motion='zoom_in' if shot_index % 2 == 0 else 'zoom_out', picture_ratio=picture_ratio)
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
        "-frames:v", str(frames), *_encoder_args(intermediate=True),
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
    # Subtitle defects are reported by quality.py but do not block a usable
    # render. Audio/video integrity and the image timeline remain hard gates.


def _timeline_clip_durations(timeline: list[dict]) -> list[float]:
    """Add dissolve overlap while preserving exact final content duration."""
    return [
        round(float(item["duration"]) + (TRANSITION_DUR if index < len(timeline) - 1 else 0.0), 3)
        for index, item in enumerate(timeline)
    ]


def _exact_timeline_durations(timeline: list[dict]) -> list[float]:
    """Timeline v3 uses hard visual boundaries so audio and images never drift."""
    return [round(float(item["duration"]), 3) for item in timeline]


def _select_timeline_clip_durations(timeline: list[dict], audio_duration: float) -> list[float]:
    """Reserve transition overlap only when the selected path applies dissolves."""
    if _use_dissolve(len(timeline), audio_duration):
        return _timeline_clip_durations(timeline)
    return _exact_timeline_durations(timeline)


def _use_dissolve(image_count: int, duration: float) -> bool:
    """Bound cumulative re-encoding by both clip count and actual video length."""
    return image_count <= config.RENDER_DISSOLVE_MAX_CLIPS and duration <= config.RENDER_DISSOLVE_MAX_DURATION


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
        "".join(f"file '{Path(clip).resolve().as_posix()}'\n" for clip in clips),
        encoding="utf-8",
    )
    _run_ffmpeg([
        ff(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-c:v", "copy", out_mp4,
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
                *_encoder_args(intermediate=True), "-r", str(FPS), "-an", output,
            ], check=True, capture_output=True)
            merged.append((output, expected))
        nodes = merged
        round_index += 1
    shutil.copyfile(nodes[0][0], out_mp4)


def _concat_intro(intro: str, content: str, out_mp4: str, tmpdir: str) -> None:
    # Both inputs were encoded with the same frame size, rate and codec.
    # Joining their packets avoids re-encoding the whole film just for 0.5s.
    expected = _video_duration(intro) + _video_duration(content)
    _concat_clips_exact([intro, content], expected, out_mp4, tmpdir)


def run(stage: dict) -> tuple[str, str | None]:
    validate_template(stage.get('params') or {}, 'render')
    validate_task_template(stage)
    if (stage.get('params') or {}).get('production_template') == 'scene-v1':
        from scene_render import run as run_scene
        return run_scene(stage)
    global _ACTIVE_DEADLINE
    task_id = stage["task_id"]
    render_started = time.monotonic()
    phase_seconds = {}
    _ACTIVE_DEADLINE = time.monotonic() + max(1.0, float(config.RENDER_TIMEOUT))
    print(f"  [render] 编码器：{'NVIDIA NVENC' if _nvenc_available() else 'CPU x264'}", flush=True)
    print("  [render] 读取图片索引", flush=True)
    images_data = _load_json_artifact(task_id, "image_index")
    print("  [render] 读取字幕时间轴", flush=True)
    subs_data = _load_json_artifact(task_id, "subtitle")
    print("  [render] 读取书籍信息", flush=True)
    book_data = _load_json_artifact(task_id, "book")
    print("  [render] 下载完整配音", flush=True)
    audio_path = _load_audio(task_id)
    audio_stage = db.get_client().table('stages').select('status,params,output_ref').eq('task_id',task_id).eq('kind','tts').single().execute().data or {}
    if (audio_stage.get('params') or {}).get('audio_source') == 'external':
        if audio_stage.get('status') != 'done':
            raise ValueError('当前外部配音尚未确认')
        row = db.get_client().table('external_narrations').select('state,audio_path,subtitle_path,review').eq('id',audio_stage['params']['external_id']).single().execute().data or {}
        if not row.get('audio_path') and (row.get('review') or {}).get('audio_expired_at'):
            raise ValueError('配音文件已按 48 小时保留规则清理；请重新上传配音后再成片')
        if row.get('state') != 'approved' or row.get('audio_path') != audio_stage.get('output_ref'):
            raise ValueError('配音版本已变化，请重新确认')
        if audio_path:
            Path(audio_path).unlink(missing_ok=True)
        audio_path = storage.download_artifact(row['audio_path'], Path(row['audio_path']).suffix or '.wav')
        local_subs = storage.download_artifact(row['subtitle_path'], '.json')
        try:
            subs_data = json.loads(Path(local_subs).read_text(encoding='utf-8'))
        finally:
            Path(local_subs).unlink(missing_ok=True)
    bgm_path, bgm_volume, narration_volume = _load_bgm_config(task_id)

    if not images_data or not audio_path:
        db.set_stage(stage["id"], "failed", error="缺少图片或音频产物（请确认 image/tts 阶段已完成）")
        return "failed", None

    images: list[dict] = _apply_image_replacements(task_id, images_data if isinstance(images_data, list) else [])
    expected_template = (stage.get('params') or {}).get('production_template')
    picture_aspect = ('1:1' if (stage.get('params') or {}).get('template_version') == 2 else '4:3') if expected_template == 'guoxue-v1' else '4:3'
    picture_ratio = 1.0 if picture_aspect == '1:1' else 4/3
    if expected_template == 'guoxue-v1' and any(image.get('cell_ratio') not in (None,picture_aspect) for image in images):
        raise ValueError(f'已有图片比例与国学{picture_aspect}模板不一致，请重新生图；旧成片已保留')
    segments: list[dict] = subs_data.get("segments", []) if isinstance(subs_data, dict) else []
    tts_duration = float(subs_data.get("duration", 0.0) if isinstance(subs_data, dict) else 0.0) or 1.0
    task_context = db.get_task_prompt_context(task_id)
    is_history = str(task_context.get("content_category") or "health") == "social_science"
    rewrite_data = _load_json_artifact(task_id, "rewrite") if is_history else {}
    book_name = str(book_data.get("book_name", "") if isinstance(book_data, dict) else "")
    author = str(book_data.get("author", "") if isinstance(book_data, dict) else "")

    tmpdir = tempfile.mkdtemp(prefix="render_")
    try:
        if not os.path.exists(audio_path):
            raise ValueError("配音临时文件不存在，已停止渲染")
        audio_local = os.path.join(tmpdir, "tts.mp3")
        shutil.copyfile(audio_path, audio_local)
        bgm_local = storage.download_artifact(bgm_path, os.path.splitext(bgm_path)[1] or ".mp3") if bgm_path else None
        if not images:
            db.set_stage(stage["id"], "failed", error="图片列表为空")
            return "failed", None
        layout_png = os.path.join(tmpdir, "layout.png")
        _make_layout_frame(
            book_name,
            author,
            layout_png,
            show_book_metadata=not is_history,
            show_disclaimer=not is_history,
        )
        cover_layout_png = layout_png
        if is_history:
            paragraphs = rewrite_data.get("paragraphs") if isinstance(rewrite_data, dict) else []
            if not isinstance(paragraphs, list):
                paragraphs = []
            # History covers use only explicitly confirmed fields. Never infer
            # a title from the first narration sentence or subtitle.
            cover_title, cover_subtitle = _history_cover_text(stage, rewrite_data)
            cover_layout_png = os.path.join(tmpdir, "history_cover_layout.png")
            _make_layout_frame("", "", cover_layout_png, show_book_metadata=False, show_disclaimer=False, cover_title=cover_title, cover_subtitle=cover_subtitle)
        cover_path = images[0].get('cover_path') or images[0]['path']
        cover_local = storage.download_artifact(cover_path, ".png")
        cover_mp4 = os.path.join(tmpdir, "cover.mp4")
        try:
            frame_mode = (stage.get('params') or {}).get('frame_mode')
            landscape_layout = frame_mode == 'landscape_blur' or (frame_mode is None and _is_landscape_art(cover_local))
            _make_cover_clip(cover_local, cover_layout_png, INTRO_DUR, cover_mp4, frame_mode=frame_mode, picture_ratio=picture_ratio)
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
            durations = _select_timeline_clip_durations(timeline, tts_duration)
        else:
            durations = _allocate_durations(images, tts_duration)
            timeline = [
                {"index": index, "path": item.get("path"), "duration": duration}
                for index, (item, duration) in enumerate(zip(images, durations))
            ]

        phase_seconds['prepare_seconds'] = round(time.monotonic() - render_started, 3)
        video_only = os.path.join(tmpdir, "video_only.mp4")
        cached = None
        try:
            revision = db.get_client().table('artifacts').select('created_at').eq('task_id',task_id).eq('type','image_index').order('created_at',desc=True).limit(1).execute().data
            if revision:
                cached = picture_cache.cache_path(task_id, {
                    'version':'subpixel-linear-zoom-16-v3', 'index_revision':revision[0]['created_at'],
                    'images':images, 'timeline':timeline, 'durations':durations,
                    'frame_mode':frame_mode, 'layout':hashlib.sha256(Path(layout_png).read_bytes()).hexdigest(),
                    'cover_layout':hashlib.sha256(Path(cover_layout_png).read_bytes()).hexdigest(),
                    'encoder': 'nvenc' if _nvenc_available() else config.RENDER_ENCODER_PRESET,
                    'fps':FPS, 'dimensions':[W,H], 'zoom':LANDSCAPE_ZOOM_AMOUNT,
                    'motion_scales':[LANDSCAPE_WORK_SCALE,LANDSCAPE_RENDER_SCALE],
                    'dissolve_limit':config.RENDER_DISSOLVE_MAX_CLIPS,
                    'dissolve_max_duration':config.RENDER_DISSOLVE_MAX_DURATION,
                })
        except Exception:
            pass  # Optional cache must never block rendering.
        cache_hit = bool(cached and picture_cache.restore(cached, video_only))
        if cache_hit:
            try:
                cache_hit = abs(_video_duration(video_only) - (tts_duration + INTRO_DUR)) <= 0.2
            except Exception:
                cache_hit = False
        if cache_hit:
            transition_mode = 'dissolve' if _use_dissolve(len(images), tts_duration) else 'hard_cut_long_timeline'
            phase_seconds.update(image_clips_seconds=0, transitions_seconds=0, intro_join_seconds=0)
            print('  [render] 复用已校验的画面轨，只重新合成文字与配乐', flush=True)
        else:
            phase_started = time.monotonic()
            clip_paths: list[str] = []
            for i, (item, duration) in enumerate(zip(images, durations)):
                _check_deadline()
                image_local = storage.download_artifact(item["path"], ".png")
                clip = os.path.join(tmpdir, f"clip_{i:03d}.mp4")
                try:
                    _make_image_clip(image_local, layout_png, duration, clip, frame_mode=frame_mode, shot_index=i, picture_ratio=picture_ratio)
                finally:
                    try:
                        os.remove(image_local)
                    except OSError:
                        pass
                clip_paths.append(clip)
                if (i + 1) % 10 == 0 or i + 1 == len(images):
                    print(f"  [render] 镜头编码 {i + 1}/{len(images)}", flush=True)

            phase_seconds['image_clips_seconds'] = round(time.monotonic() - phase_started, 3)
            phase_started = time.monotonic()
            content_mp4 = os.path.join(tmpdir, "content.mp4")
            transition_mode = "dissolve"
            if is_timeline_v3:
                if _use_dissolve(len(clip_paths), tts_duration):
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
                if _use_dissolve(len(clip_paths), tts_duration):
                    _compose_with_dissolve(clip_paths, durations, content_mp4)
                else:
                    transition_mode = "hard_cut_long_timeline"
                    cut_durations = [
                        round(float(duration) - (TRANSITION_DUR if i < len(clip_paths) - 1 else 0.0), 3)
                        for i, duration in enumerate(durations)
                    ]
                    _concat_clips_exact(clip_paths, sum(cut_durations), content_mp4, tmpdir)

            print(f"  [render] 镜头合成累计 {time.monotonic() - render_started:.1f}s", flush=True)

            phase_seconds['transitions_seconds'] = round(time.monotonic() - phase_started, 3)
            phase_started = time.monotonic()
            video_only = os.path.join(tmpdir, "video_only.mp4")
            _concat_intro(cover_mp4, content_mp4, video_only, tmpdir)
            phase_seconds['intro_join_seconds'] = round(time.monotonic() - phase_started, 3)
            phase_started = time.monotonic()

            if cached:
                picture_cache.save(cached, video_only)
        phase_started = time.monotonic()

        text_settings = _render_text_settings(stage, book_data if isinstance(book_data,dict) else {}, rewrite_data if isinstance(rewrite_data,dict) else {})
        requested_font = text_settings['title_font']
        template_id = (stage.get('params') or {}).get('production_template')
        text_settings['title_font'], font_fallback = _prepare_title_font(requested_font, os.path.join(tmpdir,'fonts'), use_configured=template_id == 'guoxue-v1')
        if template_id == 'guoxue-v1' and (font_fallback or text_settings['title_font'] != requested_font):
            raise ValueError('国学模板缺少已确认的标题字体，请检查 RENDER_TITLE_FONT_FILE')
        kai_font, _ = _prepare_title_font('KaiTi', os.path.join(tmpdir,'fonts'), use_configured=False)
        text_settings['subtitle_font'] = kai_font
        text_settings['narration_font'] = text_settings['title_font'] if landscape_layout else 'Microsoft YaHei'
        text_settings['footnote_font'] = kai_font if landscape_layout else 'Microsoft YaHei'
        _make_ass(segments, os.path.join(tmpdir, "subs.ass"), duration=tts_duration, landscape_layout=landscape_layout, picture_ratio=picture_ratio, **text_settings)
        print("  [render] 合成字幕与完整配音", flush=True)
        final = os.path.join(tmpdir, "final.mp4")
        render_args = [
            ff(), "-y", "-i", video_only,
            "-itsoffset", str(INTRO_DUR), "-i", audio_local,
        ]
        if bgm_local:
            render_args.extend(["-stream_loop", "-1", "-i", bgm_local])
        mix_filter = _audio_mix_filter(
            bool(bgm_local), bgm_volume, narration_volume, tts_duration + INTRO_DUR
        )
        audio_label = "[audio]" if bgm_local else "[narration]"
        upload_limit = storage.upload_limit_bytes()
        target_kbps = _storage_safe_video_bitrate(tts_duration + INTRO_DUR, max_bytes=upload_limit)
        render_args.extend([
            "-filter_complex", mix_filter,
            "-vf", "ass=subs.ass:fontsdir=fonts",
            *_encoder_args(target_kbps=target_kbps),
            "-map", "0:v:0", "-map", audio_label,
            "-c:a", "aac", "-b:a", "64k", "-shortest", final,
        ])
        _run_ffmpeg(render_args, check=True, capture_output=True, cwd=tmpdir)
        print(f"  [render] 字幕音乐合成累计 {time.monotonic() - render_started:.1f}s，文件 {os.path.getsize(final) / 1048576:.1f} MiB", flush=True)
        if os.path.getsize(final) > upload_limit:
            smaller = os.path.join(tmpdir, 'final_compact.mp4')
            compact_kbps = _storage_safe_video_bitrate(tts_duration + INTRO_DUR, 36, max_bytes=upload_limit)
            _run_ffmpeg([
                ff(), '-y', '-i', final, '-map', '0:v:0', '-map', '0:a:0',
                *_encoder_args(target_kbps=compact_kbps), '-c:a', 'copy', smaller,
            ], check=True, capture_output=True)
            os.replace(smaller, final)
            print(f"  [render] 存储限额压缩后 {os.path.getsize(final) / 1048576:.1f} MiB", flush=True)
        if os.path.getsize(final) > upload_limit:
            raise ValueError('成片自动压缩后仍超过当前存储安全上限，请缩短视频或分段')

        phase_seconds['text_audio_encode_seconds'] = round(time.monotonic() - phase_started, 3)
        phase_started = time.monotonic()
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
        phase_seconds['quality_seconds'] = round(time.monotonic() - phase_started, 3)
        print('  [render-timings] ' + json.dumps(phase_seconds), flush=True)
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
        quality_needs_review = quality_report["status"] == "failed"
        failed_labels = [
            check["label"] for check in quality_report["checks"]
            if check["status"] == "failed"
        ]

        timeline_path = f"{task_id}/render_timeline.json"
        storage.upload_bytes(
            timeline_path,
            json.dumps(timeline, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json",
        )
        storage.add_artifact(task_id, "render", "timeline", timeline_path, meta={
            "image_count": len(timeline), "duration": tts_duration, "version": 3 if is_timeline_v3 else 2,
        })

        # Immutable media paths prevent browsers/CDN serving an older rerender.
        sp = f"{task_id}/renders/{uuid.uuid4()}/final.mp4"
        storage.upload(sp, final, "video/mp4")
        storage.add_artifact(task_id, "render", "final", sp, meta={
            "width": W,
            "phase_seconds": phase_seconds,
            "picture_track_cache_hit": cache_hit,
            "production_template": template_id or 'legacy',
            "height": H,
            "tts_duration": tts_duration,
            "image_count": len(images),
            "intro_duration": INTRO_DUR,
            "cover": "independent_cover" if images[0].get('cover_path') else "first_image_frame",
            "cover_frames": COVER_FRAMES,
            "motion": "alternating_zoom_in_out" if landscape_layout else "zoom_in",
            "zoom_amount": LANDSCAPE_ZOOM_AMOUNT if landscape_layout else ZOOM_AMOUNT,
            "zoom_oversample": LANDSCAPE_WORK_SCALE if landscape_layout else ZOOM_OVERSAMPLE,
            "motion_render_scale": LANDSCAPE_RENDER_SCALE if landscape_layout else 1,
            "transition": transition_mode,
            "transition_duration": TRANSITION_DUR,
            "timeline_version": 3 if is_timeline_v3 else 2,
            "layout": "guoxue_landscape_blur" if landscape_layout else "book_header_photo_subtitles_disclaimer",
            "text_layout": {**text_settings, 'requested_font': requested_font, 'font_fallback': font_fallback,
                            'landscape_layout': landscape_layout, 'picture_aspect_ratio': picture_aspect if landscape_layout else None,
                            'picture_text_gap': {'above': 56, 'below': 28} if landscape_layout else None},
            "encoding_crf": config.RENDER_CRF,
            "encoding_video_bitrate_kbps": target_kbps,
            "file_size_bytes": os.path.getsize(final),
            "disclaimer_font_size": DISCLAIMER_FONT_SIZE,
            "disclaimer_opacity": DISCLAIMER_OPACITY,
            "quality_status": quality_report["status"],
            "quality_report": quality_path,
            "bgm_enabled": bool(bgm_local),
            "bgm_volume": bgm_volume if bgm_local else None,
            "narration_volume": narration_volume,
        })
        if quality_needs_review:
            review_error = f"自动质检未通过：{'、'.join(failed_labels)}"
            db.set_stage(stage["id"], "needs_review", output_ref=sp, error=review_error)
            print(f"  [REVIEW] render needs_review; 成片已保留 ({review_error})", flush=True)
            return "needs_review", sp
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
        if 'bgm_local' in locals() and bgm_local and os.path.exists(bgm_local):
            try:
                os.remove(bgm_local)
            except OSError:
                pass
