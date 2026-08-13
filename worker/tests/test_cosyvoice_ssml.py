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
        self.assertIn('<speak rate="0.94" pitch="1.03" volume="54">', ssml)
        self.assertIn('<break time="260ms"/>', ssml)
        self.assertIn("A&amp;B", ssml)
        self.assertEqual("cosy_warm_narrative_v1", _COSY_WARM_NARRATIVE)

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
        self.assertEqual("你好世界", boundaries[0]["text"])


if __name__ == "__main__":
    unittest.main()
