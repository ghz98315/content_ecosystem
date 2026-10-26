"""Read-only local stock library adapter for approved, externally narrated tasks.

Only contact frames and the edit decision list are uploaded. Source MP4 files
remain on the Worker machine and are checked again immediately before render.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

import imageio_ffmpeg

import db
import storage
from narration import clean_tts_text, visible_len
from stock_processing import motion_probe, settings
from stock_timing import timed_blocks

DEFAULT_ROOT = r"D:\Obsidian\99_剪映素材库\剪映公用素材库"
FOLDERS = {
    "guoxue": ("20_国学", "10_通用画面"),
    "health": ("30_健康", "10_通用画面"),
    "scene": ("40_城市场景", "10_通用画面"),
}
# Checked at three points in the source. These contain prominent baked-in
# lettering or a phone interface, so they must not enter automated selection.
EXCLUDED_NAMES = {
    "13437496578829092.mp4", "13437497502513749.mp4",
    "13437497479368540.mp4",
}


def library_root() -> Path:
    root = Path(os.environ.get("LOCAL_MEDIA_LIBRARY_ROOT", DEFAULT_ROOT)).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("本地素材库目录不存在")
    return root


def resolve_asset(asset: dict) -> Path:
    """Never trust a path supplied through task params or a saved edit list."""
    root = library_root()
    relative = str(asset.get("relative_path") or "")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("本地素材路径无效")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root) or path.suffix.lower() != ".mp4" or not path.is_file():
        raise ValueError("素材文件超出允许的本地素材库")
    if path.parent.name == "00_待整理":
        raise ValueError("待整理素材不能用于成片")
    expected_size = asset.get("bytes")
    if expected_size is not None and path.stat().st_size != int(expected_size):
        raise ValueError("本地素材已改变，请重新检查并选片")
    return path


def probe(path: Path) -> tuple[float, int, int]:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=12)
    duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    video = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", result.stderr)
    if not duration or not video:
        raise ValueError(f"素材视频无法读取：{path.name}")
    hours, minutes, seconds = duration.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds), int(video[1]), int(video[2])


def scan(category: str) -> list[dict]:
    root = library_root()
    folders = FOLDERS.get(category, FOLDERS["guoxue"])
    assets = []
    for folder in folders:
        for path in sorted((root / folder).glob("*.mp4")):
            if path.name in EXCLUDED_NAMES or path.is_symlink():
                continue
            try:
                duration, width, height = probe(path)
                if duration < 8 or min(width, height) < 540:
                    continue
                relative = path.relative_to(root).as_posix()
                assets.append({
                    "id": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16],
                    "provider": "local_library", "media_type": "video",
                    "relative_path": relative, "title": f"{folder} · {path.stem}",
                    "tags": folder, "page": "本地素材库", "author": "用户提供",
                    "license": "按素材库授权记录", "license_url": "",
                    "duration": duration, "width": width, "height": height,
                    "bytes": path.stat().st_size,
                })
            except (OSError, ValueError, subprocess.TimeoutExpired):
                continue
    if not assets:
        raise ValueError("本地素材库没有可用视频")
    return assets


def plan(text: str, subtitles: dict, category: str) -> list[dict]:
    """Deterministic, non-random continuous excerpts; keep narration intact."""
    from stages import render

    duration = float(subtitles["duration"])
    parts = timed_blocks(text, subtitles, target=43, minimum=34, maximum=55)
    # A tiny trailing clip feels like a glitch. Attach it to its predecessor.
    if len(parts) > 1:
        prefix = sum(visible_len(part) for part in parts[:-1])
        if duration - render._cue_time_at_char(prefix, subtitles["segments"], duration) < 12:
            parts[-2] += parts[-1]
            parts.pop()
    cursor = 0
    sketches = []
    for part in parts:
        size = visible_len(part)
        sketches.append({"index": len(sketches), "sentence": part, "char_start": cursor,
                         "char_end": cursor + size, "char_count": size, "path": "pending"})
        cursor += size
    timeline = render._build_timeline(sketches, subtitles["segments"], duration)
    for sketch, timing in zip(sketches, timeline):
        sketch.update(start=timing["start"], end=timing["end"], duration=timing["duration"])

    assets = scan(category)
    used: dict[str, int] = {}
    result = []
    for index, sketch in enumerate(sketches):
        wanted = float(sketch["duration"])
        options = []
        for asset in assets:
            for rate in (1.0, 0.5, 0.3):
                if asset["duration"] >= wanted * rate + .25:
                    last = used.get(asset["id"], -100)
                    if index - last <= 2:
                        continue
                    # Prefer fresh footage, normal speed and diverse folders.
                    preferred = FOLDERS.get(category, FOLDERS["guoxue"])[index % 2]
                    score = (int(last >= 0) * 20 + (0 if rate == 1 else 4 if rate == .5 else 12)
                             + (0 if asset["relative_path"].startswith(preferred) else 2)
                             + int(asset["duration"] < wanted + 2) * 2)
                    options.append((score, asset["id"], asset, rate))
                    break
        if not options:
            raise ValueError(f"第 {index + 1} 段没有足够时长的本地视频")
        _, _, asset, rate = min(options)
        used[asset["id"]] = index
        source_duration = wanted * rate
        source_start = 0.0 if asset["duration"] < source_duration + 8 else min(
            max(0.0, asset["duration"] - source_duration - .2),
            round(asset["duration"] * .12, 2),
        )
        result.append({**sketch, "asset": asset, "source_start": source_start,
                       "source_end": source_start + source_duration, "playback_rate": rate,
                       "processing": settings({"color_style": "natural_warm_v1", "feather": 36})})
    return result


def check_excerpt(entry: dict) -> dict:
    path = resolve_asset(entry["asset"])
    actual, width, height = probe(path)
    source_duration = entry["duration"] * entry["playback_rate"]
    if actual - entry["source_start"] < source_duration - .05:
        raise ValueError(f"源片时长不足：{path.name}")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    start = float(entry["source_start"])
    probes = [motion_probe(path, ff, start, min(8, source_duration)),
              motion_probe(path, ff, start + max(0, source_duration - 8), min(8, source_duration))]
    if all(item.get("state") == "nearly_static" for item in probes):
        raise ValueError(f"所选片段几乎静止：{path.name}")
    return {"source_width": width, "source_height": height,
            "motion_check": probes, "source_duration": round(actual, 2)}


def run(stage: dict) -> tuple[str, str | None]:
    from stages.image import _find_chosen_text
    from stock_media import load_audio_timeline

    task = stage["task_id"]
    text = clean_tts_text(_find_chosen_text(task, stage) or "")
    if not text:
        raise ValueError("缺少已确认文案")
    subtitles = load_audio_timeline(task)
    category = str((stage.get("params") or {}).get("content_line") or "guoxue")
    entries = plan(text, subtitles, category)
    revision = uuid.uuid4().hex
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    aspect = str((stage.get("params") or {}).get("image_aspect_ratio") or "1:1")
    width, height = (960, 720) if aspect == "4:3" else (720, 720)
    scratch = Path(__file__).resolve().parent / "output"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="local-materials-", dir=scratch) as directory:
        for entry in entries:
            entry.update(check_excerpt(entry))
            source = resolve_asset(entry["asset"])
            preview = Path(directory) / f"{entry['index']:03}.jpg"
            # Preview is the exact center-cropped composition used by the render.
            command = [ff, "-y", "-loglevel", "error", "-ss",
                       str(entry["source_start"] + entry["duration"] * entry["playback_rate"] / 2),
                       "-i", str(source), "-frames:v", "1", "-vf",
                       f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}", str(preview)]
            subprocess.run(command, check=True, capture_output=True, timeout=30)
            path = f"{task}/stock/local-{revision}/preview-{entry['index']:03}.jpg"
            storage.upload(path, str(preview), "image/jpeg")
            storage.add_artifact(task, "image", "image", path,
                                 meta={"visual_mode": "stock_video", "source": "local_library"})
            entry.update(path=path, cell_ratio=aspect, visual_type="video", motion="source_motion")
    prefix = f"{task}/stock/local-{revision}"
    index_path = prefix + "/index.json"
    storage.upload_bytes(index_path, json.dumps(entries, ensure_ascii=False).encode("utf-8"),
                         "application/json")
    storage.add_artifact(task, "image", "video_index", index_path,
                         meta={"visual_mode": "stock_video", "source": "local_library", "count": len(entries)})
    return "done", index_path
