import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from coverr_source import assets_from_payload,search
from stock_timing import timed_blocks
from stock_media import build_plan

class CoverrTimingTests(unittest.TestCase):
 def test_only_free_original_supported_media(self):
  good={'id':'1','duration':'50.5','max_width':1920,'max_height':1080,'urls':{'mp4_download':'https://cdn.coverr.co/test.mp4'},'tags':['ocean']}
  rows=assets_from_payload({'hits':[good,{**good,'is_premium':True},{**good,'is_ai_generated':True},{**good,'duration':'nan'},{**good,'urls':{'mp4':'http://cdn.coverr.co/a'}}]})
  self.assertEqual(1,len(rows));self.assertEqual(50.5,rows[0]['duration'])
 def timeline(self,text):return {'duration':100,'segments':[{'text':text,'char_start':0,'char_end':len(text),'start':0,'end':100}]}
 def test_long_shots_lossless_and_audio_based(self):
  text=('看看海边的天空。'*100);subs=self.timeline(text);parts=timed_blocks(text,subs)
  self.assertEqual(text,''.join(parts));self.assertEqual(2,len(parts))
 def test_short_sources_shorten_shots_without_looping(self):
  text='看海边天空。'*100;subs=self.timeline(text)
  asset={'id':'x','duration':20,'provider':'coverr','url':'https://cdn.coverr.co/a','title':'ocean'}
  with patch('stock_media.search_candidates',return_value=([asset],[])):
   plan=build_plan(text,subs,'health',policy={'matching_mode':'atmosphere','shot_target_seconds':[40,60]})
  self.assertEqual(text,''.join(e['sentence'] for e in plan['entries']))
  self.assertTrue(all(0<e['duration']<=20 for e in plan['entries']))
  self.assertEqual(100,plan['entries'][-1]['end']);self.assertTrue(plan['notices'])
 def test_cache_uses_no_api_call(self):
  import hashlib
  with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'COVERR_API_KEY':'fake'}),patch('coverr_source.httpx.Client') as client:
   signature=hashlib.sha256(b'fake').hexdigest()[:16];path=Path(folder)/('coverr-'+hashlib.sha256((signature+'ocean').encode()).hexdigest()+'.json');path.write_text(json.dumps({'hits':[]}))
   self.assertEqual(([],[]),search('ocean',Path(folder)));client.assert_not_called()

if __name__=='__main__':unittest.main()
