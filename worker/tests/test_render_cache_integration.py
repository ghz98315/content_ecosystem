"""Synthetic real-ffmpeg regression. No cloud data or model requests."""
import json,shutil,tempfile,unittest,wave
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from PIL import Image,ImageDraw
import picture_cache
from stages import render

class RenderCacheIntegration(unittest.TestCase):
 def test_render_twice_reuses_picture_track_when_only_title_changes(self):
  with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
   root=Path(directory);image=root/'source.png'
   canvas=Image.new('RGB',(800,600),'#ddd0b2');draw=ImageDraw.Draw(canvas)
   for x in range(0,800,25):draw.line((x,0,800-x,600),fill='#333333',width=3)
   canvas.save(image)
   audio=root/'source.wav'
   with wave.open(str(audio),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*16000*2)
   def copy(source,suffix):
    target=root/(str(len(list(root.iterdir())))+suffix);shutil.copyfile(source,target);return str(target)
   artifacts=[]
   def artifact(task,kind,type_,path,meta=None,**kwargs):
    if type_=='final':artifacts.append(meta)
   def load(task,kind):
    return {'image_index':[{'path':'test-image','text':'虚构文案'}],
       'subtitle':{'duration':2,'segments':[{'start':0,'end':2,'text':'虚构文案'}]},
       'book':{'book_name':'测试','author':'测试'}}.get(kind,{})
   client=MagicMock();query=client.table.return_value
   for name in ('select','eq','order','limit','single'):getattr(query,name).return_value=query
   query.execute.return_value=SimpleNamespace(data=[{'created_at':'fixed-revision'}])
   # Audio stage uses a dict, artifact revision uses a list.
   def table(name):
    q=MagicMock()
    for method in ('select','eq','order','limit','single'):getattr(q,method).return_value=q
    q.execute.return_value=SimpleNamespace(data=[{'created_at':'fixed-revision'}] if name=='artifacts' else {})
    return q
   client.table.side_effect=table
   patches=[patch.object(picture_cache,'ROOT',root/'cache'),patch.object(render,'validate_template'),
    patch.object(render,'_load_json_artifact',side_effect=load),patch.object(render,'_load_audio',side_effect=lambda task:copy(audio,'.wav')),
    patch.object(render,'_load_bgm_config',return_value=(None,.1,1)),patch.object(render,'_apply_image_replacements',side_effect=lambda task,images:images),
    patch.object(render.db,'get_client',return_value=client),patch.object(render.db,'get_task_prompt_context',return_value={'content_category':'health'}),
    patch.object(render.db,'retry',side_effect=lambda fn:fn()),patch.object(render.storage,'download_artifact',side_effect=lambda path,suffix:copy(image,suffix)),
    patch.object(render.storage,'upload'),patch.object(render.storage,'upload_bytes'),patch.object(render.storage,'add_artifact',side_effect=artifact),
    patch.object(render,'_prepare_title_font',return_value=('KaiTi',False)),patch.object(render,'inspect_render_quality',return_value={'status':'passed','checks':[],'summary':{},'metrics':{}})]
   for item in patches:stack.enter_context(item)
   make=stack.enter_context(patch.object(render,'_make_image_clip',wraps=render._make_image_clip))
   stage={'id':'synthetic-stage','task_id':'synthetic-task','params':{'frame_mode':'landscape_blur','video_text':{'title':'初次标题'}}}
   self.assertEqual(render.run(stage)[0],'done');self.assertEqual(make.call_count,1)
   stage['params']['video_text']['title']='修改标题'
   self.assertEqual(render.run(stage)[0],'done');self.assertEqual(make.call_count,1)
   self.assertEqual([item['picture_track_cache_hit'] for item in artifacts],[False,True])
   self.assertEqual([item['text_layout']['title'] for item in artifacts],['初次标题','修改标题'])
   self.assertEqual(artifacts[-1]['phase_seconds']['image_clips_seconds'],0)

if __name__=='__main__':unittest.main()
