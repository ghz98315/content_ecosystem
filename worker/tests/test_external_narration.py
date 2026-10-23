import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from stages import external_narration
from stages import tts


class ExternalNarrationWorkerTests(unittest.TestCase):
    def test_external_mode_never_calls_any_tts_provider(self):
        stage={'id':'s','task_id':'t','params':{'audio_source':'external','external_job':'j'}}
        with patch('stages.external_narration._finish') as finish, patch('stages.tts.get_tts_provider') as provider:
            self.assertEqual(('managed',None),tts.run(stage))
        provider.assert_not_called()
        self.assertEqual('waiting',finish.call_args.args[1])

    def test_invalid_audio_is_reported_without_publishing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'bad.mp3'; source.write_bytes(b'not audio')
            row={'id':'version','original_path':'t/external/version/original.mp3','size_bytes':9,
                 'subtitle_text':'经典。','script_text':'经典。','review':{}}
            client=MagicMock()
            client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data=row
            stage={'id':'s','task_id':'t','params':{'external_id':'version','external_job':'j'}}
            with patch.object(external_narration.db,'get_client',return_value=client), \
                 patch.object(external_narration.storage,'download_artifact',return_value=str(source)), \
                 patch.object(external_narration,'_finish') as finish, \
                 patch.object(external_narration.storage,'upload') as upload:
                external_narration.run(stage)
            self.assertEqual('failed',finish.call_args.args[1])
            self.assertIn('无法解码',finish.call_args.args[2]['error'])
            upload.assert_not_called()

    def test_realignment_reuses_recognition_and_preserves_recording_duration(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'original.wav'
            with wave.open(str(source),'wb') as wav:
                wav.setparams((1,2,16000,0,'NONE','not compressed'))
                wav.writeframes(b'\x00\x00'*16000*4)
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            row={'id':'version','original_path':'t/external/version/original.wav',
                 'size_bytes':source.stat().st_size,'script_text':'读经典。','subtitle_text':'读经典。',
                 'review':{'source_sha256':source_hash,'pause_optimization':{'policy':'cap_internal_silence_1s_v1'},'recognized_text':'读经典',
                           'words':[{'word':'读经典','start':.5,'end':2.5}]}}
            client=MagicMock()
            client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data=row
            stage={'id':'s','task_id':'t','params':{'external_id':'version','external_job':'j'}}
            with patch.object(external_narration.db,'get_client',return_value=client), \
                 patch.object(external_narration.storage,'download_artifact',return_value=str(source)), \
                 patch.object(external_narration,'_finish') as finish, \
                 patch.object(external_narration.storage,'upload') as upload_audio, \
                 patch.object(external_narration.storage,'upload_bytes') as save_subtitle, \
                 patch('stages.transcribe._model') as model:
                external_narration.run(stage)
            model.assert_not_called()
            upload_audio.assert_not_called()
            self.assertEqual('approved',finish.call_args.args[1])
            self.assertEqual(row['original_path'],finish.call_args.args[3])
            report=finish.call_args.args[2]
            self.assertTrue(report['alignment_ready'])
            self.assertTrue(report['auto_processed'])
            self.assertAlmostEqual(4,report['duration'],places=2)
            self.assertEqual(.5,report['segments'][0]['start'])
            self.assertEqual(2.5,report['segments'][0]['end'])
            saved=json.loads(save_subtitle.call_args.args[1])
            self.assertEqual('timeline_v3',saved['input_format'])
            self.assertNotIn('tts.mp3',save_subtitle.call_args.args[0])

    def test_upload_failure_keeps_recognition_for_retry(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'original.wav'
            with wave.open(str(source),'wb') as wav:
                wav.setparams((1,2,16000,0,'NONE','not compressed'));wav.writeframes(b'\x00\x00'*16000*4)
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            row={'id':'version','original_path':'t/external/version/original.wav','size_bytes':source.stat().st_size,'script_text':'读经典。','subtitle_text':'读经典。','review':{}}
            client=MagicMock();client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data=row
            segment=SimpleNamespace(text='读经典',words=[SimpleNamespace(word='读经典',start=.5,end=2.5,probability=.99)])
            with patch.object(external_narration.db,'get_client',return_value=client),patch.object(external_narration.storage,'download_artifact',return_value=str(source)),patch.object(external_narration,'_finish') as finish,patch.object(external_narration.storage,'upload_bytes',side_effect=RuntimeError('temporary upload error')),patch('stages.transcribe._transcribe_media',return_value=([segment],None,{})):
                external_narration.run({'id':'s','task_id':'t','params':{'external_id':'version','external_job':'j'}})
            self.assertEqual('failed',finish.call_args.args[1])
            self.assertEqual(source_hash,finish.call_args.args[2]['source_sha256'])
            self.assertTrue(finish.call_args.args[2]['words'])

    def test_real_mp3_is_reused_without_reencoding_or_audio_upload(self):
        import hashlib,subprocess,imageio_ffmpeg
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'original.mp3'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','4','-c:a','libmp3lame',str(source)],check=True,capture_output=True)
            row={'id':'v','original_path':'t/external/v/original.mp3','size_bytes':source.stat().st_size,'script_text':'读经典。','subtitle_text':'读经典。','review':{'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pause_optimization':{'policy':'cap_internal_silence_1s_v1'},'recognized_text':'读经典','words':[{'word':'读经典','start':.5,'end':2.5}]}}
            client=MagicMock();client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data=row
            with patch.object(external_narration.db,'get_client',return_value=client),patch.object(external_narration.storage,'download_artifact',return_value=str(source)),patch.object(external_narration,'_finish') as finish,patch.object(external_narration.storage,'upload') as upload,patch.object(external_narration.storage,'upload_bytes'):
                external_narration.run({'id':'s','task_id':'t','params':{'external_id':'v','external_job':'j'}})
            self.assertEqual('approved',finish.call_args.args[1]);self.assertEqual(row['original_path'],finish.call_args.args[3]);upload.assert_not_called()
            self.assertAlmostEqual(4,finish.call_args.args[2]['duration'],places=2)


if __name__=='__main__': unittest.main()
