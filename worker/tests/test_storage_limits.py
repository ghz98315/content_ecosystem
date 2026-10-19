import unittest
from unittest.mock import MagicMock,patch
import storage

class StorageLimitTests(unittest.TestCase):
 def test_413_is_actionable_and_not_retried_as_a_chunk_failure(self):
  client=MagicMock();client.post.return_value.status_code=413
  client.post.return_value.text='private-provider-details'
  with patch.object(storage.httpx,'Client') as factory,patch.object(storage.db,'retry',side_effect=lambda fn:fn()):
   factory.return_value.__enter__.return_value=client
   with self.assertRaisesRegex(ValueError,'分片上传也受此限制') as caught:
    storage._upload_resumable('t/audio.wav','unused.wav','audio/wav',100*1024*1024)
  self.assertNotIn('private-provider-details',str(caught.exception));client.patch.assert_not_called()

if __name__=='__main__':unittest.main()
