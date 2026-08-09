"""TTS provider boundary; production currently defaults to Edge TTS."""
from __future__ import annotations

import base64
import os
import re
import subprocess
import tempfile
from typing import Protocol

import httpx
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


class CosyVoice2Provider:
    """OpenAI-compatible CosyVoice2 HTTP adapter kept outside production by default."""

    def __init__(self) -> None:
        base_url = (
            os.environ.get("COSYVOICE2_BASE_URL", "").strip()
            or os.environ.get("COSYVOICE_BASE_URL", "").strip()
        ).rstrip("/")
        self.endpoint = (
            os.environ.get("COSYVOICE2_ENDPOINT", "").strip()
            or os.environ.get("COSYVOICE_ENDPOINT", "").strip()
        )
        if not self.endpoint and base_url:
            self.endpoint = f"{base_url}/audio/speech"
        self.api_key = (
            os.environ.get("COSYVOICE2_API_KEY", "").strip()
            or os.environ.get("COSYVOICE_API_KEY", "").strip()
        )
        self.model = (
            os.environ.get("COSYVOICE2_MODEL", "").strip()
            or os.environ.get("COSYVOICE_MODEL", "").strip()
            or "cosyvoice2"
        )
        self.configured_voice = (
            os.environ.get("COSYVOICE2_VOICE", "").strip()
            or os.environ.get("COSYVOICE_VOICE", "").strip()
        )
        self.timeout = max(15.0, float(os.environ.get("COSYVOICE2_TIMEOUT", "120")))

    @staticmethod
    def _decode_json_audio(payload: dict) -> tuple[bytes | None, str | None]:
        value = payload.get("audio_base64") or payload.get("audio")
        if isinstance(value, str):
            if value.startswith(("http://", "https://")):
                return None, value
            if value.startswith("data:") and "," in value:
                value = value.split(",", 1)[1]
            try:
                return base64.b64decode(value, validate=True), None
            except ValueError as exc:
                raise ValueError("CosyVoice2 返回的音频不是有效 base64") from exc

        data = payload.get("data")
        if isinstance(data, dict):
            return CosyVoice2Provider._decode_json_audio(data)
        url = payload.get("url") or payload.get("audio_url")
        return None, str(url) if url else None

    async def synthesize(self, text: str, voice: str) -> tuple[bytes, list[dict], float]:
        if not self.endpoint:
            raise ValueError(
                "CosyVoice2 未配置：请设置 COSYVOICE2_BASE_URL 或 COSYVOICE2_ENDPOINT"
            )
        selected_voice = self.configured_voice or voice
        if not selected_voice:
            raise ValueError("CosyVoice2 未配置音色：请设置 COSYVOICE2_VOICE")

        headers = {"Accept": "audio/mpeg, application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = {
            "model": self.model,
            "input": text,
            "voice": selected_voice,
            "response_format": "mp3",
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.post(self.endpoint, headers=headers, json=request)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "json" in content_type:
                audio, audio_url = self._decode_json_audio(response.json())
                if audio_url:
                    # Never forward the synthesis credential to a provider-supplied URL.
                    audio_response = await client.get(audio_url)
                    audio_response.raise_for_status()
                    audio = audio_response.content
            else:
                audio = response.content

        if not audio:
            raise ValueError("CosyVoice2 响应中未找到音频数据")
        fd_mp3, mp3_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd_mp3)
        try:
            with open(mp3_path, "wb") as output:
                output.write(audio)
            duration = _probe_duration(mp3_path, [])
        finally:
            try:
                os.remove(mp3_path)
            except OSError:
                pass
        if duration <= 0:
            raise ValueError("CosyVoice2 音频时长探测失败")
        # CosyVoice2 endpoints commonly omit timestamp events. A full-text anchor
        # makes the existing subtitle builder fall back to deterministic interpolation.
        boundaries = [{"text": text, "start": 0.0, "end": duration}]
        return audio, boundaries, duration


def get_tts_provider(
    name: str | None = None,
    *,
    allow_experimental: bool = False,
) -> TTSProvider:
    provider = (name or os.environ.get("TTS_PROVIDER", "edge")).strip().lower()
    if provider in {"edge", "edge-tts"}:
        return EdgeTTSProvider()
    if provider in {"cosyvoice2", "cosyvoice"}:
        production_enabled = os.environ.get(
            "COSYVOICE2_PRODUCTION_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes"}
        if not allow_experimental and not production_enabled:
            raise ValueError(
                "CosyVoice2 尚未通过生产启用门；请先使用 tts_compare.py 完成试听验收"
            )
        return CosyVoice2Provider()
    raise ValueError(
        f"未适配的 TTS Provider: {provider}。当前可用 provider 为 edge、cosyvoice2。"
    )
