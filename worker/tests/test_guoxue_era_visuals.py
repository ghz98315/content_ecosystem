import unittest
from guoxue_visuals import infer_era, grid_prompt


class EraVisualTests(unittest.TestCase):
    def test_modern_life_beats_classic_reference(self):
        self.assertEqual(infer_era('今天子女换工作，想起《道德经》'), '现代')

    def test_periods_are_distinct(self):
        self.assertEqual(infer_era('民国街巷里两人交谈'), '民国')
        self.assertEqual(infer_era('庄子在战国时期讲故事'), '先秦')

    def test_grid_preserves_four_three_and_style(self):
        prompt=grid_prompt(['今天子女换工作','庄子在战国时期讲故事'],aspect='4:3')
        self.assertIn('4:3',prompt)
        self.assertIn('21世纪',prompt)
        self.assertIn('先秦时代',prompt)
        self.assertIn('熟宣纸',prompt)


if __name__ == '__main__': unittest.main()
