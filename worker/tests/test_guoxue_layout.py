import tempfile
import unittest
import json
from unittest.mock import MagicMock, patch
from pathlib import Path

from guoxue_visuals import grid_prompt
from stages.image import _guoxue_storyboard, _char_count
from stages.render import _make_ass, _prepare_title_font, H, _landscape_composition_graph, _is_landscape_art, _render_text_settings, _encoder_args, _storage_safe_video_bitrate


class GuoxueLayoutTests(unittest.TestCase):
    def test_history_cover_uses_shared_titles_and_preserves_explicit_blank(self):
        from stages.render import _history_cover_text
        old={'cover_confirmed':True,'cover_title':'旧主标题','cover_subtitle':'旧副标题'}
        self.assertEqual(('新标题',''),_history_cover_text({'params':{'video_text':{'title':'新标题','subtitle':''}}},old))
        self.assertEqual(('旧主标题','旧副标题'),_history_cover_text({'params':{}},old))
        self.assertEqual(('',''),_history_cover_text({'params':{'video_text':{'title':'新标题','subtitle':'副标题'}}},{'cover_confirmed':False}))

    def test_long_video_bitrate_stays_within_storage_budget(self):
        five_minutes = _storage_safe_video_bitrate(300)
        twelve_minutes = _storage_safe_video_bitrate(720)
        self.assertLess(twelve_minutes, five_minutes)
        self.assertGreaterEqual(twelve_minutes, 180)
        with patch('stages.render._nvenc_available', return_value=True):
            args = _encoder_args(target_kbps=twelve_minutes)
        self.assertIn('h264_nvenc', args)
        self.assertIn(f'{twelve_minutes}k', args)

    def test_reference_font_colors_and_outlines_are_independent(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'font.ass'
            _make_ass([],str(path),title='主标题',subtitle='副标题',title_font='PlayFont-ChenkunGBT',duration=2,landscape_layout=True)
            content=path.read_text(encoding='utf-8-sig')
            self.assertIn('Style: Heading,PlayFont-ChenkunGBT,92,&H003B41BA,&H000000FF,&H00F1F3F5,',content)
            self.assertIn('Style: Subheading,KaiTi,56,&H001A1D20,&H000000FF,&H00FFFFFF,',content)
            self.assertIn('Style: Default,PlayFont-ChenkunGBT,72,&H00FFFFFF,',content)
            self.assertIn('Style: Footnote,KaiTi,32,&H001A1D20,&H000000FF,&H00FFFFFF,',content)
        with self.assertRaises(ValueError):
            _make_ass([], 'unused.ass', title_color='red,invalid')

    def test_saved_text_overrides_fallback_and_can_hide_fields(self):
        settings = _render_text_settings({'params': {'video_text': {'title': '自定义标题', 'subtitle': '', 'footnote': '第一期'}}}, {'book_name': '旧书名'}, {'cover_title': '旧标题', 'cover_confirmed': True})
        self.assertEqual('自定义标题', settings['title'])
        self.assertEqual('', settings['subtitle'])
        self.assertEqual('第一期', settings['footnote'])

    def test_landscape_text_tracks_picture_edges_and_long_titles_fit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sample.ass'
            _make_ass([], str(path), title='长'*32, subtitle='副'*48, footnote='脚注', duration=2, landscape_layout=True)
            content = path.read_text(encoding='utf-8-sig')
            self.assertIn(r'\an2\pos(540,419)', content)
            self.assertIn(r'\an2\pos(540,499)', content)
            self.assertIn(r'\an9\pos(1010,1393)', content)
            self.assertIn(r'\fs26\q2', content)

    def test_square_picture_moves_all_three_text_anchors(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'square.ass'
            _make_ass([],str(path),title='主标题',subtitle='副标题',footnote='脚注',duration=2,landscape_layout=True,picture_ratio=1)
            content=path.read_text(encoding='utf-8-sig')
            self.assertIn(r'\an2\pos(540,284)',content)
            self.assertIn(r'\an2\pos(540,364)',content)
            self.assertIn(r'\an9\pos(1010,1528)',content)
            self.assertIn('Style: Footnote,KaiTi,32,',content)
        from PIL import Image
        from stages.image import _split_grid
        import io
        source=io.BytesIO()
        Image.new('RGB',(2048,2048),'#d8d0bd').save(source,format='PNG')
        cells=_split_grid(source.getvalue(),4,grid_cells=2,cell_ratio=1.0)
        self.assertEqual(len(cells),4)
        for cell in cells:
            with Image.open(io.BytesIO(cell)) as image:
                self.assertEqual(image.width,image.height)
        self.assertIn('1:1',grid_prompt(['书房静读'],grid_cells=2,aspect='1:1'))

    def test_landscape_composition_keeps_full_foreground(self):
        from PIL import Image
        from stages.image import _split_grid, _validate_grid_source
        import io
        graph = _landscape_composition_graph()
        self.assertIn('scale=1080:810:force_original_aspect_ratio=decrease', graph)
        self.assertIn('overlay=0:555', graph)
        self.assertIn('gblur=sigma=36', graph)
        self.assertNotIn('zoompan', graph)
        _validate_grid_source(4096,3072,expected_ratio=4/3)
        with self.assertRaises(ValueError):
            _validate_grid_source(3072,4096,expected_ratio=4/3)
        source = io.BytesIO()
        Image.new('RGB',(1200,900)).save(source,format='PNG')
        pieces = _split_grid(source.getvalue(),9,3,4/3)
        self.assertEqual(9,len(pieces))
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'cell.png'
            file.write_bytes(pieces[0])
            self.assertTrue(_is_landscape_art(str(file)))

    def test_independent_cover_does_not_consume_narration_range(self):
        import stages.image as module
        text = '家人一起商量生活' * 120
        expected = _guoxue_storyboard(text)
        opened = MagicMock()
        opened.__enter__.return_value.size = (4096,3072)
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
        self.assertTrue(all(c.kwargs['size']=='4:3' for c in generate.call_args_list))
        self.assertTrue(all(x['cell_ratio']=='4:3' for x in index))

    def test_storyboard_preserves_every_character_and_normal_lengths(self):
        text = ('家人一起商量日常安排，理解彼此的心意。\n' * 60)
        shots = _guoxue_storyboard(text)
        self.assertEqual(text, ''.join(s['text'] for s in shots))
        self.assertTrue(all(100 <= s['char_count'] <= 130 for s in shots))
        self.assertEqual(_char_count(text), shots[-1]['char_end'])
        self.assertTrue(all(a['char_end'] == b['char_start'] for a,b in zip(shots,shots[1:])))

    def test_short_source_is_not_padded_with_invented_copy(self):
        text = ' 先听家人把话说完。\n'
        shots = _guoxue_storyboard(text)
        self.assertEqual(text, ''.join(s['text'] for s in shots))
        self.assertTrue(shots[0]['short_source_exception'])

    def test_grid_uses_traditional_clothes_and_varied_spaces(self):
        prompt = grid_prompt(['在集市买菜', '到田地里劳作', '与家人吃晚饭'], cover=True, grid_cells=3)
        for required in ['工笔', '淡墨', 'Nike', '堂屋', '集市', '田野', '独立封面', '4:3', '3行3列']:
            self.assertIn(required, prompt)
        self.assertIn('不要分隔线', prompt)
        four = grid_prompt(['在集市买菜', '到田地里劳作'], grid_cells=2)
        self.assertIn('2行2列四宫格', four)
        self.assertIn('参考图只决定笔触', four)

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
