from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rewrite_review import evaluate, format_for_reading, normalized, opening_hook, remainder
from stages.rewrite import _generate_candidates


HOOK = '您是否也遇到过？先别急着下结论。咱们慢慢说清楚。'
OLD = '甲乙丙丁戊己庚辛壬癸' * 60 + '。'
NEW = '春夏秋冬东西南北山川' * 60 + '。'
SOURCE = HOOK + OLD
CONTEXT = {'category': 'social_science', 'keyword': '测试主题', 'title': '测试'}


def response(body: str, reason='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason, message=SimpleNamespace(
        content=json.dumps({'rewritten_remainder': body, 'rewrite_strategy': ['调整论述顺序并重建句式']}, ensure_ascii=False)))])


class LocalReviewTests(unittest.TestCase):
    def test_punctuation_formatting_cannot_hide_reuse(self):
        formatted = SOURCE.replace('甲', ' 甲\n')
        report = evaluate(SOURCE, formatted, HOOK)
        self.assertAlmostEqual(1.0, report['unlocked']['phrase_overlap'])

    def test_paragraph_reordering_is_still_detected(self):
        a = '家人想换工作时，需要先把收入安排解释清楚。'
        b = '担忧并不等于要替孩子作出每一个决定。'
        report = evaluate(HOOK + a + b, HOOK + b + a, HOOK)
        self.assertGreater(report['unlocked']['score'], 0.7)

    def test_changed_tail_is_allowed_and_fixed_hook_measured_separately(self):
        report = evaluate(SOURCE, HOOK + NEW, HOOK)
        self.assertEqual('passed', report['status'])
        self.assertTrue(report['hook_preserved'])
        self.assertLess(report['unlocked']['score'], 0.10)

    def test_hook_floor_routes_to_manual_without_false_pass(self):
        report = evaluate(HOOK + '甲乙丙丁戊己庚辛壬癸。', HOOK + '春夏秋冬东西南北山川。', HOOK)
        self.assertEqual('manual_review', report['status'])
        self.assertGreater(report['locked_floor'], 0.10)
        self.assertFalse(report['retry_issues'])

    def test_format_preserves_content_and_adds_paragraphs(self):
        text = '第一段信息应当完整讲清楚。' * 35
        self.assertEqual(normalized(text), normalized(format_for_reading(text)))
        self.assertIn('\n\n', format_for_reading(text))
        self.assertEqual(HOOK, opening_hook(SOURCE))
        self.assertEqual(OLD, remainder(SOURCE, HOOK))


class RevisionLoopTests(unittest.TestCase):
    def generate(self, replies, mode='initial_dedup'):
        with patch('stages.rewrite._request_rewrite', side_effect=replies) as request:
            result = _generate_candidates(SOURCE, CONTEXT, mode=mode)
        return result, request

    def test_first_pass_stops_without_repairs(self):
        (candidates, _, data), request = self.generate([response(NEW)])
        self.assertEqual(1, request.call_count)
        self.assertTrue(candidates[0].startswith(HOOK))
        self.assertEqual('passed', data['rewrite_review']['status'])

    def test_three_repairs_max_and_keep_latest_draft_and_history(self):
        (candidates, _, data), request = self.generate([response(OLD) for _ in range(4)])
        report = data['rewrite_review']
        self.assertEqual(4, request.call_count)
        self.assertEqual(3, report['revisions_used'])
        self.assertEqual(4, len(report['attempts']))
        self.assertEqual('manual_review', report['status'])
        self.assertEqual('limit_reached', report['stop_reason'])
        self.assertTrue(candidates[0].endswith(OLD))
        self.assertIn('【可改写区重复片段】', request.call_args_list[1].kwargs['messages'][1]['content'])

    def test_pass_on_repair_and_repost_uses_same_policy(self):
        (_, _, data), request = self.generate([response(OLD), response(NEW)], mode='repost_dedup')
        self.assertEqual(2, request.call_count)
        self.assertEqual('passed', data['rewrite_review']['status'])
        self.assertEqual(1, data['rewrite_review']['revisions_used'])

    def test_network_failure_keeps_prior_usable_text(self):
        (candidates, _, data), request = self.generate([response(OLD), RuntimeError('offline')])
        self.assertEqual(2, request.call_count)
        self.assertTrue(candidates[0].endswith(OLD))
        self.assertEqual('service_error', data['rewrite_review']['stop_reason'])

    def test_truncated_or_invalid_repair_does_not_replace_complete_text(self):
        replies = [response(OLD), response(NEW, 'length'), response(NEW, 'length'), response(NEW, 'length')]
        (candidates, _, data), request = self.generate(replies)
        self.assertEqual(4, request.call_count)
        self.assertTrue(candidates[0].endswith(OLD))
        self.assertEqual(1, data['rewrite_review']['selected_attempt'])
        self.assertEqual('manual_review', data['rewrite_review']['status'])


if __name__ == '__main__':
    unittest.main()
