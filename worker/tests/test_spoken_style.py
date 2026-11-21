import unittest

from spoken_style import health_conversational_issues, history_style_issues, spoken_style_issues
from prompt_profiles import SPOKEN_STYLE_RULES


class SpokenStyleTests(unittest.TestCase):
    def test_locked_hook_is_excluded(self):
        self.assertEqual(spoken_style_issues('原稿里说过。\n\n咱们接着聊。', '原稿里说过。'), [])

    def test_body_audit_language_requires_revision(self):
        self.assertTrue(spoken_style_issues('咱们接着聊。医学事实未独立核验。'))
        self.assertTrue(spoken_style_issues('作者转述，依据原稿保留。'))

    def test_attribution_review_variants_and_locked_tail(self):
        for note in ('这句话的具体出处尚有待核实。', '来源仍待考证。', '这段话的归属尚未确认。', '原文版本不详。'):
            with self.subTest(note=note):
                self.assertTrue(spoken_style_issues('咱们接着聊。' + note))
                self.assertEqual([], spoken_style_issues('咱们接着聊。\n\n' + note, tail=note))
        self.assertEqual([], spoken_style_issues('想知道这句话从哪儿来，可以先翻翻这本书。'))
        self.assertEqual([], spoken_style_issues('这批材料的来源未公开。'))

    def test_every_category_receives_shared_rule(self):
        self.assertIn('45岁以上', SPOKEN_STYLE_RULES)
        self.assertIn('开头锁定钩子原样保留', SPOKEN_STYLE_RULES)

    def test_history_disclaimer_and_mechanical_transitions_require_revision(self):
        self.assertTrue(history_style_issues('钩子。\n\n但这不能反过来说，伤害都出于不懂事。', '钩子。'))
        text = '钩子。\n\n但先讲故事。\n\n不过再说一层。\n\n因此回到生活。\n\n最后落下来。'
        self.assertTrue(any('转折词' in issue for issue in history_style_issues(text, '钩子。')))
        self.assertEqual([], history_style_issues('钩子。\n\n他指着炉火讲起那个故事。', '钩子。'))

    def test_womens_growth_rejects_review_tone_and_dense_hedging(self):
        hook = '这是一个关于孤独的故事。'
        body = ('未必有人懂你。\n\n不必急着解释。\n\n这不等于没有价值。\n\n'
                '孤独不意味着失败。\n\n生活不一定给答案。\n\n关系不能保证理解。')
        self.assertTrue(health_conversational_issues(hook + '\n\n' + body, hook, '女性成长与孤独'))
        self.assertTrue(health_conversational_issues('这句话的具体出处尚待核实。', '', '女性成长'))
        self.assertEqual([], health_conversational_issues('她抬头看见飞鸟掠过，终于愿意听听自己的心。', '', '女性成长'))
        self.assertEqual([], health_conversational_issues('服药后的情况不一定相同，应按医生安排处理。', '', '涉及用药治疗'))


if __name__ == '__main__':
    unittest.main()
