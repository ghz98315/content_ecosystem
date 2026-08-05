from __future__ import annotations

import json
import unittest

from resolvers.self_resolver import select_hot_comments
from stages.image import _split_storyboard
from stages.render import _allocate_durations, TRANSITION_DUR
from stages.rewrite import _candidate_issues, _parse_candidates


class RewriteQualityTests(unittest.TestCase):
    def test_structured_single_draft_is_complete(self):
        source = "这是原文内容。" * 20
        text = "这就是原文内容。" * 20
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
