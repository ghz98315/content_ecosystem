import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

import config
from history_visuals import _portrait_for, compile_history_plan, image_prompt, request_history_cover, request_history_plan, select_history_cover
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

    def test_landscape_history_titles_persist_after_ten_frame_cover(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.ass'
            render._make_ass([], str(path), title='历史标题', subtitle='历史副标', footnote='脚注', duration=20,
                             landscape_layout=True, intro_duration=10 / 30)
            events = path.read_text(encoding='utf-8-sig')
        end = render._fmt_ass_time(20, 10 / 30)
        self.assertIn(f'0:00:00.00,{end},Heading', events)
        self.assertIn(f'0:00:00.00,{end},Subheading', events)
        self.assertIn(f'0:00:00.00,{end},Footnote', events)

    def test_history_subtitle_uses_white_then_yellow_and_black_outline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.ass'
            render._make_ass([], str(path), title='历史标题', subtitle='第一行\r\n第二行',
                             duration=20, landscape_layout=True, intro_duration=10 / 30,
                             history_subtitle_style=True)
            events = path.read_text(encoding='utf-8-sig')
        style = next(line for line in events.splitlines() if line.startswith('Style: Subheading,'))
        heading = next(line for line in events.splitlines() if line.startswith('Style: Heading,'))
        self.assertEqual('&H00FFFFFF', heading.split(',')[3])
        self.assertEqual('&H00000000', heading.split(',')[5])
        self.assertEqual('70', style.split(',')[2])
        self.assertEqual(['&H00FFFFFF', '&H000000FF', '&H00000000'], style.split(',')[3:6])
        footnote = next(line for line in events.splitlines() if line.startswith('Style: Footnote,'))
        caption = next(line for line in events.splitlines() if line.startswith('Style: Default,'))
        self.assertEqual('&H00FFFFFF', footnote.split(',')[3])
        self.assertEqual('&H00000000', footnote.split(',')[5])
        self.assertEqual('72', caption.split(',')[2])
        self.assertEqual('&H00FFFFFF', caption.split(',')[3])
        self.assertEqual('&H00000000', caption.split(',')[5])
        first = next(line for line in events.splitlines() if 'Subheading' in line and '第一行' in line)
        second = next(line for line in events.splitlines() if 'Subheading' in line and '第二行' in line)
        self.assertIn(r'\fs70', first)
        self.assertIn(r'\1c&H00E6FF&', second)
        self.assertIn(r'\pos(540,425)', first)
        self.assertIn(r'\pos(540,515)', second)
        self.assertIn('0:00:00.00,0:00:20.33,Subheading', events)

    def test_history_cover_looks_beyond_first_scene_for_the_main_figure(self):
        images = [
            {'path': 'first.png', 'sentence': '雾中的空街。', 'prompt_scene': '薄雾与街道'},
            {'path': 'second.png', 'sentence': '维特根斯坦追问怎样生活。', 'prompt_scene': '西方人，男子；书房近景'},
            {'path': 'third.png', 'sentence': '维特根斯坦反复追问语言与生活。', 'prompt_scene': '西方人，男子；远景'},
        ]
        script = ''.join(image['sentence'] for image in images)
        self.assertEqual(1, select_history_cover(images, script, '维特根斯坦的一生'))

    def test_history_cover_upscales_existing_image_proportionally(self):
        with tempfile.TemporaryDirectory() as directory:
            source, result = (Path(directory) / name for name in ('source.png', 'enhanced.png'))
            Image.new('RGB', (460, 345), '#a46b47').save(source)
            render.enhance_history_cover(str(source), str(result))
            with Image.open(result) as enhanced:
                self.assertEqual((1080, 810), enhanced.size)
            with Image.open(source) as original:
                self.assertEqual((460, 345), original.size)

    def test_uploaded_cover_preserves_top_and_crops_wide_images_equally(self):
        with tempfile.TemporaryDirectory() as directory:
            source, result = (Path(directory) / name for name in ('source.png', 'enhanced.png'))
            portrait = Image.new('RGB', (360, 640), '#303080')
            portrait.paste('#206020', (0, 0, 360, 270))
            portrait.paste('#a03030', (0, 0, 360, 60))
            portrait.save(source)
            render.enhance_history_cover(str(source), str(result), crop_top_4x3=True)
            with Image.open(result) as image:
                self.assertEqual((1080, 810), image.size)
                self.assertEqual((160, 48, 48), image.getpixel((540, 45)))
                self.assertEqual((32, 96, 32), image.getpixel((540, 760)))

            landscape = Image.new('RGB', (1800, 900), '#303080')
            landscape.paste('#a03030', (300, 0, 1500, 900))
            landscape.save(source)
            render.enhance_history_cover(str(source), str(result), crop_top_4x3=True)
            with Image.open(result) as image:
                self.assertEqual((1200, 900), image.size)
                self.assertEqual((160, 48, 48), image.getpixel((0, 0)))
                self.assertEqual((160, 48, 48), image.getpixel((1199, 899)))

            Image.new('RGB', (1200, 900), '#206020').save(source)
            render.enhance_history_cover(str(source), str(result), crop_top_4x3=True)
            with Image.open(result) as image:
                self.assertEqual((1200, 900), image.size)

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

    def test_image_stage_reserves_first_grid_cell_only_for_automatic_history_cover(self):
        raw = io.BytesIO()
        Image.new('RGB', (1200, 900), '#bc885f').save(raw, 'PNG')
        stage = {'id':'stage','task_id':'task','params':{'production_template':'history-v1','template_version':2,
            'content_line':'social_science','visual_style':'history_period_film','image_aspect_ratio':'4:3',
            'image_provider':'apimart'}}
        shots = [{'index': index, 'text': f'镜头 {index}', 'char_count': 2, 'char_start': index * 2,
                  'char_end': index * 2 + 2, 'estimated_duration': 1, 'motion': 'zoom_in'} for index in range(9)]
        plan = [{'index': index, 'era': '年代未定', 'scene': f'年代未定的木门 {index}'} for index in range(1, 10)]
        cover = {'prompt': '中景下的主题物件', 'era': '年代未定', 'reference_status': 'matched',
                 'reference': {'image_url': 'https://upload.wikimedia.org/ref.png'}}
        for user_cover in (None, 'task/video-cover/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.png'):
            with self.subTest(user_cover=user_cover), \
                 patch.object(image, 'validate_task_template'), \
                 patch.object(image, '_find_chosen_text', return_value='旧时街巷，木门轻轻合上。'), \
                 patch.object(image.config, 'image_client', return_value=(MagicMock(), 'test-model')), \
                 patch.object(image.db, 'get_task_prompt_context', return_value={'content_category':'social_science'}), \
                 patch.object(image, '_history_storyboard', return_value=([dict(shot) for shot in shots], {'max_images': 9})), \
                 patch.object(image, '_load_history_visual_plan', return_value=(plan, 'visual-signature')), \
                 patch.object(image, '_history_render_params', return_value={'video_cover_path': user_cover}), \
                 patch.object(image, '_load_history_cover_plan', return_value=cover) as design, \
                 patch.object(image, '_existing_image_artifacts', return_value={}), \
                 patch.object(image, '_generate_grid_bytes', return_value=raw.getvalue()) as generate, \
                 patch.object(image.storage, 'upload_bytes') as upload, patch.object(image.storage, 'add_artifact'):
                self.assertEqual('done', image.run(stage)[0])
            first = generate.call_args_list[0]
            self.assertEqual('4:3', first.kwargs['size'])
            self.assertIn('【1】年代未定的木门', first.args[2])
            index = json.loads(next(call.args[1] for call in upload.call_args_list if call.args[0].endswith('images_index.json')))
            self.assertEqual(list(range(9)), [shot['index'] for shot in index])
            self.assertEqual([shot['char_start'] for shot in shots], [shot['char_start'] for shot in index])
            self.assertIn('单幅背景图', index[0]['prompt'])
            if user_cover:
                design.assert_not_called()
                self.assertEqual(1, generate.call_count)
                self.assertNotIn('【左上角封面格】', first.args[2])
                self.assertIsNone(index[0]['cover_path'])
                self.assertIsNone(first.kwargs['image_urls'])
            else:
                design.assert_called_once()
                self.assertEqual(2, generate.call_count)
                self.assertLess(first.args[2].index('【左上角封面格】'), first.args[2].index('【1】'))
                self.assertIn('【9】', generate.call_args_list[1].args[2])
                self.assertEqual(['https://upload.wikimedia.org/ref.png'], first.kwargs['image_urls'])
                self.assertIsNone(generate.call_args_list[1].kwargs['image_urls'])
                self.assertTrue(index[0]['cover_path'].endswith('/cover.png'))

    def test_history_cover_design_uses_whole_script_and_only_looks_up_main_subject(self):
        client = MagicMock()
        create = client.chat.completions.create
        create.return_value.choices[0].message.content = json.dumps({
            'subject':'示例人物', 'era':'十九世纪末法国', 'scene':'示例人物在书房的头肩近景',
        }, ensure_ascii=False)
        script = '开头从巴黎讲起。示例人物晚年仍在写作。'
        with patch('history_visuals._portrait_for', return_value=None) as lookup:
            plan = request_history_cover(client, 'model', script, '人物故事')
        lookup.assert_called_once_with('示例人物')
        self.assertEqual(script, json.loads(create.call_args.kwargs['messages'][1]['content'])['script'])
        self.assertEqual('illustrative', plan['reference_status'])
        self.assertIn('十九世纪末法国', plan['prompt'])
        self.assertNotIn('示例人物', plan['prompt'])

    def test_history_render_prioritizes_uploaded_then_generated_cover_and_keeps_legacy(self):
        entries = [{'path': 'body.png', 'cover_path': 'generated.png'}]
        uploaded = 'task/video-cover/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.png'
        self.assertEqual(('uploaded', uploaded, None),
                         render._select_history_intro_cover('task', {'video_cover_path': uploaded}, entries, '', ''))
        self.assertEqual(('history_generated', 'generated.png', None),
                         render._select_history_intro_cover('task', {}, entries, '', ''))
        self.assertEqual(('history_theme_shot', 'body.png', 0),
                         render._select_history_intro_cover('task', {}, [{'path': 'body.png'}], '', ''))
        with self.assertRaises(ValueError):
            render._select_history_intro_cover('another', {'video_cover_path': uploaded}, entries, '', '')

    def test_portrait_lookup_requires_unambiguous_person_and_commons_file(self):
        def claim(value):
            return {'mainsnak': {'datavalue': {'value': value}}}

        person = {'id': 'Q12', 'claims': {
            'P31': [claim({'id': 'Q5'})], 'P18': [claim('Portrait.jpg')],
        }}
        media = {'mime': 'image/jpeg', 'thumburl': 'https://upload.wikimedia.org/portrait.jpg',
                 'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Portrait.jpg',
                 'extmetadata': {'LicenseShortName': {'value': 'Public domain'}}}
        with patch('history_visuals.httpx.Client') as factory:
            get = factory.return_value.__enter__.return_value.get
            payloads = [
                {'search': [{'id': 'Q12', 'label': '示例人物'}, {'id': 'Q13', 'label': '另一个人'}]},
                {'entities': {'Q12': person}},
                {'query': {'pages': [{'imageinfo': [media]}]}},
            ]
            get.side_effect = [MagicMock(**{'json.return_value': payload}) for payload in payloads]
            self.assertEqual(media['descriptionurl'], _portrait_for('示例人物')['source_url'])
            self.assertEqual('File:Portrait.jpg', get.call_args.kwargs['params']['titles'])

            payloads[0]['search'][1]['label'] = '示例人物'
            payloads[1]['entities']['Q13'] = {**person, 'id': 'Q13'}
            get.reset_mock()
            get.side_effect = [MagicMock(**{'json.return_value': payload}) for payload in payloads[:2]]
            self.assertIsNone(_portrait_for('示例人物'))
            self.assertEqual(2, get.call_count)

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
