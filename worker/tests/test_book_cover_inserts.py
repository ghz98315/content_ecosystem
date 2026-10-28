import unittest

from local_materials import add_book_cover_inserts


class BookCoverInsertTests(unittest.TestCase):
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
        result=add_book_cover_inserts(entries,text,{'segments':cues,'duration':12},'养生书','task/book.jpg')
        covers=[item for item in result if item.get('book_cover_insert')]
        self.assertEqual(2,len(covers))
        self.assertEqual([(0,7),(15,24)],[(item['char_start'],item['char_end']) for item in covers])
        self.assertTrue(all(item['asset']['provider']=='task_artifact' for item in covers))


if __name__=='__main__':unittest.main()
