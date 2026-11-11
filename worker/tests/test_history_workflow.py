import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

import config
from history_visuals import compile_history_plan, image_prompt, request_history_plan
from production_templates import validate_template
from rewrite_review import evaluate, history_conversion_tail, length_bounds, opening_hook
from rewrite_skill import resolve_domain
from stages import image, render, rewrite


def _mock_history_stream(payload):
    encoded = json.dumps(payload, ensure_ascii=False)
    chunks = [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part))])
              for part in (encoded[:len(encoded)//2], encoded[len(encoded)//2:])]
    stream = MagicMock()
    stream.__enter__.return_value = iter(chunks)
    return stream


class HistoryWorkflowTests(unittest.TestCase):
    def test_history_storyboard_client_uses_deepseek_without_switching_rewrite(self):
        with patch.object(config, 'DEEPSEEK_API_KEY', 'test-key'), \
             patch.object(config, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.example/v1'), \
             patch.object(config, 'REWRITE_PROVIDER', 'openai'), \
             patch.object(config, 'openai_client') as client:
            self.assertIs(config.history_storyboard_client(), client.return_value)
        client.assert_called_once_with(api_key='test-key', base_url='https://api.deepseek.example/v1',
                                       timeout=config.DEEPSEEK_TIMEOUT, max_retries=0)

    def test_generated_script_locks_both_ends_and_reports_middle_reuse(self):
        hook = '第一句留个悬念。第二句说到旧事。第三句引出人物。第四句回到日常。'
        middle = '甲乙丙丁戊己庚辛壬癸' * 18 + '。'
        tail = '最后，我推荐一本《示例读本》。买不买随您，有空可以翻一翻。'
        source = f'{hook}\n\n{middle}\n\n{tail}'
        rewritten = '春夏秋冬东西南北山川' * 18 + '。'
        response = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps({
            'rewritten_remainder': rewritten, 'rewrite_strategy': ['从结果讲起', '改用生活比喻'],
        }, ensure_ascii=False)))])
        self.assertEqual(tail, history_conversion_tail(source))
        self.assertEqual(hook, opening_hook(source, 'social_science'))
        self.assertFalse(history_conversion_tail(hook + middle))
        with patch.object(rewrite, '_request_rewrite', return_value=response) as call:
            candidates, _, structure = rewrite._generate_candidates(source, {'category':'social_science'})
        self.assertEqual(1, call.call_count)
        self.assertEqual('\n\n'.join((hook, rewritten, tail)), candidates[0])
        report = structure['rewrite_review']
        self.assertTrue(report['tail_preserved'])
        self.assertEqual(0, report['unlocked']['score'])
        self.assertGreater(report['full']['score'], 0.10)
        self.assertIn('转化结尾未逐字保留', evaluate(source, candidates[0][:-1], hook, 'social_science', locked_tail=tail)['retry_issues'])
        self.assertEqual((90, 110), length_bounds('甲' * 100, 'social_science'))
        self.assertEqual('history', resolve_domain(source, category='social_science')['domain'])

    def test_render_template_accepts_old_and_new_snapshots(self):
        for version, style, ratio, mode in ((1, 'history_ink_scroll', '9:16', 'portrait'),
                                            (2, 'history_period_film', '4:3', 'landscape_blur')):
            base = {'production_template':'history-v1', 'content_line':'social_science', 'template_version':version}
            validate_template({**base, 'visual_style':style, 'image_aspect_ratio':ratio}, 'image')
            validate_template({**base, 'frame_mode':mode}, 'render')
        with self.assertRaises(ValueError):
            validate_template({**base, 'visual_style':style, 'image_aspect_ratio':'9:16'}, 'image')

    def test_landscape_history_title_and_subtitle_end_at_the_cover_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.ass'
            render._make_ass([], str(path), title='历史标题', subtitle='历史副标', footnote='脚注', duration=20,
                             landscape_layout=True, cover_titles_only=True)
            events = path.read_text(encoding='utf-8-sig')
        end = render._fmt_ass_time(0)
        self.assertIn(f'0:00:00.00,{end},Heading', events)
        self.assertIn(f'0:00:00.00,{end},Subheading', events)
        self.assertIn(f'0:00:00.00,{render._fmt_ass_time(20)},Footnote', events)

    def test_history_subtitle_uses_white_then_yellow_and_black_outline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.ass'
            render._make_ass([], str(path), title='历史标题', subtitle='第一行\r\n第二行',
                             duration=20, landscape_layout=True, cover_titles_only=True,
                             history_subtitle_style=True)
            events = path.read_text(encoding='utf-8-sig')
        style = next(line for line in events.splitlines() if line.startswith('Style: Subheading,'))
        self.assertEqual(['&H00FFFFFF', '&H000000FF', '&H00000000'], style.split(',')[3:6])
        self.assertIn(r'第一行\N{\1c&H00E6FF&}第二行', events)
        self.assertIn('0:00:00.00,0:00:00.50,Subheading', events)

    def test_numbered_prompts_keep_cast_continuity_and_per_shot_era(self):
        card = {'id':'P1','aliases':['虚构人物甲'],'origin':'西方人','kind':'女子','age':'约40岁',
                'face':'方圆脸、眉骨清晰、棕发','clothing':'细纹粗呢外套'}
        shot = {'index':1,'cast':['P1'],'era':'十九世纪末法国','setting':'虚构人物甲读《示例读本》','composition':'窗边中景'}
        rows = compile_history_plan({'cast':[card], 'shots':[
            shot, {**shot,'index':2,'setting':'站在木案旁'},
            {**shot,'index':3,'cast':[],'era':'二十世纪中期英国','setting':'空书房'},
        ]}, 3)
        self.assertEqual(rows[0]['scene'].split('；')[0], rows[1]['scene'].split('；')[0])
        prompt = image_prompt([row['scene'] for row in rows], start=10)
        self.assertIn('【10】西方人，约40岁，女子', prompt)
        self.assertIn('【12】二十世纪中期英国', prompt)
        self.assertIn('4:3横版3×3九宫格', prompt)
        self.assertNotIn('虚构人物甲', prompt)
        self.assertNotIn('示例读本', prompt)

    def test_image_stage_submits_numbered_landscape_grid_and_saves_individual_prompt(self):
        raw = io.BytesIO()
        Image.new('RGB', (1200, 900), '#bc885f').save(raw, 'PNG')
        stage = {'id':'stage','task_id':'task','params':{'production_template':'history-v1','template_version':2,
            'content_line':'social_science','visual_style':'history_period_film','image_aspect_ratio':'4:3'}}
        plan = [{'index':1,'era':'年代未定','scene':'年代未定的木门与廊道，斜侧光空镜'}]
        with patch.object(image, 'validate_task_template'), \
             patch.object(image, '_find_chosen_text', return_value='旧时街巷，木门轻轻合上。'), \
             patch.object(image.config, 'image_client', return_value=(MagicMock(), 'test-model')), \
             patch.object(image.db, 'get_task_prompt_context', return_value={'content_category':'social_science'}), \
             patch.object(image, '_load_history_visual_plan', return_value=(plan, 'visual-signature')), \
             patch.object(image, '_existing_image_artifacts', return_value={}), \
             patch.object(image, '_generate_grid_bytes', return_value=raw.getvalue()) as generate, \
             patch.object(image.storage, 'upload_bytes') as upload, patch.object(image.storage, 'add_artifact'):
            self.assertEqual('done', image.run(stage)[0])
        self.assertEqual('4:3', generate.call_args.kwargs['size'])
        self.assertIn('【1】年代未定的木门', generate.call_args.args[2])
        index = json.loads(next(call.args[1] for call in upload.call_args_list if call.args[0].endswith('images_index.json')))
        self.assertEqual('4:3', index[0]['cell_ratio'])
        self.assertIn('单幅背景图', index[0]['prompt'])

    def test_philosophical_scenes_pass_concrete_metaphors_to_the_image_model(self):
        client = MagicMock()
        scenes = ['思维可以逐渐打开。', '长期的积累，就像水滴石穿。']
        examples = ['树冠形成可辨的侧脸轮廓', '水滴正落向石面的圆凹，凹处有少许积水']
        payload = {'cast': [], 'shots': [
            {'index': index, 'cast': [], 'era': '年代未定', 'setting': setting, 'composition': '主体位于中央安全区'}
            for index, setting in enumerate(examples, 1)
        ]}
        create = client.chat.completions.create
        create.return_value = _mock_history_stream(payload)
        plan = request_history_plan(client, 'model', scenes)
        rules = create.call_args.kwargs['messages'][0]['content']
        self.assertIn('树冠形成清晰的人头侧影', rules)
        self.assertIn('水滴正对凹陷', rules)
        self.assertIn('具体事件优先照有依据的情节设计', rules)
        self.assertTrue(create.call_args.kwargs['stream'])
        for setting, shot in zip(examples, plan):
            prompt = image_prompt([shot['scene']], grid=1)
            self.assertIn(setting, prompt)
            self.assertIn('手机缩略图', prompt)
            self.assertIn('4:3横版', prompt)

    def test_long_history_plan_keeps_cast_and_global_shot_numbers_across_batches(self):
        card = {'id':'P1','aliases':['示例人物'],'origin':'西方人','kind':'女子','age':'约40岁',
                'face':'棕发方脸','clothing':'深色粗呢外套'}
        rows = [{'index':index,'cast':['P1'],'era':'年代未定','setting':'示例人物翻开书册',
                 'composition':'中景'} for index in range(1, 8)]
        client = MagicMock()
        create = client.chat.completions.create
        create.side_effect = [_mock_history_stream({'cast':[card],'shots':rows[:6]}),
                              _mock_history_stream({'cast':[],'shots':rows[6:]})]
        plan = request_history_plan(client, 'model', ['旁白'] * 7)
        second_request = json.loads(create.call_args.kwargs['messages'][1]['content'])
        self.assertEqual([card], second_request['existing_cast'])
        self.assertEqual(7, second_request['scenes'][0]['index'])
        self.assertEqual(list(range(1, 8)), [shot['index'] for shot in plan])
        self.assertIn('西方人', plan[-1]['scene'])
        self.assertNotIn('示例人物', plan[-1]['scene'])

    def test_history_gateway_timeout_is_identified_before_image_submission(self):
        client = MagicMock()
        timeout = RuntimeError('upstream')
        timeout.status_code = 524
        client.chat.completions.create.side_effect = timeout
        with self.assertRaisesRegex(RuntimeError, '历史社科分镜第1–1镜请求超时，尚未提交生图'):
            request_history_plan(client, 'model', ['旁白'])


if __name__ == '__main__':
    unittest.main()
