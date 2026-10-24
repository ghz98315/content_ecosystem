from __future__ import annotations

import unittest

from stages.render import _validate_timeline
from stages.tts import _build_subtitle_cues
from narration import mark_book_titles_in_cues


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

    def test_external_cues_gain_title_marks_without_changing_timing(self):
        cues = [{"text": "今天读道德经", "start": 0.0, "end": 1.5, "char_start": 0, "char_end": 6}]
        result = mark_book_titles_in_cues(cues, "《道德经》")
        self.assertEqual("今天读《道德经》", result[0]["text"])
        self.assertEqual((0.0, 1.5, 0, 6), (result[0]["start"], result[0]["end"], result[0]["char_start"], result[0]["char_end"]))
        self.assertEqual("今天读道德经", cues[0]["text"])

    def test_title_split_across_adjacent_cues_is_rejoined(self):
        cues = [
            {"text": "今天读道德", "start": 0.0, "end": 1.0, "char_start": 0, "char_end": 5},
            {"text": "经很有意思", "start": 1.0, "end": 2.0, "char_start": 5, "char_end": 10},
        ]
        result = mark_book_titles_in_cues(cues, "道德经")
        self.assertEqual(1, len(result))
        self.assertEqual("今天读《道德经》很有意思", result[0]["text"])
        self.assertEqual(2.0, result[0]["end"])
        self.assertEqual(10, result[0]["char_end"])


if __name__ == "__main__":
    unittest.main()
