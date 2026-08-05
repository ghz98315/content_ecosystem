from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

import db
from compliance import check_text, scan_text
from prompt_profiles import derive_keyword, load_compliance_rules, load_prompt, normalize_category, protected_terms
from resolvers.self_resolver import select_hot_comments
from stages.image import _split_storyboard
from stages.render import _allocate_durations, TRANSITION_DUR
from stages.rewrite import _candidate_issues, _parse_candidates
from stages.tts import _clean_tts_text, _split_tts_segments, _synthesize


class RewriteQualityTests(unittest.TestCase):
    def test_structured_single_draft_is_complete(self):
        source = "这是原文内容。" * 20
        text = "这为原文内容。" * 20
        raw = json.dumps({"text": text}, ensure_ascii=False)
        candidates = _parse_candidates(raw)
        self.assertEqual(1, len(candidates))
        self.assertEqual([], _candidate_issues(candidates, source, "stop"))

    def test_length_finish_is_rejected(self):
        source = "完整原文。" * 20
        candidates = ["完整候选。" * 20]
        self.assertIn("模型输出达到长度上限", _candidate_issues(candidates, source, "length"))

    def test_large_rewrite_is_rejected(self):
        source = "你有没有发现越是着急越容易做错决定？中间讲清楚三个关键方法。最后记住先停下来再行动。" * 3
        rewritten = "今天分享一些完全不同的新鲜故事和人物经历，内容主题已经发生变化，最后也换成另一套营销引导。" * 3
        issues = _candidate_issues([rewritten], source, "stop")
        self.assertIn("改写幅度过大，未保持原文主体", issues)


class PromptProfileTests(unittest.TestCase):
    def test_health_prompts_are_loaded_and_reserved_profiles_are_rejected(self):
        self.assertIn("健康类书籍", load_prompt("health", "rewrite"))
        self.assertIn("疗效和安全承诺", load_compliance_rules("health"))
        with self.assertRaisesRegex(ValueError, "尚未开放"):
            normalize_category("social_science")

    def test_prompt_context_preserves_book_numbers_and_keyword(self):
        source = "《控糖方法》建议连续观察14天，变化约为12%。"
        self.assertEqual("控糖、控糖方法", derive_keyword("#控糖 《控糖方法》", source))
        self.assertEqual(["《控糖方法》", "14", "12%"], protected_terms(source))


class _FakeCompletions:
    def __init__(self, payload: dict):
        self.payload = payload

    def create(self, **_kwargs):
        message = type("Message", (), {"content": json.dumps(self.payload, ensure_ascii=False)})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, payload: dict):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(payload)})()


class ComplianceTests(unittest.TestCase):
    def test_treatment_promise_blocks_final_script(self):
        text = "照着这个方法做，三天见效，而且不用去医院。"
        report = check_text(_FakeClient({"issues": []}), "test", "health", text, {})
        self.assertEqual("blocked", report["status"])
        self.assertTrue(any(item["level"] == "high" for item in report["issues"]))

    def test_contextual_chapter_word_does_not_trigger_absolute_claim(self):
        self.assertEqual([], scan_text("第一章介绍作者的求学经历。"))

    def test_disease_term_requires_review_without_automatic_block(self):
        report = check_text(_FakeClient({"issues": []}), "test", "health", "书中回顾了糖尿病研究的历史。", {})
        self.assertEqual("warning", report["status"])


class StoryboardTests(unittest.TestCase):
    def test_storyboard_targets_eight_seconds(self):
        source = "这是一个用于测试语义分镜的完整文案，它包含多个观点和自然停顿。" * 12
        shots = _split_storyboard(source)
        self.assertTrue(shots)
        self.assertEqual(len(source), sum(shot["char_count"] for shot in shots))
        self.assertTrue(all(24 <= shot["char_count"] <= 32 for shot in shots))
        self.assertTrue(all(shot["motion"] == "zoom_in" for shot in shots))

    def test_render_duration_compensates_dissolves(self):
        images = [{"char_count": 28}] * 4
        durations = _allocate_durations(images, 32.0)
        final_duration = sum(durations) - TRANSITION_DUR * (len(images) - 1)
        self.assertAlmostEqual(32.0, final_duration, places=2)


class TtsInputTests(unittest.TestCase):
    def test_only_narration_survives_storyboard_formatting(self):
        formatted = """# 分镜脚本
[00:00-00:08]
画面：老人站在窗边，镜头缓慢推进
旁白：这是第一句正文。
- **文案：这是第二句正文。**
字幕：重复字幕不要朗读
转场：叠化 0.5 秒
---
结尾：这是最后一句。
"""
        self.assertEqual(
            "这是第一句正文。\n这是第二句正文。\n这是最后一句。",
            _clean_tts_text(formatted),
        )

    def test_json_wrapper_and_escaped_ssml_are_removed(self):
        wrapped = json.dumps({"text": "正文一。&lt;break time=\"800ms\"/&gt;正文二。"}, ensure_ascii=False)
        self.assertEqual("正文一。正文二。", _clean_tts_text(wrapped))

    def test_edge_tts_receives_plain_text_not_custom_ssml(self):
        captured: dict[str, str] = {}

        class FakeCommunicate:
            def __init__(self, text, voice, **kwargs):
                captured.update(text=text, voice=voice, boundary=kwargs.get("boundary"))

            async def stream(self):
                yield {"type": "audio", "data": b"audio"}
                yield {"type": "SentenceBoundary", "text": "纯正文。", "offset": 0, "duration": 10_000_000}

        with patch("edge_tts.Communicate", FakeCommunicate):
            audio, segments = asyncio.run(_synthesize("纯正文。", "test-voice"))

        self.assertEqual(b"audio", audio)
        self.assertEqual("纯正文。", captured["text"])
        self.assertNotIn("<speak", captured["text"])
        self.assertEqual("SentenceBoundary", captured["boundary"])
        self.assertEqual(1.0, segments[0]["end"])

    def test_long_script_splits_without_changing_a_character(self):
        text = "第一段说明一个观点，并保留正常停顿。第二段继续解释原因，让内容自然推进。" * 12
        parts = _split_tts_segments(text)
        self.assertGreater(len(parts), 1)
        self.assertEqual(text, "".join(parts))
        self.assertTrue(all(1 <= len(part) <= 105 for part in parts))
        self.assertTrue(all(part[-1] in "。！？!?；;\n" for part in parts[:-1]))

    def test_parallel_parts_merge_timestamps_in_original_order(self):
        text = "第一句内容完整结束。" * 20

        async def fake_part(part, _voice):
            return part.encode("utf-8"), [{"text": part, "start": 0.1, "end": 2.0}]

        with patch("stages.tts._synthesize_part", side_effect=fake_part), patch(
            "stages.tts._concat_mp3", return_value=b"merged"
        ) as concat:
            audio, segments = asyncio.run(_synthesize(text, "test-voice"))

        self.assertEqual(b"merged", audio)
        self.assertGreater(len(segments), 1)
        self.assertEqual(text, "".join(segment["text"] for segment in segments))
        self.assertEqual(0.1, segments[0]["start"])
        self.assertEqual(2.1, segments[1]["start"])
        self.assertEqual(len(segments), len(concat.call_args.args[0]))


class NetworkRetryTests(unittest.TestCase):
    def test_ssl_eof_is_transient_and_retried(self):
        calls = 0

        def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
            return "ok"

        with patch("db.reset_client"), patch("db.time.sleep"):
            self.assertEqual("ok", db.retry(flaky, attempts=3))
        self.assertEqual(3, calls)

    def test_business_error_is_not_retried(self):
        calls = 0

        def invalid():
            nonlocal calls
            calls += 1
            raise ValueError("invalid payload")

        with self.assertRaisesRegex(ValueError, "invalid payload"):
            db.retry(invalid)
        self.assertEqual(1, calls)

    def test_missing_category_column_falls_back_to_legacy_task_fields(self):
        missing_column = RuntimeError("42703 column tasks.content_category does not exist")
        modern = type("Query", (), {"data": None})()
        legacy = type("Query", (), {"data": {"title": "标题", "author": {"name": "作者"}}})()
        with patch("db.retry", side_effect=[missing_column, legacy]):
            task = db.get_task_prompt_context("task-id")
        self.assertEqual("标题", task["title"])
        self.assertNotIn("content_category", task)


class CommentRankingTests(unittest.TestCase):
    def test_replies_affect_ranking_and_duplicates_are_removed(self):
        comments = [
            {"text": "点赞较高", "likes": 20, "replies": 0},
            {"text": "讨论很多", "likes": 1, "replies": 5},
            {"text": "点赞较高", "likes": 3, "replies": 0},
        ]
        ranked = select_hot_comments(comments)
        self.assertEqual(["讨论很多", "点赞较高"], [item["text"] for item in ranked])


if __name__ == "__main__":
    unittest.main()
