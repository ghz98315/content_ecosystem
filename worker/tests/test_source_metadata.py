from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from source_metadata import publication_title, split_source_description
from stages.book import _publication_metadata
from stages.ingest import _write_task_meta


class SourceMetadataTests(unittest.TestCase):
    def test_source_title_and_tags_are_split_without_losing_order(self):
        title, tags = split_source_description(
            "为什么昂贵面霜也挡不住衰老____#女性成长_#抗衰老_#健康生活_#抗老生活_#逆龄"
        )
        self.assertEqual("为什么昂贵面霜也挡不住衰老", title)
        self.assertEqual(["女性成长", "抗衰老", "健康生活", "抗老生活", "逆龄"], tags)

    def test_publish_title_is_unpunctuated_and_limited_to_sixteen_characters(self):
        value = publication_title("为什么越贵的面霜，越挡不住衰老？这是答案")
        self.assertEqual("为什么越贵的面霜越挡不住衰老这是", value)
        self.assertLessEqual(len(value), 16)

    def test_book_publication_metadata_uses_structured_source_tags(self):
        with patch("stages.book.db.get_task_prompt_context", return_value={
            "title": "原标题",
            "source_tags": ["健康生活", "抗衰老"],
        }):
            result = _publication_metadata("task-id", {"publish_title": "抗老，先看生活顺序！"})
        self.assertEqual("原标题", result["source_title"])
        self.assertEqual(["健康生活", "抗衰老"], result["source_tags"])
        self.assertEqual("抗老先看生活顺序", result["publish_title"])

    def test_ingest_falls_back_before_source_tags_migration(self):
        query = MagicMock()
        query.update.return_value = query
        query.eq.return_value = query
        query.execute.side_effect = [RuntimeError("source_tags missing from schema cache"), MagicMock()]
        client = MagicMock()
        client.table.return_value = query
        result = type("Result", (), {
            "title": "一个原标题_#健康生活_#读书",
            "play_count": 12,
            "author": {"name": "作者"},
        })()

        with patch("stages.ingest.db.get_client", return_value=client):
            _write_task_meta("task-id", result)

        self.assertEqual(2, query.update.call_count)
        self.assertEqual(["健康生活", "读书"], query.update.call_args_list[0].args[0]["source_tags"])
        self.assertNotIn("source_tags", query.update.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
