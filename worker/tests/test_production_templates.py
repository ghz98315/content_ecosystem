import unittest
from unittest.mock import MagicMock, patch
from production_templates import validate_template
from stage_timing import StageTiming, close_interrupted
from stages.render import _render_text_settings


class ProductionContractTests(unittest.TestCase):
    def test_guoxue_isolated_from_other_templates(self):
        validate_template({'production_template':'guoxue-v1','template_version':1,'visual_style':'guoxue_gongbi_life','image_aspect_ratio':'4:3'},'image')
        for template in ['health-v1','history-v1','education-v1']:
            with self.assertRaises(ValueError):
                validate_template({'production_template':template,'template_version':1,'visual_style':'guoxue_gongbi_life','image_aspect_ratio':'4:3'},'image')
        with self.assertRaises(ValueError):
            validate_template({'production_template':'guoxue-v2','template_version':2},'render')
        validate_template({},'image')

    def test_local_font_configuration_does_not_leak(self):
        with patch.dict('os.environ',{'RENDER_TITLE_FONT':'private-font','RENDER_TITLE_COLOR':'#BA413B'}):
            other=_render_text_settings({'params':{'production_template':'health-v1'}},{},{})
            self.assertEqual('KaiTi',other['title_font'])
            self.assertEqual('#FFF4D9',other['title_color'])
            guoxue=_render_text_settings({'params':{'production_template':'guoxue-v1'}},{},{})
            self.assertEqual('private-font',guoxue['title_font'])

    def test_timing_records_attempt_and_excludes_crash_downtime(self):
        client=MagicMock()
        with patch('stage_timing.db.get_client',return_value=client):
            timer=StageTiming({'id':'stage','task_id':'task','kind':'render'})
            timer.start();timer.finish()
        payload=client.table.return_value.insert.call_args.args[0]
        result=client.table.return_value.update.call_args.args[0]['meta']
        self.assertEqual('stage_timing',payload['type'])
        self.assertEqual('finished',result['state'])
        self.assertGreaterEqual(result['processing_seconds'],0)
        self.assertIn('ended_at',result)
        client.reset_mock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data=[{'id':'clock','meta':{'stage_id':'stage','state':'running','started_at':'2026-10-16T00:00:00Z'}}]
        with patch('stage_timing.db.get_client',return_value=client):
            close_interrupted({'id':'stage','task_id':'task','updated_at':'2026-10-16T00:01:00Z'})
        self.assertEqual('2026-10-16T00:01:00Z',client.table.return_value.update.call_args.args[0]['meta']['ended_at'])

    def test_timing_failure_does_not_fail_video_work(self):
        with patch('stage_timing.db.retry',side_effect=RuntimeError('offline')):
            timer=StageTiming({'id':'stage','task_id':'task','kind':'render'})
            timer.start();timer.finish()
            self.assertFalse(timer.saved)
