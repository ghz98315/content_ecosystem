import tempfile,unittest,io
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import stock_media as stock
from production_templates import validate_template
from stages import image,render

class HealthStockTests(unittest.TestCase):
 def test_health_versions_are_isolated(self):
  for version,aspect,mode in [(1,'9:16','portrait'),(2,'4:3','landscape_blur')]:
   validate_template({'production_template':'health-v1','template_version':version,'visual_style':'warm_editorial','image_aspect_ratio':aspect},'image')
   validate_template({'production_template':'health-v1','template_version':version,'frame_mode':mode},'render')
  with self.assertRaises(ValueError):validate_template({'production_template':'health-v1','template_version':2,'frame_mode':'portrait'},'render')

 def test_negative_medical_and_explanation_roles(self):
  for title in ['hospice care','bloody surgery','terminally ill patient','痛苦病床','funeral']:
   self.assertFalse(stock.health_candidate_allowed({'title':title},'explanation'))
  self.assertTrue(stock.health_candidate_allowed({'title':'sunny park slow motion walking'}))
  self.assertTrue(stock.health_candidate_allowed({'title':'anatomy medical diagram'},'explanation'))
  self.assertFalse(stock.health_candidate_allowed({'title':'anatomy medical diagram'},'lifestyle'))

 def test_prompt_uses_actual_health_aspect(self):
  prompt=image._build_grid_prompt(['阳光下适度运动'],'health',aspect='4:3')
  self.assertIn('4:3',prompt);self.assertNotIn('9:16',prompt)
  self.assertIn('临终关怀',prompt);self.assertIn('非血腥',prompt)

 def test_health_grid_source_and_cuts_are_four_by_three(self):
  buffer=io.BytesIO();Image.new('RGB',(1600,1200),'#cedfba').save(buffer,format='PNG')
  image._validate_grid_source(1600,1200,expected_ratio=4/3)
  cuts=image._split_grid(buffer.getvalue(),3,3,4/3)
  for piece in cuts:
   with Image.open(io.BytesIO(piece)) as picture:self.assertAlmostEqual(4/3,picture.width/picture.height,delta=.01)

 def test_public_photo_selection_and_real_render(self):
  asset={'id':'photo','media_type':'image','duration':0,'url':'https://images.pexels.com/photos/1/a.jpg'}
  plan={'processing_defaults':stock.HEALTH_POLICY['processing_defaults'],'entries':[{'index':0,'duration':1,'candidates':[asset]}]}
  entry=stock.selection_entries(plan,[{'asset_id':'photo','offset':0}])[0]
  with self.assertRaises(ValueError):stock.selection_entries(plan,[{'asset_id':'photo','offset':1}])
  with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'output') as folder:
   source=Path(folder)/'photo.png';Image.new('RGB',(800,600),'#9bbf98').save(source)
   target=Path(folder)/'photo.mp4'
   with patch.object(stock,'fetch_source',return_value=source),patch.object(render,'W',360),patch.object(render,'H',640),patch.object(render,'_nvenc_available',return_value=False):
    stock.make_video_clip(entry,1,str(target),frame_mode='landscape_blur',picture_ratio=4/3)
    self.assertAlmostEqual(1,render._video_duration(str(target)),delta=.1)

if __name__=='__main__':unittest.main()
