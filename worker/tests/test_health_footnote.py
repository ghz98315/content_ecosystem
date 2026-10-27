import tempfile,unittest
from pathlib import Path
from stages.render import _make_ass,_render_text_settings

class HealthFootnoteTests(unittest.TestCase):
 def test_health_defaults_use_book_and_author_without_changing_other_templates(self):
  book={'book_name':'《好好生活》','author':'张老师'}
  health=_render_text_settings({'params':{'production_template':'health-v1'}},book,{})
  self.assertEqual(health['title'],'《好好生活》')
  self.assertEqual(health['subtitle'],'张老师（著）')
  self.assertEqual(health['footnote'],'本文根据《好好生活》书籍和资料整理\n仅作参考分享\n不提供任何健康建议或者行为指导')
  missing=_render_text_settings({'params':{'production_template':'health-v1'}},{},{})
  self.assertEqual(missing['title'],'')
  self.assertEqual(missing['subtitle'],'')
  self.assertNotIn('《》',missing['footnote'])
  guoxue=_render_text_settings({'params':{'production_template':'guoxue-v1'}},book,{})
  self.assertEqual(guoxue['footnote'],'读书分享')
 def test_health_centered_with_literal_line_breaks(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'sub.ass'
   settings=_render_text_settings({'params':{'production_template':'health-v1','video_text':{'title':'健康标题','subtitle':'健康副标题','footnote':'第一行\n第二行'}}},{},{})
   _make_ass([],str(path),landscape_layout=True,picture_ratio=4/3,duration=10,**settings)
   value=path.read_text(encoding='utf-8')
   self.assertIn(r'\an8\pos(540,1393)',value)
   self.assertIn(r'第一行\N第二行',value)
   self.assertIn('Style: Heading,KaiTi,92,&H00FFFFFF,&H000000FF,&H00000000',value)
   self.assertIn('Style: Subheading,KaiTi,56,&H0000E6FF',value)
   self.assertIn('Style: Footnote,KaiTi,29,&H4DFFFFFF',value)
   self.assertIn('Style: Footnote,KaiTi,29,&H4DFFFFFF,&H000000FF,&H00FFFFFF,&H80000000,0,0,0,0,100,100,0,0,1,0,0,3',value)
   self.assertIn(r'\an2\pos(540,527)',value)
 def test_guoxue_keeps_right_alignment(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'sub.ass';settings=_render_text_settings({'params':{'production_template':'guoxue-v1','video_text':{'footnote':'第一行\n第二行'}}},{},{})
   _make_ass([],str(path),landscape_layout=True,picture_ratio=1,duration=10,**settings)
   value=path.read_text(encoding='utf-8');self.assertIn(r'\an9\pos(1010,1528)',value);self.assertIn('第一行 第二行',value)
 def test_health_subtitle_and_captions_share_configured_font(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'health.ass'
   settings=_render_text_settings({'params':{'production_template':'health-v1'}},{},{})
   _make_ass([{'start':0,'end':2,'text':'健康生活'}],str(path),landscape_layout=True,picture_ratio=4/3,duration=2,
             subtitle_font='HarmonyOS Sans SC',narration_font='HarmonyOS Sans SC',**settings)
   value=path.read_text(encoding='utf-8')
   self.assertIn('Style: Subheading,HarmonyOS Sans SC,56,',value)
   self.assertIn('Style: Default,HarmonyOS Sans SC,',value)

if __name__=='__main__':unittest.main()
