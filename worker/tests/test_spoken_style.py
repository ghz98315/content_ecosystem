import unittest

from spoken_style import spoken_style_issues
from prompt_profiles import SPOKEN_STYLE_RULES


class SpokenStyleTests(unittest.TestCase):
    def test_locked_hook_is_excluded(self):
        self.assertEqual(spoken_style_issues('原稿里说过。\n\n咱们接着聊。', '原稿里说过。'), [])

    def test_body_audit_language_requires_revision(self):
        self.assertTrue(spoken_style_issues('咱们接着聊。医学事实未独立核验。'))
        self.assertTrue(spoken_style_issues('作者转述，依据原稿保留。'))

    def test_every_category_receives_shared_rule(self):
        self.assertIn('45岁以上', SPOKEN_STYLE_RULES)
        self.assertIn('开头锁定钩子原样保留', SPOKEN_STYLE_RULES)


if __name__ == '__main__':
    unittest.main()
