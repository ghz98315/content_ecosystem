import tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from stock_processing import settings,source_filters,feather_mask,motion_probe,candidate_score,POLICY
import stock_media
from stages import render

class StockProcessingTests(unittest.TestCase):
 def test_legacy_is_unchanged_and_new_policy_is_opt_in(self):
  self.assertEqual('none',settings()['color_style']);self.assertEqual(0,settings()['feather'])
  self.assertEqual('natural_warm_v1',settings(POLICY['processing_defaults'])['color_style'])

 def test_invalid_crop_and_color_are_rejected(self):
  for value in [{'crop_top':.3},{'crop_top':.25,'crop_bottom':.25},{'feather':float('nan')},{'color_style':'unknown'}]:
   with self.assertRaises(ValueError):settings(value)

 def test_mask_edges_soften_without_blurring_center(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'mask.png';feather_mask(path,1080,1080,36)
   with Image.open(path) as image:
    self.assertEqual(0,image.getpixel((0,500)));self.assertEqual(255,image.getpixel((500,500)))
    self.assertTrue(0<image.getpixel((18,500))<255)

 def test_moving_people_and_aerial_rank_above_static_scenery(self):
  self.assertGreater(candidate_score({'title':'family walking outdoors'}),candidate_score({'title':'静景','motion_check':{'state':'nearly_static'}}))
  self.assertGreater(candidate_score({'title':'aerial coast'}),candidate_score({'title':'captioned static_scenery'}))

 def test_all_clips_must_share_color_style(self):
  asset=stock_media.CATALOG[0]
  plan={'entries':[{'index':0,'duration':2,'candidates':[asset]},{'index':1,'duration':2,'candidates':[asset]}]}
  with self.assertRaisesRegex(ValueError,'同一种'):
   stock_media.selection_entries(plan,[{'asset_id':asset['id'],'offset':0,'color_style':'none'},{'asset_id':asset['id'],'offset':3,'color_style':'natural_warm_v1'}])

 def test_real_crop_removes_bottom_caption_and_feather_encodes(self):
  output=Path(__file__).resolve().parents[1]/'output';output.mkdir(exist_ok=True)
  with tempfile.TemporaryDirectory(dir=output) as folder:
   root=Path(folder);source=root/'caption-source.mp4'
   subprocess.run([render.ff(),'-v','error','-y','-f','lavfi','-i','color=c=0x508070:size=640x480:rate=30',
      '-vf','drawbox=x=0:y=430:w=640:h=50:color=magenta:t=fill','-t','2',str(source)],check=True,capture_output=True)
   self.assertEqual('nearly_static',motion_probe(source,render.ff(),duration=2)['state'])
   with patch.object(stock_media,'fetch_source',return_value=source),patch.object(render,'W',360),patch.object(render,'H',640),patch.object(render,'_nvenc_available',return_value=False):
    entry={'asset':stock_media.CATALOG[0],'source_start':0,'processing':{**POLICY['processing_defaults'],'crop_bottom':.12}}
    target=root/'processed.mp4';stock_media.make_video_clip(entry,1,str(target),frame_mode='portrait')
    frame=root/'cropped.png';subprocess.run([render.ff(),'-v','error','-y','-i',str(target),'-frames:v','1',str(frame)],check=True,capture_output=True)
    with Image.open(frame) as picture:
     pink=sum(r>160 and b>130 and g<100 for r,g,b in picture.convert('RGB').getdata())
     self.assertEqual(0,pink,'Original bottom caption area remains visible')
    stock_media.make_video_clip(entry,1,str(root/'feathered.mp4'),frame_mode='landscape_blur',picture_ratio=1)
    self.assertTrue((root/'feathered.mp4').stat().st_size>0)

if __name__=='__main__':unittest.main()
