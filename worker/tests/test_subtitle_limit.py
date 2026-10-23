import unittest

from external_alignment import align, validate_cues
from narration import SUBTITLE_MAX_CHARS, enforce_subtitle_limit, strip_subtitle_punctuation, visible_len
from stages.tts import _build_subtitle_cues


class SubtitleLimitTests(unittest.TestCase):
    def test_synthesized_subtitles_use_twelve_character_limit(self):
        text = "先把最重要的事情说清楚，然后再解释为什么这样做。"
        anchors = [{"char_start": 0, "char_end": len(text), "start": 0, "end": 6}]
        cues = _build_subtitle_cues(text, anchors, 6)
        self.assertEqual(strip_subtitle_punctuation(text), "".join(c["text"] for c in cues))
        self.assertTrue(all(c["char_count"] <= SUBTITLE_MAX_CHARS for c in cues))

    def test_external_alignment_and_manual_cues_use_same_limit(self):
        text = "先把最重要的事情说清楚然后再解释为什么这样做"
        words = [{"word": char, "start": i * .2, "end": (i + 1) * .2} for i, char in enumerate(text)]
        duration = len(text) * .2
        cues, _ = align(text, words, duration)
        self.assertTrue(all(visible_len(c["text"]) <= SUBTITLE_MAX_CHARS for c in cues))
        manual = [{"text": text, "start": 0, "end": duration}]
        repaired = validate_cues(text, enforce_subtitle_limit(manual), duration)
        self.assertEqual(text, "".join(c["text"] for c in repaired))
        self.assertTrue(all(visible_len(c["text"]) <= SUBTITLE_MAX_CHARS for c in repaired))

    def test_saved_legacy_cue_reflows_without_changing_time_span(self):
        cues = [{"text": "先把最重要的事情说清楚然后再解释", "start": 2, "end": 5,
                 "char_start": 10, "char_end": 28}]
        repaired = enforce_subtitle_limit(cues)
        self.assertGreater(len(repaired), 1)
        self.assertEqual(cues[0]["text"], "".join(c["text"] for c in repaired))
        self.assertEqual((2, 5), (repaired[0]["start"], repaired[-1]["end"]))
        self.assertTrue(all(visible_len(c["text"]) <= SUBTITLE_MAX_CHARS for c in repaired))


if __name__ == "__main__":
    unittest.main()
