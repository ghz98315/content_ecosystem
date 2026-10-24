import tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
from external_asr_repair import missing_windows,repair_omissions
from external_alignment import align,validate_cues

class LocalAsrRepairTests(unittest.TestCase):
 def fixture(self):
  text=''.join(chr(0x4e00+i) for i in range(430))
  complete=[{'word':char,'start':i*.15,'end':(i+1)*.15,'probability':.99} for i,char in enumerate(text)]
  return text,complete,complete[:200]+complete[231:]
 def test_long_omission_with_time_gets_bounded_window(self):
  text,_,words=self.fixture();windows=missing_windows(text,words,65)
  self.assertEqual(1,len(windows));self.assertLess(windows[0][1]-windows[0][0],10)
 def test_no_time_to_speak_does_not_force_repair(self):
  text,_,words=self.fixture()
  for i,w in enumerate(words):w.update(start=i*.15,end=(i+1)*.15)
  self.assertEqual([],missing_windows(text,words,65))
 def test_wrong_recording_still_rejected(self):
  with self.assertRaises(ValueError):align('完全不同的文本',[{'word':'今天吃饭了','start':0,'end':2}],3,repair=True)
 def test_retry_disables_vad_and_keeps_script(self):
  text,complete,words=self.fixture();start,end=missing_windows(text,words,65)[0]
  def recognize(path,*,vad_filter):
   self.assertFalse(vad_filter)
   fresh=[SimpleNamespace(word=w['word'],start=round(w['start']-start,4),end=round(w['end']-start,4),probability=.99) for w in complete if w['start']>=start and w['end']<=end]
   return [SimpleNamespace(words=fresh)],None,{}
  with tempfile.TemporaryDirectory() as tmp,patch('external_asr_repair.subprocess.run'):
   repaired,reports=repair_omissions(text,words,65,'recording',tmp,'ffmpeg',recognize)
  self.assertTrue(reports[0]['accepted'])
  cues,_=align(text,repaired,65,repair=True);self.assertTrue(validate_cues(text,cues,65))

if __name__=='__main__':unittest.main()
