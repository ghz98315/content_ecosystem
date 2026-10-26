import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_materials import resolve_asset
from stock_media import fetch_source


class LocalMaterialSafetyTests(unittest.TestCase):
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
