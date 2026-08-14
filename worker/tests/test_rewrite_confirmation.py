from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from stages import rewrite
from stages import book


class RewriteConfirmationTests(unittest.TestCase):
    def test_dialogue_structure_reuses_health_compliance_but_requires_turns(self):
        valid = "主持人：为什么越着急越容易做错？\n嘉宾：因为注意范围会变窄。\n主持人：那应该怎么调整？\n嘉宾：先停一下，再确认关键条件。"
        self.assertEqual([], rewrite._dialogue_structure_issues(valid))
        self.assertTrue(rewrite._dialogue_structure_issues("主持人：这是独白。"))
        self.assertTrue(rewrite._dialogue_structure_issues("主持人：为什么？\n主持人：我再说一句。\n嘉宾：回答。\n主持人：总结。"))
        self.assertTrue(rewrite._dialogue_structure_issues("主持人：这是一个很长的问题吗？\n嘉宾：这是回答。\n主持人：那怎么办？\n嘉宾：这是回答。"))

    def test_dialogue_delivery_plan_requires_exact_turns_and_short_instructions(self):
        text = "主持人：为什么会这样？\n嘉宾：咱们先从日常习惯慢慢看。"
        raw = json.dumps({
            "text": text,
            "delivery_plan": [
                {"speaker": "主持人", "text": "为什么会这样？", "instruction": "轻松好奇地问，句尾自然上扬"},
                {"speaker": "嘉宾", "text": "咱们先从日常习惯慢慢看。", "instruction": "耐心平实地解释，像聊天"},
            ],
        }, ensure_ascii=False)
        plan = rewrite._dialogue_delivery_plan(raw, text)
        self.assertEqual("主持人", plan[0]["speaker"])
        self.assertEqual("耐心平实地解释，像聊天", plan[1]["instruction"])

        mismatched = raw.replace("为什么会这样？", "这是什么原因？")
        self.assertIsNone(rewrite._dialogue_delivery_plan(mismatched, text))

    def test_dialogue_title_instruction_only_applies_to_dialogue_tasks(self):
        with patch("stages.book.db.get_task_prompt_context", return_value={"narration_mode": "dual_dialogue"}):
            self.assertIn("双人对谈", book._dialogue_title_instruction("task-id"))
        with patch("stages.book.db.get_task_prompt_context", return_value={"narration_mode": "single"}):
            self.assertEqual("", book._dialogue_title_instruction("task-id"))

    def test_health_dialogue_uses_an_isolated_prompt_profile(self):
        self.assertEqual(
            "dual_dialogue_initial_dedup",
            rewrite._rewrite_prompt_kind("health", "initial_dedup", "dual_dialogue"),
        )
        self.assertEqual(
            "dual_dialogue_repost_dedup",
            rewrite._rewrite_prompt_kind("health", "repost_dedup", "dual_dialogue"),
        )
        self.assertEqual("initial_dedup", rewrite._rewrite_prompt_kind("health", "initial_dedup", "single"))
        self.assertEqual(
            "initial_dedup",
            rewrite._rewrite_prompt_kind("social_science", "initial_dedup", "dual_dialogue"),
        )

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
