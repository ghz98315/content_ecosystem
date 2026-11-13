import unittest

from spoken_style import spoken_style_issues
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


if __name__ == '__main__':
    unittest.main()
