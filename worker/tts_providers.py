"""TTS provider boundary; production currently defaults to Edge TTS."""
from __future__ import annotations

import base64
import html
import json
import os
import re
import subprocess
import tempfile
from typing import Any, Protocol

import httpx
import imageio_ffmpeg


class TTSProvider(Protocol):
    async def synthesize(
        self, text: str, voice: str, instruction: str | None = None,
        request_options: dict[str, Any] | None = None,
    ) -> tuple[bytes, list[dict], float]:
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
    async def synthesize(
        self, text: str, voice: str, instruction: str | None = None,
        request_options: dict[str, Any] | None = None,
    ) -> tuple[bytes, list[dict], float]:
        import edge_tts

        fd_mp3, mp3_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd_mp3)
        segments: list[dict] = []
        try:
            options = request_options or {}
            rate = options.get("rate") or options.get("speed")
            kwargs = {"boundary": "SentenceBoundary"}
            if rate is not None:
                # edge-tts accepts a percentage string (for example, -8%).
                # Keep the option opt-in so legacy requests are byte-for-byte
                # equivalent at the provider boundary.
                rate_value = str(rate).strip()
                if re.fullmatch(r"[+-]?\d+(?:\.\d+)?%", rate_value):
                    kwargs["rate"] = rate_value
                else:
                    numeric = float(rate_value)
                    kwargs["rate"] = f"{numeric:+g}%"
            comm = edge_tts.Communicate(text, voice, **kwargs)
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

    def __init__(self, model_override: str | None = None) -> None:
        self.dashscope_api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        self.dashscope_model = os.environ.get("DASHSCOPE_MODEL", "").strip()
        self.dashscope_voice = os.environ.get("DASHSCOPE_VOICE", "").strip()
        profile_name = os.environ.get("DASHSCOPE_VOICE_PROFILE", "").strip()
        profiles_raw = os.environ.get("DASHSCOPE_VOICE_PROFILES_JSON", "").strip()
        if profile_name and profiles_raw:
            try:
                profiles = json.loads(profiles_raw)
                profile = profiles.get(profile_name)
                if not isinstance(profile, dict):
                    raise ValueError(f"unknown voice profile: {profile_name}")
                self.dashscope_model = str(profile.get("model", "")).strip() or self.dashscope_model
                self.dashscope_voice = str(profile.get("voice", "")).strip() or self.dashscope_voice
            except (json.JSONDecodeError, AttributeError) as exc:
                raise ValueError("DASHSCOPE_VOICE_PROFILES_JSON must be a JSON object") from exc
        if model_override:
            self.dashscope_model = model_override
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
        self.instruction = (
            os.environ.get("DASHSCOPE_INSTRUCTION", "").strip()
            or os.environ.get("COSYVOICE_INSTRUCTION", "").strip()
            or "请像两个人日常聊天一样，用自然、平实、温和的中文口吻表达；语调跟随语义有正常起伏，问句自然上扬，句末自然收束。不要刻意强调，不要播音腔，不要像背书或表演。严格遵从文本中的 SSML break 停顿，不自行增加或拉长停顿。"
        )

        dashscope_endpoint = os.environ.get("DASHSCOPE_ENDPOINT", "").strip()
        workspace = os.environ.get("DASHSCOPE_WORKSPACE_ID", "").strip()
        region = os.environ.get("DASHSCOPE_REGION", "cn-beijing").strip()
        if not dashscope_endpoint and workspace:
            dashscope_endpoint = (
                f"https://{workspace}.{region}.maas.aliyuncs.com"
                "/api/v1/services/audio/tts/SpeechSynthesizer"
            )
        self.dashscope_endpoint = dashscope_endpoint

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
        output = payload.get("output")
        if isinstance(output, dict):
            audio = output.get("audio")
            if isinstance(audio, dict):
                return CosyVoice2Provider._decode_json_audio(audio)
        url = payload.get("url") or payload.get("audio_url")
        return None, str(url) if url else None

    async def synthesize(
        self, text: str, voice: str, instruction: str | None = None,
        request_options: dict[str, Any] | None = None,
    ) -> tuple[bytes, list[dict], float]:
        use_dashscope = bool(
            self.dashscope_api_key and self.dashscope_model and self.dashscope_endpoint
        )
        if not use_dashscope and not self.endpoint:
            raise ValueError(
                "CosyVoice2 未配置：请设置 DASHSCOPE_API_KEY/DASHSCOPE_MODEL/DASHSCOPE_ENDPOINT"
            )
        # A task snapshot is authoritative. Environment profiles only provide a
        # default for legacy tasks that do not carry a selected voice.
        selected_voice = voice or self.dashscope_voice or self.configured_voice
        if not selected_voice:
            raise ValueError("CosyVoice2 未配置音色：请设置 COSYVOICE2_VOICE")

        headers = {"Accept": "audio/mpeg, application/json"}
        ssml_enabled = bool(re.match(r"^\s*<speak(?:\s|>)", text, re.IGNORECASE))
        if use_dashscope:
            headers["Authorization"] = f"Bearer {self.dashscope_api_key}"
            endpoint = self.dashscope_endpoint
            request = {
                "model": self.dashscope_model,
                "input": {
                    "text": text,
                    "voice": selected_voice,
                    "format": "mp3",
                    "sample_rate": 22050,
                    "enable_ssml": ssml_enabled,
                    "instruction": instruction.strip() if instruction else self.instruction,
                },
            }
        else:
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            endpoint = self.endpoint
            request = {
                "model": self.model,
                "input": text,
                "voice": selected_voice,
                "response_format": "mp3",
            }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.post(endpoint, headers=headers, json=request)
            status_code = getattr(response, "status_code", 200)
            detail_text = getattr(response, "text", "")[:1000]
            ssml_engine_reject = (
                status_code == 400
                and ssml_enabled
                and ("428" in detail_text or "InvalidParameter" in detail_text)
            )
            if getattr(response, "is_error", status_code >= 400) and ssml_engine_reject:
                # Some cloned voices reject SSML with opaque engine code 428.
                # Retry this segment as plain text before failing the stage.
                plain_request = dict(request)
                plain_input = dict(plain_request["input"])
                plain_input["text"] = re.sub(r"<[^>]+>", "", text)
                plain_input["enable_ssml"] = False
                plain_input.pop("instruction", None)
                plain_request["input"] = plain_input
                response = await client.post(endpoint, headers=headers, json=plain_request)
                status_code = getattr(response, "status_code", 200)
            if getattr(response, "is_error", status_code >= 400):
                detail = response.text[:1000]
                raise ValueError(f"DashScope TTS 请求失败 ({status_code}): {detail}")
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
        spoken_text = re.sub(r"<[^>]+>", "", text) if ssml_enabled else text
        boundaries = [{"text": html.unescape(spoken_text), "start": 0.0, "end": duration}]
        return audio, boundaries, duration


class IndexTTS25Provider:
    """HTTP adapter for the self-hosted, single-model IndexTTS2.5 service."""

    def __init__(self, model_override: str | None = None) -> None:
        base_url = os.environ.get("INDEXTTS25_BASE_URL", "").strip().rstrip("/")
        self.endpoint = os.environ.get("INDEXTTS25_ENDPOINT", "").strip()
        if not self.endpoint and base_url:
            self.endpoint = f"{base_url}/v1/audio/speech"
        self.health_endpoint = (
            os.environ.get("INDEXTTS25_HEALTH_ENDPOINT", "").strip()
            or (f"{base_url}/health" if base_url else "")
        )
        self.api_token = os.environ.get("INDEXTTS25_API_TOKEN", "").strip()
        self.model = model_override or os.environ.get(
            "INDEXTTS25_MODEL", "index-tts-2.5"
        ).strip()
        self.configured_voice = os.environ.get("INDEXTTS25_VOICE", "").strip()
        self.timeout = max(30.0, float(os.environ.get("INDEXTTS25_TIMEOUT", "300")))
        self.duration_factor = float(os.environ.get("INDEXTTS25_DURATION_FACTOR", "1.08"))
        self.emo_alpha = float(os.environ.get("INDEXTTS25_EMO_ALPHA", "0.55"))
        self.use_qwen_emotion = os.environ.get(
            "INDEXTTS25_USE_QWEN_EMOTION", "true"
        ).strip().lower() in {"1", "true", "yes"}
        self.plain_voices = {
            item.strip() for item in os.environ.get(
                "INDEXTTS25_PLAIN_VOICES", ""
            ).split(",") if item.strip()
        }
        self.emotion_text = os.environ.get(
            "INDEXTTS25_EMOTION_TEXT",
            "自然、有交流感地讲述，语气随语义起伏；重点自然加强，解释处放松，句末自然收束，不要播音腔。",
        ).strip()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "audio/wav, audio/mpeg, application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def healthcheck(self) -> dict:
        if not self.health_endpoint:
            raise ValueError("IndexTTS2.5 未配置健康检查地址")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(self.health_endpoint, headers=self._headers())
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise ValueError(f"IndexTTS2.5 健康检查未就绪: {payload}")
        return payload

    async def synthesize(
        self, text: str, voice: str, instruction: str | None = None,
        request_options: dict[str, Any] | None = None,
    ) -> tuple[bytes, list[dict], float]:
        if not self.endpoint:
            raise ValueError(
                "IndexTTS2.5 未配置：请设置 INDEXTTS25_BASE_URL 或 INDEXTTS25_ENDPOINT"
            )
        selected_voice = voice or self.configured_voice
        if not selected_voice:
            raise ValueError("IndexTTS2.5 未配置音色 profile")
        overrides = request_options or {}
        if not isinstance(overrides, dict):
            raise ValueError("IndexTTS2.5 task options must be an object")
        allowed_options = {
            "duration_factor", "emo_alpha", "emotion_voice", "emo_vector",
            "emotion_text", "use_qwen_emotion", "temperature", "top_p",
            "repetition_penalty",
        }
        unsupported = set(overrides) - allowed_options
        if unsupported:
            raise ValueError(f"unsupported IndexTTS2.5 task options: {sorted(unsupported)}")
        request = {
            "model": self.model,
            "input": text,
            "voice": selected_voice,
            "language": "zh",
            "response_format": "wav",
            "duration_factor": overrides.get("duration_factor", self.duration_factor),
            # English reference clips can make the Qwen emotion branch drift
            # into a non-target language. Keep those profiles on plain
            # IndexTTS inference while preserving the narrator35 baseline.
            "use_qwen_emotion": overrides.get(
                "use_qwen_emotion",
                self.use_qwen_emotion and selected_voice not in self.plain_voices,
            ),
            "emotion_text": str(overrides.get("emotion_text") or instruction or self.emotion_text).strip(),
            "emo_alpha": overrides.get("emo_alpha", self.emo_alpha),
        }
        for name in ("emotion_voice", "emo_vector", "temperature", "top_p", "repetition_penalty"):
            if name in overrides:
                request[name] = overrides[name]
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.post(
                self.endpoint, headers=self._headers(), json=request,
            )
            if response.is_error:
                raise ValueError(
                    f"IndexTTS2.5 请求失败 ({response.status_code}): {response.text[:1000]}"
                )
            content_type = response.headers.get("content-type", "").lower()
            if "json" in content_type:
                audio, audio_url = CosyVoice2Provider._decode_json_audio(response.json())
                if audio_url:
                    audio_response = await client.get(audio_url)
                    audio_response.raise_for_status()
                    audio = audio_response.content
            else:
                audio = response.content
        if not audio:
            raise ValueError("IndexTTS2.5 响应中未找到音频数据")

        fd_audio, audio_path = tempfile.mkstemp(suffix=".audio")
        os.close(fd_audio)
        fd_mp3, mp3_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd_mp3)
        try:
            with open(audio_path, "wb") as output:
                output.write(audio)
            duration = _probe_duration(audio_path, [])
            subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", audio_path,
                    "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "128k", mp3_path,
                ],
                check=True,
                capture_output=True,
            )
            with open(mp3_path, "rb") as source:
                mp3_audio = source.read()
        finally:
            for path in (audio_path, mp3_path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        if duration <= 0:
            raise ValueError("IndexTTS2.5 音频时长探测失败")
        return mp3_audio, [{"text": text, "start": 0.0, "end": duration}], duration


def get_tts_provider(
    name: str | None = None,
    *,
    allow_experimental: bool = False,
    model: str | None = None,
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
        return CosyVoice2Provider(model_override=model)
    if provider in {"indextts25", "index-tts-2.5", "indextts2.5"}:
        production_enabled = os.environ.get(
            "INDEXTTS25_PRODUCTION_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes"}
        if not allow_experimental and not production_enabled:
            raise ValueError(
                "IndexTTS2.5 尚未通过生产启用门；请先完成 2000 字长文试听验收"
            )
        return IndexTTS25Provider(model_override=model)
    raise ValueError(
        f"未适配的 TTS Provider: {provider}。当前可用 provider 为 edge、cosyvoice2、indextts25。"
    )
