"""Shorten long, truly silent gaps in uploaded narration before alignment."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import imageio_ffmpeg


POLICY = 'cap_internal_silence_1s_v1'
_START = re.compile(r'silence_start:\s*([0-9.]+)')
_END = re.compile(r'silence_end:\s*([0-9.]+)')
_MAX_CUTS = 500


def _silent_runs(decoded: Path) -> list[tuple[float, float]]:
    result = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-nostats', '-i', str(decoded),
        '-af', 'silencedetect=noise=-40dB:d=1.05', '-f', 'null', '-',
    ], capture_output=True, text=True, timeout=360)
    if result.returncode:
        raise RuntimeError('静音检测失败')
    runs: list[tuple[float, float]] = []
    start: float | None = None
    for line in result.stderr.splitlines():
        found_start = _START.search(line)
        if found_start:
            start = float(found_start.group(1))
        found_end = _END.search(line)
        if found_end and start is not None:
            end = float(found_end.group(1))
            if end > start:
                runs.append((start, end))
            start = None
    return runs


def cap_internal_pauses(original: str, decoded: Path, duration: float, output: Path) -> tuple[Path | None, dict]:
    """Keep 0.5 s on each side of a long internal silence; leave speech untouched."""
    report: dict = {'policy': POLICY, 'limit_seconds': 1.0, 'applied': False,
                    'shortened_count': 0, 'removed_seconds': 0.0}
    try:
        runs = _silent_runs(decoded)
        cuts = [(start + 0.5, end - 0.5) for start, end in runs
                if start >= 0.2 and end <= duration - 0.2 and end - start > 1.05]
        if not cuts:
            return None, report
        if len(cuts) > _MAX_CUTS:
            report['note'] = '长停顿过多，已保留原始配音以避免不完整裁切'
            return None, report
        expression = '+'.join(f'between(t\\,{start:.4f}\\,{end:.4f})' for start, end in cuts)
        result = subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-i', original,
            '-map', '0:a:0', '-vn', '-af', f'aselect=not({expression}),asetpts=N/SR/TB',
            '-ac', '1', '-ar', '48000', '-c:a', 'libmp3lame', '-b:a', '192k', str(output),
        ], capture_output=True, timeout=600)
        if result.returncode or not output.exists() or output.stat().st_size == 0:
            raise RuntimeError('停顿压缩未完成')
        report.update(applied=True, shortened_count=len(cuts),
                      removed_seconds=round(sum(end - start for start, end in cuts), 3))
        return output, report
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError):
        output.unlink(missing_ok=True)
        report['note'] = '静音优化未完成，已安全保留原始配音'
        return None, report
