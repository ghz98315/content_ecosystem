import unittest
import tempfile
from pathlib import Path

from external_alignment import align, validate_cues
from narration import SUBTITLE_MAX_CHARS, enforce_subtitle_limit, strip_subtitle_punctuation, subtitle_display_text, subtitle_visible_len, split_semantic_units, subtitle_intervals
from stages.tts import _build_subtitle_cues
from stages.render import _make_ass
from scene_render import write_ass as write_scene_ass


class SubtitleLimitTests(unittest.TestCase):
    def test_final_captions_leave_two_tenths_between_normal_cues(self):
        cues = [
            {'text': '第一句', 'start': 0.0, 'end': 1.0},
            {'text': '第二句', 'start': 1.0, 'end': 2.0},
        ]
        intervals = list(subtitle_intervals(cues, 2.0))
        self.assertAlmostEqual(0.8, intervals[0][2])
        self.assertAlmostEqual(1.0, intervals[1][1])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gap.ass'
            _make_ass(cues, str(path), duration=2.0)
            content = path.read_text(encoding='utf-8-sig')
            self.assertIn('0:00:00.50,0:00:01.30,Default', content)

    def test_only_question_and_exclamation_marks_reach_final_video(self):
        raw = "先读《道德经》，再看20%。真的吗？当然！"
        units = split_semantic_units(raw)
        self.assertEqual("先读《道德经》再看20%真的吗？当然！",
                         "".join(unit["text"] for unit in units))
        self.assertGreaterEqual(len(units), 4)  # commas and periods still split screens
        legacy = [{"text": raw, "start": 0.0, "end": 4.0}]
        with tempfile.TemporaryDirectory() as directory:
            for writer in (lambda path: _make_ass(legacy, str(path), duration=4.0),
                           lambda path: write_scene_ass(legacy, 4.0, "", str(path))):
                path = Path(directory) / "captions.ass"
                writer(path)
                dialogue = "\n".join(line for line in path.read_text(encoding="utf-8-sig").splitlines()
                                     if line.startswith("Dialogue:"))
                self.assertNotIn("，", dialogue)
                self.assertNotIn("。", dialogue)
                self.assertIn("？", dialogue)
                self.assertIn("！", dialogue)
                self.assertIn("%", dialogue)

    def test_display_and_validation_share_symbol_normalization(self):
        for source in ("下降20%至5％。", "体温37℃，误差±2%。", "价格¥10，剂量2mg/L。",
                       "比例1:2，费用$5。", "范围5-10，约3‰。", "说明@标记，含#号。"):
            with self.subTest(source=source):
                displayed = subtitle_display_text(source)
                self.assertEqual(strip_subtitle_punctuation(source),
                                 strip_subtitle_punctuation(displayed))
                cues = validate_cues(source, enforce_subtitle_limit([
                    {"text": source, "start": 0.0, "end": 6.0}
                ]), 6.0)
                self.assertEqual(strip_subtitle_punctuation(source),
                                 strip_subtitle_punctuation("".join(c["text"] for c in cues)))

    def test_percent_sign_remains_in_health_subtitles_and_validation(self):
        text = "有些人说下降20%，另一些人说只有5％。"
        self.assertEqual("有些人说下降20%另一些人说只有5%",
                         "".join(unit["text"] for unit in split_semantic_units(text)))
        manual = [{"text": text, "start": 0.0, "end": 5.0}]
        cues = validate_cues(text, enforce_subtitle_limit(manual), 5.0)
        self.assertEqual(2, sum(cue["text"].count("%") for cue in cues))

    def test_synthesized_subtitles_use_ten_character_limit(self):
        text = "先把最重要的事情说清楚，然后再解释为什么这样做。"
        anchors = [{"char_start": 0, "char_end": len(text), "start": 0, "end": 6}]
        cues = _build_subtitle_cues(text, anchors, 6)
        self.assertEqual(strip_subtitle_punctuation(text), strip_subtitle_punctuation("".join(c["text"] for c in cues)))
        self.assertTrue(all(c["char_count"] <= SUBTITLE_MAX_CHARS for c in cues))

    def test_external_alignment_and_manual_cues_use_same_limit(self):
        text = "先把最重要的事情说清楚然后再解释为什么这样做"
        words = [{"word": char, "start": i * .2, "end": (i + 1) * .2} for i, char in enumerate(text)]
        duration = len(text) * .2
        cues, _ = align(text, words, duration)
        self.assertTrue(all(subtitle_visible_len(c["text"]) <= SUBTITLE_MAX_CHARS for c in cues))
        manual = [{"text": text, "start": 0, "end": duration}]
        repaired = validate_cues(text, enforce_subtitle_limit(manual), duration)
        self.assertEqual(text, "".join(c["text"] for c in repaired))
        self.assertTrue(all(subtitle_visible_len(c["text"]) <= SUBTITLE_MAX_CHARS for c in repaired))

    def test_saved_legacy_cue_reflows_without_changing_time_span(self):
        cues = [{"text": "先把最重要的事情说清楚然后再解释", "start": 2, "end": 5,
                 "char_start": 10, "char_end": 28}]
        repaired = enforce_subtitle_limit(cues)
        self.assertGreater(len(repaired), 1)
        self.assertEqual(cues[0]["text"], "".join(c["text"] for c in repaired))
        self.assertEqual((2, 5), (repaired[0]["start"], repaired[-1]["end"]))
        self.assertTrue(all(subtitle_visible_len(c["text"]) <= SUBTITLE_MAX_CHARS for c in repaired))

    def test_short_complete_clause_is_not_fragmented(self):
        units = split_semantic_units("原本就在十字以内。")
        self.assertEqual(["原本就在十字以内"], [unit["text"] for unit in units])

    def test_degree_adverb_stays_with_its_phrase(self):
        units = split_semantic_units("庄子曾经讲过一个很奇怪的故事，为什么喝醉的人摔不死？")
        self.assertEqual("很奇怪的故事", units[1]["text"])

    def test_punctuation_stays_at_line_end_and_is_normalized(self):
        units = split_semantic_units("读《达生》——先看故事；再想想：为什么？")
        captions = [unit["text"] for unit in units]
        self.assertEqual("读《达生》先看故事再想想为什么？", "".join(captions))
        self.assertTrue(all(subtitle_visible_len(text) <= 10 for text in captions))
        self.assertTrue(all(not any(mark in text[:-1] for mark in "，。？！") for text in captions))

    def test_external_alignment_preserves_end_marks_and_source_offsets(self):
        text = "先看《达生》，再想想为什么？"
        words = [{"word": char, "start": index * .2, "end": (index + 1) * .2}
                 for index, char in enumerate(strip_subtitle_punctuation(text))]
        cues, _ = align(text, words, len(words) * .2)
        checked = validate_cues(text, cues, len(words) * .2)
        self.assertEqual("先看《达生》再想想为什么？", "".join(c["text"] for c in checked))
        self.assertEqual(len(text), checked[-1]["char_end"])

    def test_zero_duration_asr_word_is_repaired_between_neighbours(self):
        text = "甲乙丙丁戊己庚辛壬癸"
        words = [{"word": char, "start": i * .3, "end": (i + 1) * .3} for i, char in enumerate(text)]
        words[4] = {"word": "午", "start": 1.35, "end": 1.35}
        cues, coverage = align(text, words, 3.2, repair=True)
        self.assertGreater(coverage, .8)
        self.assertEqual(text, "".join(c["text"] for c in cues))
        self.assertTrue(all(c["end"] > c["start"] for c in cues))
        validate_cues(text, cues, 3.2)


if __name__ == "__main__":
    unittest.main()
