import copy,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import stock_media as stock
from stages import image,render

class StockMediaTests(unittest.TestCase):
 def test_lossless_blocks_and_character_budget(self):
  text=('把每天的小事做好，留一点时间看看树木和天空。'*18)+'最后一段。'
  blocks=stock.split_blocks(text)
  self.assertEqual(text,''.join(blocks))
  self.assertGreater(len(blocks),1)
  self.assertTrue(all(80<=sum(c.isalnum() for c in b)<=100 for b in blocks[:-1]))

 def test_untrusted_sources_are_rejected(self):
  for url in ['http://upload.wikimedia.org/a','https://localhost/a','https://upload.wikimedia.org.evil.com/a','https://user:pass@upload.wikimedia.org/a','https://upload.wikimedia.org:8443/a']:
   self.assertFalse(stock.allowed_url(url),url)
  self.assertTrue(stock.allowed_url(stock.CATALOG[0]['url']))

 def plan(self):
  return {'revision':'r1','text_hash':stock.digest('示例文案'),'audio_duration':10,
          'entries':[{'index':0,'sentence':'示例文案','duration':10,'char_count':4,'char_start':0,'char_end':4,'candidates':[copy.deepcopy(stock.CATALOG[0])]}]}

 def test_selection_rejects_short_missing_nan_and_negative(self):
  p=self.plan();asset=p['entries'][0]['candidates'][0]
  for choice in [[],[{'asset_id':'missing','offset':0}],[{'asset_id':asset['id'],'offset':-1}],[{'asset_id':asset['id'],'offset':float('nan')}],[{'asset_id':asset['id'],'offset':80}]]:
   with self.assertRaises(ValueError):stock.selection_entries(p,choice)
  chosen=stock.selection_entries(p,[{'asset_id':asset['id'],'offset':5}])
  self.assertEqual(15,chosen[0]['source_end'])

 def test_unconfirmed_plan_does_not_download_or_generate_images(self):
  p=self.plan();client=MagicMock();stage={'id':'s','task_id':'t','params':{'visual_mode':'stock_video','stock_plan':p}}
  with patch('stages.image._find_chosen_text',return_value='示例文案'),patch.object(stock,'load_audio_timeline',return_value={'duration':10}),patch.object(stock.db,'get_client',return_value=client),patch.object(stock,'fetch_source') as download,patch.object(stock,'build_plan') as generate:
   self.assertEqual(('needs_review',None),stock.run(stage));download.assert_not_called();generate.assert_not_called()
   self.assertEqual('needs_review',client.table.return_value.update.call_args[0][0]['status'])

 def test_changed_audio_invalidates_confirmation(self):
  p=self.plan();stage={'id':'s','task_id':'t','params':{'visual_mode':'stock_video','stock_plan':p,'stock_confirmed_revision':'r1'}}
  with patch('stages.image._find_chosen_text',return_value='示例文案'),patch.object(stock,'load_audio_timeline',return_value={'duration':12}),patch.object(stock.db,'get_client',return_value=MagicMock()),patch.object(stock,'build_plan',return_value={**p,'revision':'r2'}) as replan,patch.object(stock,'fetch_source') as download:
   self.assertEqual(('needs_review',None),stock.run(stage));replan.assert_called_once();download.assert_not_called()

 def test_image_handler_routes_without_calling_paid_generation(self):
  stage={'id':'s','task_id':'t','params':{'visual_mode':'stock_video'}}
  with patch.object(image,'validate_template'),patch.object(image,'validate_task_template'),patch.object(stock,'run',return_value=('needs_review',None)) as handler,patch.object(image.config,'image_client') as paid:
   self.assertEqual(('needs_review',None),image.run(stage));handler.assert_called_once();paid.assert_not_called()

 def test_sources_credit_is_deduplicated(self):
  a={'asset':stock.CATALOG[0]};text=stock.credit_text([a,a]);self.assertEqual(1,text.count('已截取'))

 def test_source_clip_real_ffmpeg_and_duration_guard(self):
  from quality import probe_media
  sample=Path(__file__).resolve().parents[1]/'output/stock-video-evaluation-20261024/waterfall.webm'
  if not sample.exists():self.skipTest('Local network sample unavailable')
  entry={'asset':stock.CATALOG[2],'source_start':1}
  with tempfile.TemporaryDirectory(dir=sample.parent) as directory,patch.object(stock,'fetch_source',return_value=sample),patch.object(render,'W',360),patch.object(render,'H',640),patch.object(render,'_nvenc_available',return_value=False):
   target=str(Path(directory)/'clip.mp4')
   stock.make_video_clip(entry,2,target,frame_mode='landscape_blur',picture_ratio=1)
   metadata=probe_media(target,render.ff())
   self.assertEqual((360,640),(metadata['width'],metadata['height']))
   self.assertAlmostEqual(2,metadata['duration'],delta=.1)
   with self.assertRaisesRegex(ValueError,'时长'):stock.make_video_clip(entry,40,target)

if __name__=='__main__':unittest.main()
