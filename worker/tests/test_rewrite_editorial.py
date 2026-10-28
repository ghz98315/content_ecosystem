import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rewrite_editorial import scene_plan_audit, health_attribution_issues, repair_scope, apply_paragraph_edits
from rewrite_review import length_bounds, evaluate


class EditorialTests(unittest.TestCase):
    def plan(self):
        return {'information_card': [
            {'id': 'F01', 'source_quote': '虚构甲城有河岸'},
            {'id': 'F02', 'source_quote': '虚构乙城有古桥'}],
            'scene_plan': {'content_shape': 'roundup', 'ranking_type': 'unordered',
                'selected': 'A', 'selection_reason': '先看河岸再看古桥形成区别',
                'alternatives': [
                    {'id': 'A', 'structure': '空间变化', 'outline': ['河岸', '古桥'], 'reason': '地点对照'},
                    {'id': 'B', 'structure': '主题组织', 'outline': ['两城关系', '各自特色'], 'reason': '按主题聚合'}],
                'units': [{'entity': '虚构甲城', 'fact_ids': ['F01'], 'memory_point': '河岸',
                           'entry_angle': '空间', 'target_quote': '河岸连接虚构甲城'}], 'hook_risks': []}}

    def test_scene_units_require_source_entity_and_corresponding_evidence(self):
        obj = self.plan()
        self.assertFalse(scene_plan_audit('虚构甲城有河岸。虚构乙城有古桥。', '河岸连接虚构甲城。', obj)['issues'])
        wrong = copy.deepcopy(obj); wrong['scene_plan']['units'][0]['fact_ids'] = ['F02']
        self.assertTrue(scene_plan_audit('虚构甲城有河岸。虚构乙城有古桥。', '河岸连接虚构甲城。', wrong)['issues'])
        wrong = copy.deepcopy(obj); wrong['scene_plan']['units'][0]['entity'] = '不存在的丙城'
        self.assertTrue(scene_plan_audit('虚构甲城有河岸。', '河岸连接虚构甲城。', wrong)['issues'])

    def test_fake_two_plans_and_missing_output_anchor_do_not_pass(self):
        obj = self.plan(); obj['scene_plan']['alternatives'][1]['outline'] = ['河岸', '古桥']
        self.assertTrue(scene_plan_audit('虚构甲城有河岸。', '河岸连接虚构甲城。', obj)['issues'])
        self.assertTrue(scene_plan_audit('虚构甲城有河岸。', '无关正文。', self.plan())['issues'])
        self.assertEqual({}, scene_plan_audit('', '', {'scene_plan': {'units': 'invalid'}})['plan'])

    def test_patch_keeps_every_unselected_paragraph_verbatim_and_rejects_escape(self):
        paragraphs = ['已经确认的第一段。', '需修改的第二段。', '末段和转场保持原样。']
        result = apply_paragraph_edits(paragraphs, [{'index': 1, 'text': '第二段更自然。'}], [1])
        self.assertEqual([paragraphs[0], '第二段更自然。', paragraphs[2]], result.split('\n\n'))
        for edits in ([{'index': 0, 'text': '偷偷改变'}], [{'index': 1, 'text': ''}], [{'index': True, 'text': '错误编号'}]):
            with self.assertRaises(ValueError): apply_paragraph_edits(paragraphs, edits, [1])

    def test_global_length_issue_never_restricts_repair_to_local_paragraphs(self):
        previous = {'text': '第一段完整。\n\n重复片段需要改。', 'issues': ['有效字数偏差过大'],
                    'similarity': {'unlocked': {'repeated_fragments': ['重复片段']}}}
        self.assertEqual([], repair_scope(previous, '')[1])
        previous['issues'] = ['可改写部分重复指标 20%']
        self.assertEqual([1], repair_scope(previous, '')[1])

    def test_health_preserves_necessary_attribution_but_reports_production_language(self):
        hook = '原稿说到这是开头锁定。'
        self.assertFalse(health_attribution_issues(hook + '\n\n今天结合《虚构书》分享。作者记录的是个人体验，不能推广到所有人。', hook))
        self.assertTrue(health_attribution_issues('原稿提到需要休息。', ''))
        self.assertTrue(health_attribution_issues('书中说到要看条件。\n\n书中提到适用范围。', ''))

    def test_category_limits_remain_independent(self):
        self.assertEqual((90, 110), length_bounds('甲' * 100, 'scene'))
        self.assertEqual((85, 90), length_bounds('甲' * 100, 'health'))
        self.assertEqual((85, 110), length_bounds('甲' * 100, 'guoxue'))

    def test_revision_loop_reassembles_patch_and_rechecks_against_original_source(self):
        from stages.rewrite import _generate_single_candidates
        hook = '您想看看吗？先看一个地方。再看另一处。'
        source = hook + '壬' * 330 + '。'
        paragraphs = ['乙' * 110 + '。', '需改' + '丙' * 108 + '。', '丁' * 110 + '。']
        previous = hook + '\n\n' + '\n\n'.join(paragraphs)
        report = evaluate(source, previous, hook)
        report['unlocked']['repeated_fragments'] = ['需改']
        saved = {'attempt': 1, 'text': previous, 'structure': {'source_text': source},
                 'similarity': report, 'issues': ['可改写部分重复指标 20%'], 'strategy': [], 'complete': True}
        reply = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
            content=json.dumps({'paragraph_edits': [{'index': 1, 'text': '戊' * 110 + '。'}]}, ensure_ascii=False)))])
        context = {'category': 'social_science', 'rewrite_resume': [saved]}
        with patch('stages.rewrite._request_rewrite', return_value=reply) as request:
            candidates, _, structure = _generate_single_candidates(source, context, '', 'initial_dedup')
        self.assertEqual(1, request.call_count)
        self.assertEqual([hook, paragraphs[0], '戊' * 110 + '。', paragraphs[2]], candidates[0].split('\n\n'))
        self.assertEqual('paragraphs', structure['rewrite_review']['attempts'][-1]['revision_scope']['mode'])
        self.assertEqual(source, structure['source_text'])


if __name__ == '__main__': unittest.main()
