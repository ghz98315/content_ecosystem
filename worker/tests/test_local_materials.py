import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from local_materials import _unused_start, meets_native_resolution, native_crop_size, resolve_asset, sequence_signature
from stock_media import fetch_source
import media_retention


class LocalMaterialSafetyTests(unittest.TestCase):
    def test_task_seed_reuses_source_only_at_a_distinct_nonoverlapping_excerpt(self):
        first = _unused_start(150, 30, [], 'task-one', 0, 'asset')
        self.assertEqual(first, _unused_start(150, 30, [], 'task-one', 0, 'asset'))
        second = _unused_start(150, 30, [(first, first+30)], 'task-one', 4, 'asset')
        self.assertIsNotNone(second)
        self.assertTrue(second+30 <= first-0.95 or second >= first+30.95)
        self.assertIsNone(_unused_start(50, 30, [(0, 30)], 'task-one', 4, 'asset'))

    def test_sequence_signature_includes_order_and_source_range(self):
        a = {'asset': {'relative_path': 'health/a.mp4'}, 'source_start': 2, 'source_end': 12}
        b = {'asset': {'relative_path': 'health/b.mp4'}, 'source_start': 4, 'source_end': 14}
        self.assertNotEqual(sequence_signature([a, b]), sequence_signature([b, a]))
        self.assertNotEqual(sequence_signature([a, b]),
                            sequence_signature([{**a, 'source_start': 3}, b]))

    def test_clear_master_retention_only_removes_expired_video_inside_uuid_folder(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'output') as directory:
            root = Path(directory)
            valid = root / 'output' / 'high-quality-exports' / '11111111-1111-1111-1111-111111111111'
            valid.mkdir(parents=True)
            old_video = valid / 'old.mp4'
            fresh_video = valid / 'fresh.mp4'
            old_video.write_bytes(b'old')
            fresh_video.write_bytes(b'fresh')
            old_time = time.time() - 8 * 86400
            os.utime(old_video, (old_time, old_time))
            outside = root / 'output' / 'high-quality-exports' / 'not-a-task'
            outside.mkdir()
            outside_video = outside / 'old.mp4'
            outside_video.write_bytes(b'keep')
            os.utime(outside_video, (old_time, old_time))
            with patch.object(media_retention, '__file__', str(root / 'media_retention.py')):
                result = media_retention.cleanup_local_high_quality_exports()
            self.assertEqual(1, result['removed'])
            self.assertFalse(old_video.exists())
            self.assertTrue(fresh_video.exists())
            self.assertTrue(outside_video.exists())

    def test_native_crop_gate_never_enlarges_a_720p_source(self):
        self.assertEqual((960, 720), native_crop_size(1280, 720, '4:3'))
        self.assertFalse(meets_native_resolution({'width': 1280, 'height': 720}, '4:3'))
        self.assertFalse(meets_native_resolution({'width': 720, 'height': 1280}, '4:3'))
        self.assertTrue(meets_native_resolution({'width': 1280, 'height': 720}, '4:3', 720))
        self.assertTrue(meets_native_resolution({'width': 720, 'height': 1280}, '4:3', 720))
        self.assertTrue(meets_native_resolution({'width': 1920, 'height': 1080}, '4:3'))
        self.assertTrue(meets_native_resolution({'width': 1080, 'height': 1920}, '4:3'))

    def test_selected_video_stays_local_and_cannot_escape_library(self):
        scratch = Path(__file__).resolve().parents[1] / "output"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory) / "library"
            folder = root / "20_国学"
            folder.mkdir(parents=True)
            video = folder / "clip.mp4"
            video.write_bytes(b"video")
            outside = Path(directory) / "outside.mp4"
            outside.write_bytes(b"other")
            with patch.dict(os.environ, {"LOCAL_MEDIA_LIBRARY_ROOT": str(root)}):
                asset = {"provider": "local_library", "relative_path": "20_国学/clip.mp4", "bytes": 5}
                self.assertEqual(video, resolve_asset(asset))
                self.assertEqual(video, fetch_source(asset))
                with self.assertRaisesRegex(ValueError, "路径无效"):
                    resolve_asset({"relative_path": "../outside.mp4"})
                with self.assertRaisesRegex(ValueError, "路径无效"):
                    resolve_asset({"relative_path": str(outside)})
                with self.assertRaisesRegex(ValueError, "已改变"):
                    resolve_asset({**asset, "bytes": 100})


if __name__ == "__main__":
    unittest.main()
