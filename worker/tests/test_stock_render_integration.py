"""Real-ffmpeg regression of the production stock path; cloud I/O is substituted."""
import json,shutil,tempfile,unittest,wave
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from PIL import Image
import stock_media,picture_cache
from stages import render
from quality import probe_media

class StockRenderIntegration(unittest.TestCase):
 def test_video_duration_ignores_non_utf8_filename_diagnostics(self):
  diagnostic=b'Input #0, from \xff\xaa.mp4:\n  Duration: 00:00:42.75, start: 0.000000\n'
  with patch.object(render,'_run_ffmpeg',return_value=SimpleNamespace(stderr=diagnostic)):
   self.assertEqual(42.75,render._video_duration('中文素材.mp4'))

 def test_full_render_reuses_selected_video_and_does_not_call_image_encoder(self):
  source=Path(__file__).resolve().parents[1]/'output/stock-video-evaluation-20261024/waterfall.webm'
  if not source.exists():self.skipTest('Local sample missing')
  with tempfile.TemporaryDirectory(dir=source.parent) as directory,ExitStack() as stack:
   root=Path(directory);thumb=root/'thumb.png';Image.new('RGB',(500,500),'#b8cb9a').save(thumb)
   audio=root/'audio.wav'
   with wave.open(str(audio),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*16000*2)
   count=0
   def copy(src,suffix):
    nonlocal count;count+=1;target=root/(str(count)+suffix);shutil.copyfile(src,target);return str(target)
   entries=[{'path':'thumb','sentence':'虚构文案','char_start':0,'char_end':4,'char_count':4,'source_start':0,'asset':stock_media.CATALOG[2],'processing':stock_media.POLICY['processing_defaults']}]
   def load(task,kind):return {'video_index':entries,'subtitle':{'duration':2,'input_format':'timeline_v3','segments':[{'text':'虚构文案','start':0,'end':2,'char_start':0,'char_end':4}]},'book':{}}.get(kind)
   def table(name):
    q=MagicMock()
    for method in ('select','eq','order','limit','single'):getattr(q,method).return_value=q
    q.execute.return_value=SimpleNamespace(data=[{'created_at':'stock-revision'}] if name=='artifacts' else {})
    return q
   client=MagicMock();client.table.side_effect=table;artifacts=[];durations=[]
   def upload(path,local,mime):
    if mime=='video/mp4':durations.append(probe_media(local,render.ff())['duration'])
   def artifact(task,kind,type_,path,meta=None,**kw):
    if type_=='final':artifacts.append(meta)
   patches=[patch.object(picture_cache,'ROOT',root/'cache'),patch.object(stock_media,'fetch_source',return_value=source),
    patch.object(render,'validate_template'),patch.object(render,'_load_json_artifact',side_effect=load),
    patch.object(render,'_load_audio',side_effect=lambda t:copy(audio,'.wav')),patch.object(render,'_load_bgm_config',return_value=(None,.15,1)),
    patch.object(render.db,'get_client',return_value=client),patch.object(render.db,'get_task_prompt_context',return_value={'content_category':'health'}),
    patch.object(render.storage,'download_artifact',side_effect=lambda p,suffix:copy(thumb,suffix)),patch.object(render.storage,'upload',side_effect=upload),
    patch.object(render.storage,'upload_bytes'),patch.object(render.storage,'add_artifact',side_effect=artifact),
    patch.object(render,'_prepare_title_font',return_value=('KaiTi',False)),patch.object(render,'_nvenc_available',return_value=False),
    patch.object(render,'inspect_render_quality',return_value={'status':'passed','checks':[],'summary':{},'metrics':{}})]
   for p in patches:stack.enter_context(p)
   image=stack.enter_context(patch.object(render,'_make_image_clip',side_effect=AssertionError('Image-mode renderer called')))
   stage={'id':'synthetic','task_id':'synthetic','params':{'visual_mode':'stock_video','frame_mode':'landscape_blur','video_text':{'title':'虚构测试标题'}}}
   self.assertEqual('done',render.run(stage)[0]);image.assert_not_called()
   self.assertAlmostEqual(2.5,durations[-1],delta=.15)
   self.assertEqual('source_motion',artifacts[-1]['motion']);self.assertEqual(0,artifacts[-1]['zoom_amount'])
   self.assertEqual(36,artifacts[-1]['stock_processing']['feather'])
   stage['params']['video_text']['title']='修改标题'
   self.assertEqual('done',render.run(stage)[0]);self.assertTrue(artifacts[-1]['picture_track_cache_hit'])

if __name__=='__main__':unittest.main()
