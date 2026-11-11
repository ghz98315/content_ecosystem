import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from PIL import Image

from local_materials import add_book_cover_inserts, add_book_cover_pip, local_book_cover, _book_cover_settings, book_cover_pip_intervals, book_cover_relevant, render_book_cover, shared_book_cover_settings, resolve_book_cover
from stages.render import _book_cover_pip_graph, _prepare_book_cover_pip, _select_stock_cover
from music_presets import is_user_preset


class BookCoverInsertTests(unittest.TestCase):
    def test_skipped_book_stage_uses_confirmed_rewrite_title_for_local_cover(self):
        cover = {'provider': 'local_book_cover', 'relative_path': '30_健康/越吃越瘦越吃越年轻01.png'}
        def artifact(_task, kind):
            return {'book_title': '越吃越瘦越吃越年轻'} if kind == 'rewrite' else {'skipped': True}
        with patch('local_materials.db.retry', return_value=SimpleNamespace(data={'params': {}})), \
             patch('stages.render._load_json_artifact', side_effect=artifact), \
             patch('local_materials.local_book_cover', return_value=cover) as lookup, \
             patch('local_materials.network_book_cover') as network:
            found, title = _book_cover_settings('task-1')
        self.assertEqual('越吃越瘦越吃越年轻', title)
        self.assertEqual(cover, found)
        lookup.assert_called_once_with(title)
        network.assert_not_called()

    def test_local_cover_ignores_numeric_version_suffix_and_prefers_01(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'30_健康';folder.mkdir()
            Image.new('RGB',(300,500),'red').save(folder/'少食生活02.jpeg')
            Image.new('RGB',(400,600),'blue').save(folder/'少食生活01.png')
            with patch('local_materials.library_root',return_value=root):
                result=local_book_cover('《少食生活》')
            self.assertIsNotNone(result)
            self.assertEqual('30_健康/少食生活01.png',result['relative_path'])

    def test_local_cover_reads_nested_common_image_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'30_健康'/'书籍封面';folder.mkdir(parents=True)
            Image.new('RGB',(300,500),'red').save(folder/'自在生活.bmp')
            with patch('local_materials.library_root',return_value=root):
                result=local_book_cover('自在生活')
            self.assertEqual('30_健康/书籍封面/自在生活.bmp',result['relative_path'])

    def test_shared_cover_is_preferred_and_validated_for_all_content_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shared=root/'90_书籍封面';shared.mkdir()
            health=root/'30_健康';health.mkdir()
            Image.new('RGB',(300,500),'red').save(health/'道德经01.png')
            Image.new('RGB',(400,600),'blue').save(shared/'道德经.png')
            with patch('local_materials.library_root',return_value=root):
                found=local_book_cover('道德经')
                self.assertEqual('90_书籍封面/道德经.png',found['relative_path'])
                self.assertEqual(shared/'道德经.png',resolve_book_cover(found))

    def test_shared_cover_requires_book_recommendation_and_skips_missing_cover(self):
        self.assertTrue(book_cover_relevant('这本《道德经》放在手边，闲时翻看。','道德经'))
        self.assertFalse(book_cover_relevant('今天讲《道德经》中的一个故事。','道德经'))
        with patch('local_materials._book_cover_settings',return_value=(None,'道德经')), \
             patch('local_materials.local_book_cover',return_value=None):
            self.assertEqual((None,'道德经'),shared_book_cover_settings('task','把《道德经》放在床头翻看'))

    def test_manual_cover_is_kept_and_saved_index_can_restore_the_pip(self):
        asset = {'provider':'task_artifact','storage_path':'task/book_cover.png'}
        with patch('local_materials._book_cover_settings', return_value=(asset, '自在生活')):
            self.assertEqual((asset, '自在生活'), shared_book_cover_settings('task', '今天谈日常安排'))
        entries = [{'book_cover_pip': {'asset': asset, 'book_name':'自在生活', 'intervals':[]}}]
        subtitles = {'duration': 25, 'segments': [
            {'text':'今天聊《自在', 'start':0,'end':2,'char_start':0,'char_end':6},
            {'text':'生活》', 'start':2,'end':4,'char_start':6,'char_end':9},
            {'text':'末尾再聊《自在', 'start':17,'end':19,'char_start':9,'char_end':16},
            {'text':'生活》', 'start':19,'end':21,'char_start':16,'char_end':19},
        ]}
        with patch('local_materials.shared_book_cover_settings', return_value=(None, '自在生活')):
            source, intervals = render_book_cover('task', '今天聊《自在生活》，末尾再聊《自在生活》', subtitles, entries)
        self.assertEqual(asset, source)
        self.assertEqual(2, len(intervals))
        self.assertTrue(intervals[-1]['start'] >= 15)
        self.assertTrue(all(item['end'] - item['start'] >= 3 for item in intervals))

    def test_video_cover_prefers_upload_then_local_book_preset_then_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / '91_成片预设封面'; folder.mkdir()
            image = folder / '自在生活封面.png'; Image.new('RGB', (320, 480), 'red').save(image)
            task = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa'
            uploaded = f'{task}/video-cover/bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb.jpg'
            entries = [{'cover_path': 'stock-frame.jpg'}]
            with patch('local_materials.library_root', return_value=root):
                self.assertEqual(('uploaded', uploaded), _select_stock_cover(task, {'video_cover_path': uploaded}, '自在生活', entries))
                self.assertEqual(('local_preset', str(image)), _select_stock_cover(task, {}, '《自在生活》', entries))
                self.assertEqual(('selected_frame', 'stock-frame.jpg'), _select_stock_cover(task, {}, '另一册书', entries))
                with self.assertRaises(ValueError):
                    _select_stock_cover('another-task', {'video_cover_path':uploaded}, '自在生活', entries)

    def test_personal_music_preset_only_accepts_the_owning_account(self):
        owner = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa'
        path = f'user-music/{owner}/health/bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb--5rWL6K-V.mp3'
        self.assertTrue(is_user_preset(path, owner))
        self.assertFalse(is_user_preset(path, 'other-owner'))
        self.assertFalse(is_user_preset(path.replace('/health/', '/health/../'), owner))

    def test_first_and_last_spoken_title_use_confirmed_cover(self):
        text='今天读养生书。中间讲饮食和运动。最后再回到养生书。'
        cues=[
            {'text':'今天读《养生书》','start':0,'end':3,'char_start':0,'char_end':7},
            {'text':'中间讲饮食和运动','start':3,'end':8,'char_start':7,'char_end':15},
            {'text':'最后再回到《养生书》','start':8,'end':12,'char_start':15,'char_end':24},
        ]
        entries=[{'index':0,'sentence':text,'char_start':0,'char_end':24,'char_count':24,
                  'start':0,'end':12,'duration':12,'source_start':5,'source_end':17,
                  'playback_rate':1,'asset':{'id':'v','relative_path':'30_健康/a.mp4'},'path':'preview.jpg'}]
        asset={'id':'book','provider':'local_book_cover','media_type':'image','relative_path':'30_健康/养生书01.png'}
        result=add_book_cover_inserts(entries,text,{'segments':cues,'duration':12},'养生书',asset,'task/book.jpg')
        covers=[item for item in result if item.get('book_cover_insert')]
        self.assertEqual(2,len(covers))
        self.assertEqual([(0,7),(15,24)],[(item['char_start'],item['char_end']) for item in covers])
        self.assertTrue(all(item['asset']['provider']=='local_book_cover' for item in covers))
        self.assertEqual([(0,3),(8,12)],[(item['start'],item['end']) for item in covers])
        self.assertEqual([3,4],[item['duration'] for item in covers])
        self.assertAlmostEqual(12,sum(item['duration'] for item in result))

    def test_pip_keeps_video_segments_and_marks_spoken_title_ranges(self):
        text='今天读养生书。中间讲饮食和运动。最后再回到养生书。'
        cues=[
            {'text':'今天读《养生书》','start':0,'end':3,'char_start':0,'char_end':7},
            {'text':'中间讲饮食和运动','start':3,'end':8,'char_start':7,'char_end':15},
            {'text':'最后再回到《养生书》','start':8,'end':12,'char_start':15,'char_end':24},
        ]
        entries=[{'index':0,'start':0,'end':12,'duration':12,'asset':{'provider':'local_library','relative_path':'30_健康/a.mp4'}}]
        cover={'provider':'local_book_cover','relative_path':'30_健康/养生书01.png'}
        result=add_book_cover_pip(entries,text,{'segments':cues,'duration':12},'养生书',cover,'task/book.jpg')
        self.assertEqual(1,len(result))
        self.assertEqual(12,result[0]['duration'])
        self.assertEqual([{'start':0.0,'end':5.0},{'start':7.0,'end':12.0}],result[0]['book_cover_pip']['intervals'])

    def test_cover_is_still_required_when_title_is_not_spoken(self):
        timeline={'segments':[{'text':'今天谈饮食','start':0,'end':3,'char_start':0,'char_end':5}], 'duration':30}
        self.assertEqual([{'start':0.0,'end':5.0},{'start':25.0,'end':30.0}],
                         book_cover_pip_intervals('今天谈饮食',timeline,'自在生活'))

    def test_pip_is_large_centered_and_has_no_extra_frame(self):
        graph=_book_cover_pip_graph(3,4/3,'ass=subs.ass:fontsdir=fonts', ['between(t,3.8,6.1)'])
        self.assertIn('[3:v]zoompan=',graph)
        self.assertIn('overlay=(W-w)/2:555+(810-h)/2',graph)
        self.assertNotIn('pad=',graph)
        self.assertNotIn('color=0xF3EBDD',graph)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'cover.png';target=Path(directory)/'prepared.png'
            Image.new('RGB',(1792,1344),'red').save(source)
            _prepare_book_cover_pip(source,target)
            with Image.open(target) as prepared:self.assertEqual((760,570),prepared.size)


if __name__=='__main__':unittest.main()
