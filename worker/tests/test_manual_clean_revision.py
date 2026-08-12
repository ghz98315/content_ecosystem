import unittest
from unittest.mock import MagicMock, patch

from stages import rewrite


class ManualCleanRevisionTests(unittest.TestCase):
    def test_confirmed_manual_clean_text_takes_precedence_over_artifact(self):
        stages_query = MagicMock()
        stages_query.select.return_value = stages_query
        stages_query.eq.return_value = stages_query
        stages_query.limit.return_value = stages_query
        stages_query.execute.return_value = type(
            "Response", (), {"data": [{"params": {
                "manual_clean_confirmed": True,
                "manual_clean_text": "人工确认后的清洗稿",
            }}]}
        )()
        client = MagicMock()
        client.table.return_value = stages_query

        with patch("stages.rewrite.db.get_client", return_value=client), patch(
            "stages.rewrite.storage.download_artifact",
            side_effect=AssertionError("manual revision should avoid artifact download"),
        ):
            result = rewrite._load_clean_text("task-id")

        self.assertEqual("人工确认后的清洗稿", result)


if __name__ == "__main__":
    unittest.main()
