import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from local_materials import add_book_cover_inserts, local_book_cover


class BookCoverInsertTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
