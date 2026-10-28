import tempfile
import unittest
from pathlib import Path

from classic_quote import quote_overlays
from stages.render import _make_ass


class ClassicQuoteTests(unittest.TestCase):
    def test_attributed_quote_is_aligned_and_group_centered(self):
        script = '《增广贤文》有一句话：“酒中不语真君子，财上分明大丈夫”。这句话讲的是做人做事的分寸。'
        cues = [
            {'start': 1, 'end': 3, 'text': '《增广贤文》有一句话'},
            {'start': 3, 'end': 6, 'text': '酒中不语真君子'},
            {'start': 6, 'end': 9, 'text': '财上分明大丈夫'},
            {'start': 9, 'end': 12, 'text': '这句话讲的是做人做事的分寸'},
        ]
        found = quote_overlays(script, cues, 12)
        self.assertEqual(found, [{'start': 3, 'end': 12, 'lines': ['酒中不语真君子', '财上分明大丈夫']}])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.ass'
            _make_ass(cues, str(path), duration=12, landscape_layout=True, guoxue_text_style=True,
                      account_name='@一卷经典', classic_quotes=found)
            ass = path.read_text(encoding='utf-8-sig')
        self.assertIn('Style: ClassicQuote,', ass)
        self.assertIn('86,&H00FFFFFF', ass)
        self.assertIn(r'\an5\pos(540,960)', ass)
        self.assertIn(r'酒中不语真君子\N财上分明大丈夫', ass)
        self.assertIn('@一卷经典', ass)

    def test_unattributed_or_unaligned_quote_is_ignored(self):
        cues = [{'start': 1, 'end': 4, 'text': '只是另一句话'}]
        self.assertEqual(quote_overlays('“酒中不语真君子，财上分明大丈夫”', cues, 4), [])
        self.assertEqual(quote_overlays('《增广贤文》：“酒中不语真君子，财上分明大丈夫”', cues, 4), [])

    def test_enumerated_book_saying_uses_manuscript_attribution(self):
        script = '今天读《增广贤文》。\n\n第一句是“莫骂酉时妻，一夜受孤凄”。这句话提醒人回家少带怨气。'
        cues = [
            {'start': 0, 'end': 2, 'text': '今天读《增广贤文》'},
            {'start': 2, 'end': 5, 'text': '第一句是莫骂酉时妻'},
            {'start': 5, 'end': 7, 'text': '一夜受孤凄'},
            {'start': 7, 'end': 10, 'text': '这句话提醒人回家少带怨气'},
        ]
        self.assertEqual(
            quote_overlays(script, cues, 10),
            [{'start': 2, 'end': 10, 'lines': ['莫骂酉时妻', '一夜受孤凄']}],
        )

    def test_four_clauses_are_balanced_as_two_lines(self):
        script = '今天读《家训》。\n\n第一句是“修身以正，持家以俭，待人以诚，处事以稳”。随后逐句解释其中的分寸。'
        cues = [
            {'start': 0, 'end': 2, 'text': '今天读《家训》'},
            {'start': 2, 'end': 7, 'text': '第一句是修身以正持家以俭待人以诚处事以稳'},
            {'start': 7, 'end': 10, 'text': '随后逐句解释其中的分寸'},
        ]
        self.assertEqual(
            quote_overlays(script, cues, 10),
            [{'start': 2, 'end': 10, 'lines': ['修身以正，持家以俭', '待人以诚，处事以稳']}],
        )


if __name__ == '__main__':
    unittest.main()
