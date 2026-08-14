from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from stages.tts import _COSY_WARM_NARRATIVE, _cosyvoice_ssml
from tts_providers import get_tts_provider


class CosyVoiceSsmlTests(unittest.TestCase):
    def test_warm_narrative_ssml_uses_restrained_prosody_and_escapes_text(self):
        ssml = _cosyvoice_ssml("先听我说。A&B", "hook")
        self.assertIn('<speak rate="0.99" pitch="1.06" volume="55">', ssml)
        self.assertIn('<break time="800ms"/>', ssml)
        self.assertIn("A&amp;B", ssml)
        self.assertEqual("cosy_warm_narrative_v3", _COSY_WARM_NARRATIVE)

    def test_warm_narrative_uses_distinct_semantic_tones_with_sparse_pauses(self):
        alert = _cosyvoice_ssml("重点是，千万不要忽视这个风险。", "body")
        comfort = _cosyvoice_ssml("慢一点，照顾好自己。", "body")
        affirm = _cosyvoice_ssml("这是值得高兴的改变。", "body")
        self.assertIn('<speak rate="0.98" pitch="0.97" volume="53">', alert)
        self.assertIn('<speak rate="0.96" pitch="1.01" volume="51">', comfort)
        self.assertIn('<speak rate="1.01" pitch="1.04" volume="54">', affirm)
        self.assertIn('<break time="300ms"/>', alert)
        self.assertIn('<break time="800ms"/>', comfort)

    def test_ssml_pause_profile_matches_approved_punctuation_durations(self):
        ssml = _cosyvoice_ssml('您看啊，先说清楚：这不是——吓唬人……“慢一点”。好吧？', "body")
        for duration in ("300ms", "450ms", "700ms", "800ms", "900ms", "150ms"):
            self.assertIn(f'<break time="{duration}"/>', ssml)
        self.assertNotIn("，", ssml)
        self.assertNotIn("。", ssml)

    def test_dialogue_ssml_uses_distinct_host_and_guest_delivery(self):
        host = _cosyvoice_ssml("这个反差为什么值得注意？", "hook", "主持人")
        guest = _cosyvoice_ssml("我们可以从生活节奏慢慢拆开来看。", "body", "嘉宾")
        self.assertIn('<speak rate="1.03" pitch="1.12" volume="56">', host)
        self.assertIn('<speak rate="0.99" pitch="1.05" volume="54">', guest)

    def test_dashscope_request_enables_ssml_and_keeps_plain_alignment_text(self):
        captured = {}

        class Response:
            headers = {"content-type": "audio/mpeg"}
            content = b"audio"
            status_code = 200
            is_error = False
            text = ""

        class Client:
            def __init__(self, **_kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_args): return None
            async def post(self, _endpoint, **kwargs):
                captured["request"] = kwargs["json"]
                return Response()

        env = {"DASHSCOPE_API_KEY": "key", "DASHSCOPE_MODEL": "cosyvoice-v3.5-flash", "DASHSCOPE_VOICE": "voice", "DASHSCOPE_ENDPOINT": "https://tts.example"}
        with patch.dict(os.environ, env, clear=True), patch("tts_providers.httpx.AsyncClient", Client), patch("tts_providers._probe_duration", return_value=1.0):
            _audio, boundaries, _duration = asyncio.run(get_tts_provider("cosyvoice2", allow_experimental=True).synthesize('<speak rate="0.94">你好<break time="260ms"/>世界</speak>', "voice"))

        self.assertTrue(captured["request"]["input"]["enable_ssml"])
        self.assertIn("自然、温和、生活化", captured["request"]["input"]["instruction"])
        self.assertEqual("你好世界", boundaries[0]["text"])


if __name__ == "__main__":
    unittest.main()
