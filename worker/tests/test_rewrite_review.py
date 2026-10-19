from __future__ import annotations

import json
import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch, MagicMock

from rewrite_review import evaluate, format_for_reading, normalized, opening_hook, remainder, length_bounds
from stages.rewrite import _generate_candidates, _request_rewrite
from stages import rewrite


HOOK = '您是否也遇到过？先别急着下结论。咱们慢慢说清楚。'
OLD = '甲乙丙丁戊己庚辛壬癸' * 60 + '。'
NEW = '春夏秋冬东西南北山川' * 60 + '。'
SOURCE = HOOK + OLD
CONTEXT = {'category': 'social_science', 'keyword': '测试主题', 'title': '测试'}


def response(body: str, reason='stop'):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason, message=SimpleNamespace(
        content=json.dumps({'rewritten_remainder': body, 'rewrite_strategy': ['调整论述顺序并重建句式']}, ensure_ascii=False)))])


class LocalReviewTests(unittest.TestCase):
    def test_fifteen_percent_reduction_is_inclusive_but_less_is_rejected(self):
        source = '甲' * 100
        self.assertEqual((85, 110), length_bounds(source))
        at_limit = evaluate(source, '乙' * 85, '')
        below_limit = evaluate(source, '乙' * 84, '')
        self.assertFalse(any('有效字数偏差' in issue for issue in at_limit['retry_issues']))
        self.assertTrue(any('有效字数偏差' in issue for issue in below_limit['retry_issues']))

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
    def test_manual_confirmation_cannot_bypass_length_floor_and_keeps_edits(self):
        source = '甲' * 100
        text = '乙' * 84
        root = Path(__file__).resolve().parents[1] / 'output'
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            artifact = Path(tmp) / 'rewrite.json'
            artifact.write_text(json.dumps({'candidates':['乙' * 95], 'source_text':source,
                                           'rewrite_review':{'status':'manual_review'}},ensure_ascii=False),encoding='utf-8')
            latest = MagicMock(); latest.select.return_value=latest; latest.eq.return_value=latest; latest.single.return_value=latest
            latest.execute.return_value.data={'params':{'chosen_index':0,'final_text':text}}
            query = MagicMock(); query.select.return_value=query; query.eq.return_value=query; query.order.return_value=query; query.limit.return_value=query
            query.execute.return_value.data=[{'storage_path':'task/rewrite.json'}]
            update = MagicMock(); update.update.return_value=update; update.eq.return_value=update
            client=MagicMock(); client.table.side_effect=[latest,query,update]
            with patch.object(rewrite.db,'get_client',return_value=client), patch.object(rewrite.db,'get_task_prompt_context',return_value={}), patch.object(rewrite,'_load_clean_text',return_value=source), patch.object(rewrite,'_task_context',return_value={'category':'health'}), patch.object(rewrite.storage,'download_artifact',return_value=str(artifact)), patch.object(rewrite,'_upload_rewrite') as upload, patch.object(rewrite.compliance,'check_text') as audit:
                status, _=rewrite.run({'id':'stage','task_id':'task'})
            self.assertEqual('needs_review',status)
            self.assertEqual(text,upload.call_args.args[1]['manual_draft']['text'])
            saved=update.update.call_args.args[0]
            self.assertNotIn('chosen_index',saved['params'])
            self.assertIn('至少85字',saved['error'])
            audit.assert_not_called()

    def test_missing_model_does_not_repeat_provider_requests(self):
        with patch('stages.rewrite._llm') as client, patch('stages.rewrite.time.sleep') as sleep:
            request = client.return_value.chat.completions.create
            request.side_effect = RuntimeError('503 model_not_found')
            with self.assertRaisesRegex(RuntimeError, 'model_not_found'):
                _request_rewrite(model='unavailable')
            self.assertEqual(1, request.call_count)
            sleep.assert_not_called()

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

    def test_limit_prefers_length_compliant_draft_over_later_short_revision(self):
        replies = [response(OLD), response(NEW[:400] + '。'), response(NEW), response(NEW[:300] + '。')]
        with patch('stages.rewrite._request_rewrite', side_effect=replies) as request:
            candidates, _, data = _generate_candidates(SOURCE + '9。', CONTEXT)
        self.assertEqual(4, request.call_count)
        self.assertEqual(3, data['rewrite_review']['selected_attempt'])
        self.assertTrue(candidates[0].endswith(NEW))
        self.assertEqual('manual_review', data['rewrite_review']['status'])


if __name__ == '__main__':
    unittest.main()
