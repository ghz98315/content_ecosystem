from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from stages.book import _ending_context, _generate_cta, _repeats_ending


class CtaContinuationTests(unittest.TestCase):
    def test_ending_context_uses_the_final_paragraphs(self):
        text = "开头内容。\n\n中段内容。\n\n倒数第二段。\n\n最后一句收束。"
        context = _ending_context(text)
        self.assertIn("倒数第二段", context)
        self.assertIn("最后一句收束", context)
        self.assertNotIn("开头内容", context)

    def test_repeated_conclusion_is_rejected(self):
        tail = "别跟烂人烂事较劲了，护好自己的身体。"
        self.assertTrue(_repeats_ending("气坏身体，亏的是自己，别较劲了。", tail))
        self.assertFalse(_repeats_ending("想慢慢读懂这些情绪的来处，可以翻翻这本书。", tail))

    def test_generation_retries_when_first_cta_repeats_the_ending(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="别跟烂人烂事较劲了，护好自己的身体。"))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content="想把这些想法慢慢理顺，不妨翻翻《病由心灭》，点击下方链接了解它。"))]),
        ]
        result = _generate_cta(
            client, "model", "正文。\n\n别跟烂人烂事较劲了，护好自己的身体。", "病由心灭", "周行"
        )
        self.assertIn("《病由心灭》", result)
        self.assertEqual(2, client.chat.completions.create.call_count)


if __name__ == "__main__":
    unittest.main()
