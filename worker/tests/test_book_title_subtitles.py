from __future__ import annotations

import unittest

from stages.render import _validate_timeline
from stages.tts import _build_subtitle_cues


class BookTitleSubtitleTests(unittest.TestCase):
    def test_bare_book_name_is_displayed_with_title_marks(self):
        text = "这段内容来自身体重置并提供日常参考"
        anchors = [{
            "text": text,
            "start": 0.0,
            "end": 4.0,
            "char_start": 0,
            "char_end": len(text),
        }]

        cues = _build_subtitle_cues(
            text,
            anchors,
            4.0,
            max_chars=14,
            book_name="《身体重置》",
        )

        self.assertTrue(any("《身体重置》" in cue["text"] for cue in cues))
        self.assertEqual(len(text), cues[-1]["char_end"])
        _validate_timeline(
            [{"path": "image.png", "start": 0.0, "end": 4.0, "duration": 4.0}],
            cues,
            4.0,
        )

    def test_existing_title_marks_are_not_duplicated(self):
        text = "推荐阅读《身体重置》"
        anchors = [{
            "text": text,
            "start": 0.0,
            "end": 2.0,
            "char_start": 0,
            "char_end": len(text),
        }]

        cues = _build_subtitle_cues(text, anchors, 2.0, book_name="身体重置")
        display = "".join(cue["text"] for cue in cues)

        self.assertIn("《身体重置》", display)
        self.assertNotIn("《《", display)


if __name__ == "__main__":
    unittest.main()
