"""TTS provider boundary; production currently defaults to Edge TTS."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from typing import Protocol

import imageio_ffmpeg


class TTSProvider(Protocol):
    async def synthesize(self, text: str, voice: str) -> tuple[bytes, list[dict], float]:
        """Return audio bytes, provider boundaries, and decoded duration."""


def _probe_duration(path: str, segments: list[dict]) -> float:
    try:
        result = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-i", path, "-map", "0:a:0",
             "-f", "null", "-", "-progress", "pipe:1", "-nostats"],
            check=True, capture_output=True, text=True,
        )
        values = re.findall(r"out_time_us=(\d+)", result.stdout)
        if values:
            return round(int(values[-1]) / 1_000_000, 3)
    except (subprocess.CalledProcessError, ValueError):
        pass
    return float(segments[-1].get("end", 0.0)) if segments else 0.0


class EdgeTTSProvider:
    async def synthesize(self, text: str, voice: str) -> tuple[bytes, list[dict], float]:
        import edge_tts

        fd_mp3, mp3_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd_mp3)
        segments: list[dict] = []
        try:
            comm = edge_tts.Communicate(text, voice, boundary="SentenceBoundary")
            with open(mp3_path, "wb") as output:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        output.write(chunk["data"])
                    elif chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                        segments.append({
                            "text": chunk.get("text", ""),
                            "start": round(chunk["offset"] / 1e7, 3),
                            "end": round((chunk["offset"] + chunk["duration"]) / 1e7, 3),
                        })
            with open(mp3_path, "rb") as source:
                return source.read(), segments, _probe_duration(mp3_path, segments)
        finally:
            try:
                os.remove(mp3_path)
            except OSError:
                pass


def get_tts_provider(name: str | None = None) -> TTSProvider:
    provider = (name or os.environ.get("TTS_PROVIDER", "edge")).strip().lower()
    if provider in {"edge", "edge-tts"}:
        return EdgeTTSProvider()
    raise ValueError(
        f"未适配的 TTS Provider: {provider}。当前可用 provider 为 edge；"
        "CosyVoice2 需完成独立适配和试听验证后启用。"
    )
