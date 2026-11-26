"""Offline, fictional input tests; no account credentials or paid services."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pipeline


class PortablePipelineTests(unittest.TestCase):
    def run_step(self, *argv):
        with patch.object(sys, 'argv', ['pipeline.py', *argv]), contextlib.redirect_stdout(io.StringIO()):
            return pipeline.main()

    def test_text_end_to_end_and_cache_and_changed_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'fiction.txt'
            source.write_text('今天去公园走走。树叶绿了。走累了就坐一会儿。心里也敞亮。\n这是一个虚构样本。', encoding='utf-8')
            out = root / 'run'
            self.assertEqual(self.run_step('ingest', '--input', str(source), '--out', str(out)), 0)
            self.assertEqual(self.run_step('transcribe', '--out', str(out)), 0)
            data = json.loads((out / 'transcript.json').read_text(encoding='utf-8'))
            self.assertFalse(data['timing_available'])
            self.assertIsNone(data['duration'])
            self.assertEqual(data['segments'], [])
            self.assertEqual(self.run_step('transcribe', '--out', str(out)), 0)
            self.assertTrue(json.loads((out / 'manifest.json').read_text(encoding='utf-8'))['transcript_reused'])
            self.assertEqual(self.run_step('prepare-clean', '--out', str(out), '--category', 'health'), 0)
            self.assertIn('health.txt', (out / 'clean-request.md').read_text(encoding='utf-8'))
            (out / 'cleaned.txt').write_text(data['text'], encoding='utf-8')
            self.assertEqual(self.run_step('finish-clean', '--out', str(out)), 0)
            self.assertEqual(json.loads((out / 'cleaned.json').read_text(encoding='utf-8'))['counts']['effective_ratio'], 1)
            self.assertTrue((out / 'diff.md').is_file())
            (out / 'source.txt').write_text('内容已经变化。', encoding='utf-8')
            self.assertEqual(self.run_step('transcribe', '--out', str(out)), 0)
            self.assertFalse(json.loads((out / 'manifest.json').read_text(encoding='utf-8'))['transcript_reused'])

    def test_failed_network_error_does_not_leak_signed_url(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(pipeline, 'ingest', side_effect=RuntimeError('https://example.invalid/?token=private-token')):
            self.assertEqual(self.run_step('ingest', '--input', 'x', '--out', tmp), 2)
            result = (Path(tmp) / 'manifest.json').read_text(encoding='utf-8')
            self.assertNotIn('private-token', result)
            self.assertNotIn('https://', result)

    def test_bad_cleaning_warns_instead_of_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'fiction.md'
            source.write_text('公园里的树叶绿了。' * 10, encoding='utf-8')
            out = root / 'run'
            self.run_step('ingest', '--input', str(source), '--out', str(out))
            self.run_step('transcribe', '--out', str(out))
            (out / 'cleaned.txt').write_text('只剩一句。', encoding='utf-8')
            self.assertEqual(self.run_step('finish-clean', '--out', str(out)), 0)
            data = json.loads((out / 'cleaned.json').read_text(encoding='utf-8'))
            self.assertTrue(data['quality_warnings'])
            self.assertEqual(data['cleaned'], '只剩一句。')

    def test_image_posts_and_unsafe_domains_still_rejected(self):
        from resolvers import wechat_channels as wx
        with self.assertRaisesRegex(wx.ChannelsError, '图文内容'):
            wx._feed_video_url({'mediaType': 2, 'picInfo': [{}], 'bgmInfo': {'bgmUrl': 'private'}})
        with self.assertRaises(wx.ChannelsError):
            wx._media_url('https://finder.video.qq.com.evil.example/a')

    def test_duplicate_ingest_preserves_existing_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'fixture.txt'
            source.write_text('虚构内容', encoding='utf-8')
            out = Path(tmp) / 'run'
            self.run_step('ingest', '--input', str(source), '--out', str(out))
            before = (out / 'manifest.json').read_bytes()
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                self.run_step('ingest', '--input', str(source), '--out', str(out))
            self.assertEqual((out / 'manifest.json').read_bytes(), before)

    def test_media_keeps_word_times_and_falls_back_from_cuda(self):
        # Exercise decoding arguments and lazy ASR/CUDA fallback without downloading a model.
        import types
        np = types.ModuleType('numpy')
        np.float32 = 'float32'
        np.frombuffer = lambda *a, **k: SimpleNamespace(size=16000)
        ff = types.ModuleType('imageio_ffmpeg')
        ff.get_ffmpeg_exe = lambda: 'ffmpeg'
        whisper = types.ModuleType('faster_whisper')
        def model(name, device, compute_type):
            if device == 'cuda':
                raise RuntimeError('CUDA unavailable')
            word = SimpleNamespace(start=.1, end=.5, word='你好')
            segment = SimpleNamespace(id=0, start=.1, end=.5, text='你好。', words=[word])
            return SimpleNamespace(transcribe=lambda *a, **k: (iter([segment]), SimpleNamespace(language='zh', duration=1.0)))
        whisper.WhisperModel = model
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {'numpy':np, 'imageio_ffmpeg':ff, 'faster_whisper':whisper}), patch.object(pipeline.subprocess, 'run', return_value=SimpleNamespace(stdout=b'audio')) as decode:
            source = Path(tmp) / 'fiction.wav'
            source.write_bytes(b'fictional audio fixture')
            out = Path(tmp) / 'run'
            self.run_step('ingest', '--input', str(source), '--out', str(out))
            self.assertEqual(self.run_step('transcribe', '--out', str(out), '--device', 'cuda'), 0)
            data = json.loads((out / 'transcript.json').read_text(encoding='utf-8'))
            self.assertTrue(data['timing_available'])
            self.assertTrue(data['timings']['cpu_fallback'])
            self.assertEqual(data['segments'][0]['words'][0], {'start':.1,'end':.5,'word':'你好'})
            self.assertIn('f32le', decode.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
