import os,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
import numpy as np
import picture_cache
from stages import render,transcribe

class DetailRecoveryTests(unittest.TestCase):
 def test_task_and_content_isolate_picture_cache(self):
  self.assertNotEqual(picture_cache.cache_path('a',{'revision':1}),picture_cache.cache_path('b',{'revision':1}))
  self.assertNotEqual(picture_cache.cache_path('a',{'revision':1}),picture_cache.cache_path('a',{'revision':2}))
 def test_picture_cache_restores_and_expires(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(picture_cache,'ROOT',Path(tmp)/'cache'):
   source=Path(tmp)/'input';source.write_bytes(b'picture-track');target=Path(tmp)/'restored'
   cached=picture_cache.cache_path('task',{'version':1});picture_cache.save(cached,source)
   self.assertTrue(picture_cache.restore(cached,target));self.assertEqual(source.read_bytes(),target.read_bytes())
   old=time.time()-picture_cache.MAX_AGE-10;os.utime(cached,(old,old))
   self.assertFalse(picture_cache.restore(cached,target))
 def test_picture_cache_obeys_budget(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(picture_cache,'ROOT',Path(tmp)/'cache'),patch.object(picture_cache,'MAX_BYTES',5):
   source=Path(tmp)/'input';source.write_bytes(b'123456')
   picture_cache.save(picture_cache.cache_path('task',{}),source)
   self.assertLessEqual(sum(p.stat().st_size for p in picture_cache.ROOT.glob('*.mp4')),5)
 def test_asr_uses_pcm_and_consumes_lazy_segments(self):
  audio=np.array([.1,-.2],dtype=np.float32)
  model=MagicMock();model.transcribe.return_value=(iter([SimpleNamespace(text='文案')]),SimpleNamespace(duration=1))
  with patch.object(transcribe.subprocess,'run',return_value=SimpleNamespace(stdout=audio.tobytes())),patch.object(transcribe,'_model',return_value=model):
   segments,info,metrics=transcribe._transcribe_media('input.mp3')
  self.assertEqual('文案',segments[0].text);self.assertIsInstance(model.transcribe.call_args.args[0],np.ndarray)
  self.assertIn('recognition_seconds',metrics)
 def test_intro_join_copies_packets(self):
  with patch.object(render,'_video_duration',side_effect=[.5,10]),patch.object(render,'_concat_clips_exact') as concat:
   render._concat_intro('cover','content','out','tmp')
  concat.assert_called_once_with(['cover','content'],10.5,'out','tmp')
 def test_gpu_failure_automatically_falls_back(self):
  audio=np.array([.1],dtype=np.float32);cpu=MagicMock()
  cpu.transcribe.return_value=(iter([SimpleNamespace(text='完整')]),SimpleNamespace(duration=1))
  with patch.object(transcribe.config,'WHISPER_DEVICE','cuda'),patch.object(transcribe.subprocess,'run',return_value=SimpleNamespace(stdout=audio.tobytes())),patch.object(transcribe,'_model',side_effect=[RuntimeError('CUDA out of memory'),cpu]) as model:
   segs,info,metrics=transcribe._transcribe_media('source')
  self.assertEqual('cpu',metrics['device']);self.assertEqual('完整',segs[0].text)
  self.assertEqual(('cpu','int8'),model.call_args.args)
 def test_landscape_motion_is_visible_and_uniform(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'image.png';Image.new('RGB',(400,300)).save(source)
   with patch.object(render,'_run_ffmpeg') as encode:
    render._make_landscape_clip(str(source),30,str(Path(tmp)/'out.mp4'),motion='zoom_in')
   args=encode.call_args.args[0];graph=args[args.index('-filter_complex')+1]
   self.assertIn('0.16',graph);self.assertIn('(on/899)',graph);self.assertNotIn('pow(on/',graph)
   self.assertIn('crop=4320:3240,format=yuv444p',graph)
   self.assertIn('s=2160x1620:fps=30,scale=1080:810',graph)

if __name__=='__main__':unittest.main()
