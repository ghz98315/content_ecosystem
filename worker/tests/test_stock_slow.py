import tempfile,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
from stock_media import selection_entries,make_video_clip
from stages import render

class StockSlowTests(unittest.TestCase):
 def plan(self):return {'allowed_speeds':[1,.5,.3],'reuse_gap_shots':1,'entries':[{'index':i,'duration':10,'candidates':[{'id':a,'duration':4,'url':'https://cdn.coverr.co/'+a} for a in ('a','b')]} for i in range(3)]}
 def test_half_and_third_speed_and_reuse_gap(self):
  plan=self.plan();rows=selection_entries(plan,[{'asset_id':a,'offset':0,'playback_rate':.3} for a in ('a','b','a')]);self.assertEqual(3,rows[0]['source_end'])
  with self.assertRaises(ValueError):selection_entries(plan,[{'asset_id':'a','offset':0,'playback_rate':.3}]*3)
  with self.assertRaises(ValueError):selection_entries(plan,[{'asset_id':a,'offset':0,'playback_rate':.5} for a in ('a','b','a')])
 def test_old_plan_cannot_silently_slow_down(self):
  plan=self.plan();plan.pop('allowed_speeds')
  with self.assertRaises(ValueError):selection_entries(plan,[{'asset_id':a,'offset':0,'playback_rate':.3} for a in ('a','b','a')])
 def test_real_slow_motion_duration(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'output') as folder:
   root=Path(folder);source=root/'source.mp4'
   subprocess.run([render.ff(),'-v','error','-y','-f','lavfi','-i','testsrc2=s=320x240:r=30','-t','2',str(source)],check=True,capture_output=True)
   with patch('stock_media.fetch_source',return_value=source),patch.object(render,'W',360),patch.object(render,'H',640),patch.object(render,'_nvenc_available',return_value=False):
    for rate in (.5,.3):
     output=root/f'{rate}.mp4';make_video_clip({'asset':{},'source_start':0,'playback_rate':rate},5,str(output),frame_mode='landscape_blur',picture_ratio=4/3) if rate==.3 else make_video_clip({'asset':{},'source_start':0,'playback_rate':rate},3,str(output),frame_mode='landscape_blur',picture_ratio=4/3)
     self.assertAlmostEqual(5 if rate==.3 else 3,render._video_duration(str(output)),delta=.1)

if __name__=='__main__':unittest.main()
