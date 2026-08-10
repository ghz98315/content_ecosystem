"""Automatic technical quality checks for rendered videos."""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone

from narration import has_disallowed_subtitle_punctuation, visible_len


EXPECTED_STAGES = (
    "ingest", "transcribe", "clean", "rewrite", "image", "book", "tts", "render",
)


def _check(check_id: str, label: str, status: str, detail: str, **values) -> dict:
    result = {"id": check_id, "label": label, "status": status, "detail": detail}
    result.update(values)
    return result


def probe_media(path: str, ffmpeg_path: str) -> dict:
    """Read container metadata using the bundled ffmpeg binary."""
    result = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-i", path], capture_output=True, check=False
    )
    output = (result.stderr or b"").decode("utf-8", errors="ignore")
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
    duration = 0.0
    if duration_match:
        hours, minutes, seconds = duration_match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    video_line = next((line for line in output.splitlines() if " Video: " in line), "")
    size_match = re.search(r"(?<![\d.])(\d{2,5})x(\d{2,5})(?![\d.])", video_line)
    fps_match = re.search(r"([\d.]+)\s+fps\b", video_line)
    return {
        "duration": round(duration, 3),
        "width": int(size_match.group(1)) if size_match else 0,
        "height": int(size_match.group(2)) if size_match else 0,
        "fps": float(fps_match.group(1)) if fps_match else 0.0,
        "has_video": bool(video_line),
        "has_audio": any(" Audio: " in line for line in output.splitlines()),
        "file_size": os.path.getsize(path),
    }


def detect_black_segments(path: str, ffmpeg_path: str) -> list[dict]:
    """Find sustained black frames; short dark cuts are reported as warnings only."""
    try:
        result = subprocess.run(
            [
                ffmpeg_path, "-hide_banner", "-i", path,
                "-vf", "blackdetect=d=0.5:pix_th=0.10", "-an", "-f", "null", os.devnull,
            ],
            capture_output=True,
            check=False,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return [{"error": "blackdetect_timeout"}]
    output = (result.stderr or b"").decode("utf-8", errors="ignore")
    matches = re.findall(
        r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)",
        output,
    )
    return [
        {"start": float(start), "end": float(end), "duration": float(duration)}
        for start, end, duration in matches
    ]


def evaluate_render_quality(
    *,
    media: dict,
    black_segments: list[dict],
    stage_rows: list[dict],
    images: list[dict],
    cues: list[dict],
    timeline: list[dict],
    tts_duration: float,
    width: int,
    height: int,
    fps: float,
    intro_duration: float,
) -> dict:
    checks: list[dict] = []

    stages = {str(row.get("kind")): str(row.get("status")) for row in stage_rows}
    missing_stages = [kind for kind in EXPECTED_STAGES if kind not in stages]
    bad_stages = [
        kind for kind in EXPECTED_STAGES[:-1] if stages.get(kind) != "done"
    ]
    pipeline_ok = not missing_stages and not bad_stages and stages.get("render") in {"processing", "done"}
    checks.append(_check(
        "pipeline", "流程完整性", "passed" if pipeline_ok else "failed",
        "八个环节及其状态完整" if pipeline_ok else f"缺失环节: {missing_stages or '无'}；未完成前置环节: {bad_stages or '无'}",
        actual=stages, expected="前七个环节完成，成片环节处理中或完成",
    ))

    image_ok = bool(images) and len(images) == len(timeline) and all(item.get("path") for item in images)
    checks.append(_check(
        "images", "图片完整性", "passed" if image_ok else "failed",
        f"{len(images)} 张图片对应 {len(timeline)} 个镜头",
        actual=len(images), expected=len(timeline),
    ))

    max_subtitle_chars = max((visible_len(str(cue.get("text", ""))) for cue in cues), default=0)
    punctuated = sum(
        has_disallowed_subtitle_punctuation(str(cue.get("text", "")))
        for cue in cues
    )
    reversed_cues = sum(float(cue.get("end", 0)) < float(cue.get("start", 0)) for cue in cues)
    forced_cues = sum(str(cue.get("boundary", "")) == "forced" for cue in cues)
    subtitle_ok = (
        bool(cues) and max_subtitle_chars <= 14 and punctuated == 0
        and reversed_cues == 0 and forced_cues == 0
    )
    checks.append(_check(
        "subtitles", "字幕规范", "passed" if subtitle_ok else "failed",
        f"{len(cues)} 条字幕，最长 {max_subtitle_chars} 字，标点异常 {punctuated} 条，拆词异常 {forced_cues} 条",
        actual={
            "count": len(cues), "max_chars": max_subtitle_chars,
            "punctuated": punctuated, "forced_word_cuts": forced_cues,
        },
        expected="字幕非空、每条不超过14字、仅允许成对书名号、无拆词、时间正序",
    ))

    timeline_continuous = bool(timeline)
    if timeline:
        timeline_continuous = (
            abs(float(timeline[0].get("start", 0))) <= 0.02
            and abs(float(timeline[-1].get("end", 0)) - tts_duration) <= 0.03
            and all(
                abs(float(left.get("end", 0)) - float(right.get("start", 0))) <= 0.02
                for left, right in zip(timeline, timeline[1:])
            )
            and all(float(item.get("duration", 0)) >= 0.35 for item in timeline)
        )
    checks.append(_check(
        "timeline", "音画时间轴", "passed" if timeline_continuous else "failed",
        "图片时间轴连续并完整覆盖配音" if timeline_continuous else "图片时间轴存在缺口、重叠或过短镜头",
        actual=round(float(timeline[-1].get("end", 0)), 3) if timeline else 0,
        expected=round(tts_duration, 3),
    ))

    video_ok = bool(media.get("has_video")) and media.get("width") == width and media.get("height") == height
    checks.append(_check(
        "video", "视频规格", "passed" if video_ok else "failed",
        f"{media.get('width', 0)}×{media.get('height', 0)}，{media.get('fps', 0):g} fps",
        actual={"width": media.get("width"), "height": media.get("height"), "fps": media.get("fps")},
        expected={"width": width, "height": height, "fps": fps},
    ))

    fps_ok = abs(float(media.get("fps") or 0) - fps) <= 0.1
    checks.append(_check(
        "fps", "帧率", "passed" if fps_ok else "failed",
        f"实际 {media.get('fps', 0):g} fps，目标 {fps:g} fps",
        actual=media.get("fps", 0), expected=fps,
    ))

    audio_ok = bool(media.get("has_audio"))
    checks.append(_check(
        "audio", "音轨", "passed" if audio_ok else "failed",
        "AAC 音轨存在" if audio_ok else "未检测到音轨",
        actual=audio_ok, expected=True,
    ))

    expected_duration = tts_duration + intro_duration
    duration_delta = abs(float(media.get("duration") or 0) - expected_duration)
    duration_ok = duration_delta <= 0.25
    checks.append(_check(
        "duration", "成片时长", "passed" if duration_ok else "failed",
        f"实际 {media.get('duration', 0):.3f} 秒，目标 {expected_duration:.3f} 秒，偏差 {duration_delta:.3f} 秒",
        actual=media.get("duration", 0), expected=round(expected_duration, 3),
    ))

    file_ok = int(media.get("file_size") or 0) >= 100_000
    checks.append(_check(
        "file", "文件有效性", "passed" if file_ok else "failed",
        f"文件大小 {int(media.get('file_size') or 0):,} 字节",
        actual=int(media.get("file_size") or 0), expected=">=100000",
    ))

    checks.append(_check(
        "black_frames", "持续黑帧", "warning" if black_segments else "passed",
        f"检测到 {len(black_segments)} 段持续黑帧，建议人工确认" if black_segments else "未检测到持续0.5秒以上的黑帧",
        actual=black_segments, expected=[],
    ))

    failed = sum(check["status"] == "failed" for check in checks)
    warnings = sum(check["status"] == "warning" for check in checks)
    status = "failed" if failed else "warning" if warnings else "passed"
    return {
        "version": 1,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"passed": len(checks) - failed - warnings, "warnings": warnings, "failed": failed},
        "checks": checks,
        "metrics": {
            "image_count": len(images),
            "subtitle_count": len(cues),
            "tts_duration": round(tts_duration, 3),
            "video_duration": media.get("duration", 0),
            "file_size": media.get("file_size", 0),
        },
    }


def inspect_render_quality(final_path: str, ffmpeg_path: str, **context) -> dict:
    media = probe_media(final_path, ffmpeg_path)
    black_segments = detect_black_segments(final_path, ffmpeg_path)
    return evaluate_render_quality(media=media, black_segments=black_segments, **context)
