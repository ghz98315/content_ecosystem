import unittest,tempfile,subprocess,hashlib,sys
from pathlib import Path
from unittest.mock import patch,MagicMock
import media_upload as m
class MediaUploadTests(unittest.TestCase):
 def test_limits(self):
  m._cached_upload_limit.cache_clear()
  client=MagicMock();client.storage.get_bucket.return_value.file_size_limit=10_000_000
  with patch.object(m.db,'get_client',return_value=client):self.assertEqual(m.upload_limit_bytes(),9_600_000)
  m._cached_upload_limit.cache_clear()
 def test_small_unchanged(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'a.mp3';p.write_bytes(b'abc')
   with m.prepared_file(p,'audio/mpeg',limit=4) as output:self.assertEqual(output,str(p))
 def test_empty_and_data_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'a.bin';p.write_bytes(b'')
   with self.assertRaises(ValueError):
    with m.prepared_file(p,'application/octet-stream',limit=1):pass
   p.write_bytes(b'abc')
   with self.assertRaises(ValueError):
    with m.prepared_file(p,'application/octet-stream',limit=1):pass
   self.assertEqual(p.read_bytes(),b'abc')
 def test_large_wav_real(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'large.wav'
   subprocess.run([m._ffmpeg(),'-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=192000','-t','70','-ac','2',str(p)],check=True,capture_output=True)
   before=hashlib.sha256(p.read_bytes()).hexdigest();self.assertGreater(p.stat().st_size,50_000_000)
   with m.prepared_file(p,'audio/wav',limit=48_000_000) as output:
    self.assertLess(Path(output).stat().st_size,48_000_000);self.assertAlmostEqual(m.duration(output),70,delta=.2)
   self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),before);self.assertFalse(Path(output).exists())
if __name__=='__main__':unittest.main()
