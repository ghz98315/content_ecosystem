import unittest

from stages.transcribe import _infer_book_signal


class TranscriptBookSignalTests(unittest.TestCase):
    def test_extracts_explicit_bracketed_title(self):
        result = _infer_book_signal("今天讲《被讨厌的勇气》的核心观点")
        self.assertEqual({"title": "被讨厌的勇气", "confidence": "medium", "evidence": "transcript_book_brackets"}, result)

    def test_extracts_labeled_title_with_low_confidence(self):
        result = _infer_book_signal("这本书是人类简史，今天介绍第一章")
        self.assertEqual("人类简史", result["title"])
        self.assertEqual("low", result["confidence"])

    def test_does_not_guess_without_explicit_signal(self):
        result = _infer_book_signal("今天我们聊聊一个重要的心理学观点")
        self.assertIsNone(result["title"])
