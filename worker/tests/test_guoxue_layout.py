import tempfile
import unittest
import json
from unittest.mock import MagicMock, patch
from pathlib import Path

from guoxue_visuals import grid_prompt
from stages.image import _guoxue_storyboard, _char_count
from stages.render import _make_ass, _prepare_title_font, H


class GuoxueLayoutTests(unittest.TestCase):
    def test_independent_cover_does_not_consume_narration_range(self):
        import stages.image as module
        text = '家人一起商量生活' * 120
        expected = _guoxue_storyboard(text)
        opened = MagicMock()
        opened.__enter__.return_value.size = (2336,3520)
        with patch.object(module, '_find_chosen_text',return_value=text), \
             patch.object(module, '_existing_image_artifacts',return_value={}), \
             patch.object(module.config, 'image_client',return_value=(MagicMock(),'gpt-image-2')), \
             patch.object(module.db,'get_task_prompt_context',return_value={'content_category':'health'}), \
             patch.object(module,'_generate_grid_bytes',return_value=b'grid') as generate, \
             patch.object(module,'_split_grid',side_effect=lambda raw,n,*args:[b'piece']*n), \
             patch('PIL.Image.open',return_value=opened), \
             patch.object(module.storage,'upload_bytes') as upload, \
             patch.object(module.storage,'add_artifact') as artifact:
            state,path=module.run({'id':'image-stage','task_id':'task','params':{'visual_style':'guoxue_gongbi_life'}})
        self.assertEqual('done',state)
        index=json.loads(next(c.args[1] for c in upload.call_args_list if c.args[0].endswith('/images_index.json')))
        self.assertEqual(len(expected),len(index))
        self.assertEqual(text,''.join(x['sentence'] for x in index))
        self.assertTrue(all(x['cover_path'].endswith('/cover.png') for x in index))
        self.assertEqual(1,sum(c.args[2]=='cover_image' for c in artifact.call_args_list))
        self.assertTrue(all(c.kwargs['resolution']=='4k' for c in generate.call_args_list))

    def test_storyboard_preserves_every_character_and_normal_lengths(self):
        text = ('家人一起商量日常安排，理解彼此的心意。\n' * 60)
        shots = _guoxue_storyboard(text)
        self.assertEqual(text, ''.join(s['text'] for s in shots))
        self.assertTrue(all(75 <= s['char_count'] <= 100 for s in shots))
        self.assertEqual(_char_count(text), shots[-1]['char_end'])
        self.assertTrue(all(a['char_end'] == b['char_start'] for a,b in zip(shots,shots[1:])))

    def test_short_source_is_not_padded_with_invented_copy(self):
        text = ' 先听家人把话说完。\n'
        shots = _guoxue_storyboard(text)
        self.assertEqual(text, ''.join(s['text'] for s in shots))
        self.assertTrue(shots[0]['short_source_exception'])

    def test_grid_uses_traditional_clothes_and_varied_spaces(self):
        prompt = grid_prompt(['在集市买菜', '到田地里劳作', '与家人吃晚饭'], cover=True)
        for required in ['工笔', '千层底', 'Nike', '堂屋', '集市', '田野', '独立封面', '9:16', '3行3列']:
            self.assertIn(required, prompt)
        self.assertIn('不要分隔线', prompt)

    def test_titles_and_footnote_are_final_overlay_events(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sample.ass'
            _make_ass([{'start':0,'end':2,'text':'字幕正文'}],str(path),title='主标题',subtitle='副标题',footnote='脚注',duration=2)
            content = path.read_text(encoding='utf-8-sig')
            self.assertIn('0:00:00.00,0:00:02.50,Heading',content)
            self.assertIn('Subheading',content)
            self.assertIn('Footnote',content)
            self.assertIn(r'\pos(540,1280)',content)
            self.assertIn('字幕正文',content)

    def test_invalid_overlay_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            _make_ass([], 'unused.ass', subtitle_y=float('nan'))


if __name__ == '__main__':
    unittest.main()
