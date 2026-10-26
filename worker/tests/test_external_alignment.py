import unittest

from external_alignment import align, differences, recording_match_report, validate_cues


class ExternalAlignmentTests(unittest.TestCase):
    def test_unrelated_long_recording_is_not_treated_as_asr_noise(self):
        script='孔子带着学生周游列国，向隐士询问渡口。' * 8
        audio='八十岁也能保持思维敏捷，今天读不老的大脑。' * 35
        report=recording_match_report(script,audio)
        self.assertEqual('unrelated',report['state'])
        self.assertGreater(report['audio_chars'],report['script_chars'])

    def test_small_asr_error_does_not_trigger_wrong_recording_alert(self):
        script='每天读经典，慢慢理解其中的道理。' * 8
        report=recording_match_report(script,script.replace('经典','经点',1))
        self.assertEqual('review',report['state'])

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

    def test_auto_alignment_repairs_minor_asr_typo_without_changing_script(self):
        text='今天读经典，陪您慢慢读懂生活里的道理。'
        words=[{'word':'今天读经点','start':0,'end':2},
               {'word':'陪您慢慢读懂生活里的道理','start':4,'end':9}]
        cues,coverage=align(text,words,10,repair=True)
        checked=validate_cues(text,cues,10)
        self.assertTrue(any(c.get('auto_repaired') for c in checked))
        self.assertTrue(all(not c['needs_timing_review'] for c in checked))
        self.assertLess(coverage,1)
        self.assertEqual(2,checked[0]['end'])
        self.assertEqual(4,checked[1]['start'])

    def test_auto_alignment_rejects_unrelated_recording(self):
        with self.assertRaises(ValueError):
            align('今天读经典，陪您慢慢读懂生活里的道理。',
                  [{'word':'完全不同的录音资料','start':0,'end':3}],4,repair=True)

    def test_auto_alignment_preserves_script_during_short_asr_omission(self):
        text='今天读经典，陪您一起慢慢读懂生活里的道理。'
        words=[{'word':'今天读经典','start':0,'end':2},
               {'word':'陪您慢慢读懂生活里的道理','start':4,'end':9}]
        cues,_=align(text,words,10,repair=True)
        self.assertEqual('今天读经典陪您一起慢慢读懂生活里的道理',''.join(c['text'] for c in validate_cues(text,cues,10)))

    def test_numbers_are_compared_by_pronunciation(self):
        cues,coverage=align('每天15分钟。',[{'word':'每天十五分钟','start':0,'end':3}],4)
        self.assertEqual(1,coverage)
        self.assertEqual('每天15分钟',cues[0]['text'])
        self.assertEqual([],differences('每天15分钟','每天十五分钟'))

    def test_traditional_asr_matches_simplified_script_without_changing_subtitles(self):
        text='今天读《道德经》，把心放慢。明天继续读经典。'
        words=[{'word':'今天讀道德經把心放慢','start':0,'end':4},
               {'word':'明天繼續讀經典','start':5,'end':8}]
        cues,coverage=align(text,words,9,repair=True)
        checked=validate_cues(text,cues,9)
        self.assertEqual(1,coverage)
        self.assertEqual([],differences(text,'今天讀《道德經》，把心放慢。明天繼續讀經典。',words))
        self.assertEqual('今天读道德经把心放慢明天继续读经典',''.join(c['text'] for c in checked))
        self.assertEqual(5,checked[-1]['start'])

    def test_traditional_asr_difference_keeps_raw_suggestion_positions(self):
        items=differences('今天读经典。','今天讀經書。')
        self.assertEqual(1,len(items))
        self.assertEqual('典',items[0]['original'])
        self.assertEqual('書',items[0]['suggestion'])
        self.assertEqual(4,items[0]['raw_start'])

    def test_repeated_spoken_text_is_reported(self):
        self.assertTrue(differences('今天读经典。','今天读经典今天读经典。'))

    def test_batch_edit_uses_exact_raw_positions_and_keeps_punctuation(self):
        text = '每天15分钟，先读经典，再聊心得。'
        items = differences(text, '每天十五分钟，先读经书，再聊感受。')
        self.assertEqual(2, len(items))
        for item in reversed(items):
            start, end = item['raw_start'], item['raw_end']
            self.assertEqual(item['original'], text[start:end])
            text = text[:start] + item['suggestion'] + text[end:]
        self.assertEqual('每天15分钟，先读经书，再聊感受。', text)

    def test_partial_normalized_number_is_not_batch_editable(self):
        items = differences('每天15分钟。', '每天十六分钟。')
        self.assertTrue(items)
        self.assertNotIn('raw_start', items[0])

    def test_unicode_positions_are_browser_utf16_offsets(self):
        item = differences('📖今天读经典。', '📖今天读经书。')[0]
        self.assertEqual(6, item['raw_start'])
        self.assertEqual('典', item['original'])

    def test_insert_and_delete_have_explicit_suggestions(self):
        deleted = differences('今天先读经典。', '今天读经典。')[0]
        self.assertEqual('先', deleted['original'])
        self.assertEqual('', deleted['suggestion'])
        added = differences('今天读经典。', '今天先读经典。')[0]
        self.assertEqual('', added['original'])
        self.assertEqual('先', added['suggestion'])

    def test_word_timestamps_locate_difference_for_preview(self):
        item = differences('今天读经典。', '今天读经书。',
                           [{'word':'今天读经书', 'start':1, 'end':3}])[0]
        self.assertEqual(.5, item['audio_start'])
        self.assertEqual(3.5, item['audio_end'])

    def test_repeated_words_keep_distinct_raw_positions(self):
        text = '先读经典，再读经典，最后讨论。'
        items = differences(text, '先读经典，再读经书，最后讨论。')
        self.assertEqual(1, len(items))
        self.assertEqual(text.rindex('典'), items[0]['raw_start'])

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
