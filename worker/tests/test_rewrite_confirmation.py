from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from stages import rewrite
from stages import book


class RewriteConfirmationTests(unittest.TestCase):
    def test_dialogue_title_instruction_only_applies_to_dialogue_tasks(self):
        with patch("stages.book.db.get_task_prompt_context", return_value={"narration_mode": "dual_dialogue"}):
            self.assertIn("双人对谈", book._dialogue_title_instruction("task-id"))
        with patch("stages.book.db.get_task_prompt_context", return_value={"narration_mode": "single"}):
            self.assertEqual("", book._dialogue_title_instruction("task-id"))
    def test_confirmed_draft_does_not_run_compliance_a_second_time(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = Path(tmpdir) / "rewrite.json"
            artifact.write_text(
                json.dumps({"candidates": ["reviewed draft"], "compliance": {"status": "blocked"}}),
                encoding="utf-8",
            )
            artifact_query = MagicMock()
            artifact_query.select.return_value = artifact_query
            artifact_query.eq.return_value = artifact_query
            artifact_query.order.return_value = artifact_query
            artifact_query.limit.return_value = artifact_query
            artifact_query.execute.return_value = type(
                "Response", (), {"data": [{"storage_path": "task/rewrite.json"}]}
            )()
            latest_query = MagicMock()
            latest_query.select.return_value = latest_query
            latest_query.eq.return_value = latest_query
            latest_query.single.return_value = latest_query
            latest_query.execute.return_value = type(
                "Response", (), {"data": {"params": {"chosen_index": 0, "final_text": "approved draft"}}}
            )()
            update_query = MagicMock()
            update_query.update.return_value = update_query
            update_query.eq.return_value = update_query
            client = MagicMock()
            client.table.side_effect = [latest_query, artifact_query, update_query]
            stage = {
                "id": "rewrite-stage",
                "task_id": "task-id",
                "params": {"chosen_index": 0, "final_text": "approved draft"},
            }

            with patch("stages.rewrite.db.get_task_prompt_context", return_value={}), patch(
                "stages.rewrite._load_clean_text", return_value="source"
            ), patch("stages.rewrite._task_context", return_value={"category": "health"}), patch(
                "stages.rewrite.db.get_client", return_value=client
            ), patch("stages.rewrite.storage.download_artifact", return_value=str(artifact)), patch(
                "stages.rewrite._upload_rewrite"
            ) as upload, patch(
                "stages.rewrite.compliance.check_text",
                side_effect=AssertionError("confirmed drafts must not be rechecked"),
            ):
                status, output_ref = rewrite.run(stage)

        self.assertEqual(("done", "task/rewrite.json"), (status, output_ref))
        self.assertEqual("approved draft", upload.call_args.args[1]["final_text"])
        self.assertEqual({"status": "blocked"}, upload.call_args.args[1]["compliance"])


if __name__ == "__main__":
    unittest.main()
