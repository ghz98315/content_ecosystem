import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from PIL import Image

from local_materials import add_book_cover_inserts, add_book_cover_pip, local_book_cover, _book_cover_settings
from stages.render import _book_cover_pip_graph


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
        self.assertEqual([{'start':0,'end':3},{'start':8,'end':12}],result[0]['book_cover_pip']['intervals'])

    def test_pip_is_large_centered_and_has_no_extra_frame(self):
        graph=_book_cover_pip_graph(3,4/3,'ass=subs.ass:fontsdir=fonts', ['between(t,3.8,6.1)'])
        self.assertIn('scale=760:570:force_original_aspect_ratio=decrease',graph)
        self.assertIn('overlay=(W-w)/2:555+(810-h)/2',graph)
        self.assertNotIn('pad=',graph)
        self.assertNotIn('color=0xF3EBDD',graph)


if __name__=='__main__':unittest.main()
