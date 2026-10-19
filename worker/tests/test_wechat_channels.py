import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import httpx
from resolvers import wechat_channels as wx
from stages import ingest

URL='https://weixin.qq.com/sph/AnhssXs7C3'
PLAY='https://channels.weixin.qq.com/finder-preview/pages/feed?token=test-token&eid=test-eid'
MEDIA='https://finder.video.qq.com/test.mp4?key=signed-test-key'
def response(value,status=200):return httpx.Response(status,json=value)

class ChannelsTests(unittest.TestCase):
 def test_supported_link_and_share_text(self):
  self.assertEqual(wx.normalize_url('分享 '+URL),URL)
  self.assertEqual(wx.normalize_url('['+URL+']('+URL+')'),URL)
 def test_rejects_untrusted_urls(self):
  for url in ['http://weixin.qq.com/sph/a','https://weixin.qq.com.evil.example/sph/a','https://evil.example/?next='+URL,'https://user:pw@weixin.qq.com/sph/a','https://weixin.qq.com/other']:
   with self.subTest(url=url),self.assertRaises(wx.ChannelsError):wx.normalize_url(url)
 def test_cookie_file_updates_without_process_restart(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'.env'
   with patch.object(wx,'ENV_FILE',path):
    path.write_text('YUANBAO_COOKIE="first"',encoding='utf-8');self.assertEqual(wx.cookie_value(),'first')
    path.write_text('YUANBAO_COOKIE="second"',encoding='utf-8');self.assertEqual(wx.cookie_value(),'second')
 def test_missing_cookie_does_not_call_network(self):
  with patch.object(wx,'cookie_value',return_value=''),patch.object(wx.httpx,'Client') as client:
   with self.assertRaisesRegex(wx.ChannelsError,'YUANBAO_COOKIE'):wx.resolve(URL)
   client.assert_not_called()
 def test_cookie_only_sent_to_yuanbao_and_private_values_not_returned(self):
  client=MagicMock();client.post.side_effect=[response({'data':{'wx_export_id':'id','playable_url':PLAY,'desc':'标题','author':'作者'}}),response({'errCode':0,'data':{'feedInfo':{'h264VideoInfo':{'videoUrl':MEDIA},'likeCountFmt':'1.2万'}}})]
  with patch.object(wx,'cookie_value',return_value='session=private-cookie'),patch.object(wx.httpx,'Client') as factory:
   factory.return_value.__enter__.return_value=client;result=wx.resolve(URL)
  first,second=client.post.call_args_list
  self.assertEqual(first.args[0],'https://yuanbao.tencent.com/api/weixin/get_parse_result')
  self.assertEqual(first.kwargs['headers']['Cookie'],'session=private-cookie')
  self.assertNotIn('Cookie',second.kwargs['headers']);self.assertEqual(result.video_url,MEDIA)
  self.assertEqual(result.raw['stats_display']['likes'],'1.2万')
  self.assertNotIn('private-cookie',json.dumps(result.raw));self.assertNotIn('test-token',json.dumps(result.raw))
  self.assertNotIn('signed-test-key',json.dumps(result.raw))
 def test_auth_error_has_safe_actionable_message(self):
  client=MagicMock();client.post.return_value=response({'error':'private-cookie'},401)
  with self.assertRaisesRegex(wx.ChannelsError,'更新 worker/.env') as error:wx._post(client,'fixed')
  self.assertNotIn('private-cookie',str(error.exception))
 def test_redirect_response_is_not_followed_with_credentials(self):
  client=MagicMock();client.post.return_value=response({},302)
  with self.assertRaises(wx.ChannelsError):wx._post(client,'fixed')
  self.assertEqual(client.post.call_count,1)
 def test_invalid_json_and_timeouts_are_sanitized(self):
  for value in [httpx.Response(200,text='not-json private-cookie'),httpx.ReadTimeout('private-cookie')]:
   client=MagicMock()
   if isinstance(value,Exception):client.post.side_effect=value
   else:client.post.return_value=value
   with self.assertRaises(wx.ChannelsError) as error:wx._post(client,'fixed')
   self.assertNotIn('private-cookie',str(error.exception))
 def test_download_rejects_non_tencent_hosts(self):
  for url in ['https://evil.example/a.mp4','https://finder.video.qq.com.evil.example/a','http://finder.video.qq.com/a','https://u:p@finder.video.qq.com/a']:
   with self.assertRaises(wx.ChannelsError):wx._media_url(url)
 def test_download_does_not_forward_credentials(self):
  client=MagicMock();response=MagicMock(status_code=200,is_success=True)
  response.iter_bytes.return_value=iter([b'video']);client.stream.return_value.__enter__.return_value=response
  with patch.object(wx.httpx,'Client') as factory:
   factory.return_value.__enter__.return_value=client;path=wx.download(MEDIA)
  try:self.assertEqual(Path(path).read_bytes(),b'video');self.assertNotIn('Cookie',client.stream.call_args.kwargs['headers'])
  finally:Path(path).unlink(missing_ok=True)
 def test_download_validates_redirect_before_second_request(self):
  client=MagicMock();response=MagicMock(status_code=302,headers={'location':'https://evil.example/a.mp4'})
  client.stream.return_value.__enter__.return_value=response
  with patch.object(wx.httpx,'Client') as factory:
   factory.return_value.__enter__.return_value=client
   with self.assertRaises(wx.ChannelsError):wx.download(MEDIA)
  self.assertEqual(client.stream.call_count,1)
 def test_download_size_limit(self):
  client=MagicMock();response=MagicMock(status_code=200,is_success=True)
  response.iter_bytes.return_value=iter([b'too-large']);client.stream.return_value.__enter__.return_value=response
  with patch.object(wx.httpx,'Client') as factory,patch.object(wx,'MAX_DOWNLOAD_BYTES',4):
   factory.return_value.__enter__.return_value=client
   with self.assertRaises(wx.ChannelsError):wx.download(MEDIA)
 def test_ingest_login_failure_enters_upload_fallback(self):
  with patch.object(wx,'resolve',side_effect=wx.ChannelsError('更新登录态')),patch.object(ingest.db,'set_stage') as save:
   self.assertEqual(ingest._ingest_wechat({'id':'stage','task_id':'task'},URL),('needs_review',None))
   self.assertEqual(save.call_args.args,('stage','needs_review'))
 def test_ingest_saves_descriptions_but_no_signed_media_url(self):
  from resolvers import ResolveResult
  with tempfile.TemporaryDirectory() as tmp:
   video=Path(tmp)/'video.mp4';audio=Path(tmp)/'audio.mp3';video.write_bytes(b'video');audio.write_bytes(b'audio')
   result=ResolveResult(ok=True,title='标题',video_url=MEDIA,raw={'resolver':'wechat_channels_yuanbao'})
   with patch.object(wx,'resolve',return_value=result),patch.object(wx,'download',return_value=str(video)),patch.object(ingest.storage,'extract_audio',return_value=str(audio)),patch.object(ingest.subprocess,'run',return_value=SimpleNamespace(stderr=b'Duration: 00:12:48.02')),patch.object(ingest,'_write_task_meta'),patch.object(ingest.storage,'ensure_bucket'),patch.object(ingest.storage,'upload'),patch.object(ingest.storage,'add_artifact') as add:
    self.assertEqual(ingest._ingest_wechat({'id':'stage','task_id':'task'},URL),('done','task/audio.mp3'))
    self.assertAlmostEqual(add.call_args.kwargs['meta']['duration'],768.02)
    self.assertNotIn('signed-test-key',json.dumps(add.call_args.kwargs['meta']))
   self.assertFalse(video.exists());self.assertFalse(audio.exists())

if __name__=='__main__':unittest.main()
