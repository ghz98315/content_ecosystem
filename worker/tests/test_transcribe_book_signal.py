import unittest
from unittest.mock import MagicMock, patch

from stages.transcribe import _infer_book_signal, _punctuate_for_reading


class TranscriptBookSignalTests(unittest.TestCase):
    def test_reading_punctuation_falls_back_to_original_on_provider_error(self):
        with patch("stages.transcribe.config.clean_client", side_effect=RuntimeError("offline")):
            self.assertEqual("没有标点的逐字稿", _punctuate_for_reading("没有标点的逐字稿"))

    def test_reading_punctuation_returns_model_output(self):
        message = MagicMock(content="没有标点的，逐字稿。")
        client = MagicMock()
        client.chat.completions.create.return_value.choices = [MagicMock(message=message)]
        with patch("stages.transcribe.config.clean_client", return_value=client):
            self.assertEqual("没有标点的，逐字稿。", _punctuate_for_reading("没有标点的逐字稿"))

    def test_reading_punctuation_rejects_model_word_changes(self):
        message = MagicMock(content="被模型改写的逐字稿。")
        client = MagicMock()
        client.chat.completions.create.return_value.choices = [MagicMock(message=message)]
        with patch("stages.transcribe.config.clean_client", return_value=client):
            self.assertEqual("没有标点的逐字稿", _punctuate_for_reading("没有标点的逐字稿"))

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
