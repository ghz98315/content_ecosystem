import unittest

from external_alignment import align, differences, validate_cues


class ExternalAlignmentTests(unittest.TestCase):
    def test_long_recorded_pause_is_preserved_in_subtitles(self):
        words = [{'word':'今天读经典','start':0.3,'end':2.0},
                 {'word':'明天再继续','start':5.0,'end':7.0}]
        cues, coverage = align('今天读经典。明天再继续。',words,8)
        self.assertEqual(1,coverage)
        self.assertEqual(2.0,cues[0]['end'])
        self.assertEqual(5.0,cues[1]['start'])
        self.assertEqual(2,len(validate_cues('今天读经典。明天再继续。',cues,8)))

    def test_missing_sentence_does_not_receive_fabricated_times(self):
        cues,_=align('今天读经典。明天再继续。',[{'word':'今天读经典','start':0,'end':2}],8)
        self.assertTrue(cues[-1]['needs_timing_review'])
        self.assertIsNone(cues[-1]['start'])

    def test_numbers_are_compared_by_pronunciation(self):
        cues,coverage=align('每天15分钟。',[{'word':'每天十五分钟','start':0,'end':3}],4)
        self.assertEqual(1,coverage)
        self.assertEqual('每天15分钟',cues[0]['text'])
        self.assertEqual([],differences('每天15分钟','每天十五分钟'))

    def test_repeated_spoken_text_is_reported(self):
        self.assertTrue(differences('今天读经典。','今天读经典今天读经典。'))

    def test_subtitle_cannot_exceed_audio_or_overlap(self):
        for cues in ([{'text':'经典','start':1,'end':3}],
                     [{'text':'经','start':0,'end':1.5},{'text':'典','start':1,'end':2}],
                     [{'text':'经典','start':float('nan'),'end':2}]):
            with self.assertRaises(ValueError): validate_cues('经典',cues,2)

    def test_manual_correction_cannot_drop_words(self):
        with self.assertRaises(ValueError):
            validate_cues('今天读经典',[{'text':'今天经典','start':0,'end':2}],3)

    def test_book_title_protection_and_timing_monotonicity(self):
        text='读《道德经》，把心放慢。'
        cues,coverage=align(text,[{'word':'读道德经','start':0,'end':2}, {'word':'把心放慢','start':3,'end':5}],6)
        self.assertEqual(1,coverage)
        checked=validate_cues(text,cues,6)
        self.assertTrue(any('道德经' in c['text'] for c in checked))
        self.assertLessEqual(checked[0]['end'],checked[-1]['start'])


if __name__=='__main__': unittest.main()
