import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from scene_visuals import storyboard, count, grid_prompt, validate_plan
from scene_render import write_ass, make_cover
from production_templates import validate_template, validate_task_template
from rewrite_skill import resolve_domain, DomainConflict


class SceneLineTests(unittest.TestCase):
    def test_storyboard_preserves_punctuation_whitespace_and_character_ranges(self):
        source=('深圳的街道连接山海。这里有树荫，也有街巷。\n\n'*13)+'把脚步放慢，再看一眼。'
        shots=storyboard(source)
        self.assertEqual(source,''.join(s['text'] for s in shots))
        self.assertEqual(count(source),shots[-1]['char_end'])
        for previous,current in zip(shots,shots[1:]):
            self.assertEqual(previous['char_end'],current['char_start'])
        self.assertTrue(all(0 < s['char_count']<=80 for s in shots))

    def test_scene_domain_and_visual_contract_cannot_use_book_rules(self):
        self.assertEqual('scene',resolve_domain('深圳大学校园','auto',('scene-v1',),'scene')['domain'])
        with self.assertRaises(DomainConflict): resolve_domain('城市','health',(),'scene')
        with self.assertRaises(DomainConflict): resolve_domain('城市','scene',(),'health')
        with self.assertRaises(ValueError):
            validate_template({'production_template':'scene-v1','template_version':1,'visual_style':'guoxue_gongbi_life','image_aspect_ratio':'4:3'},'image')
        validate_template({'production_template':'scene-v1','template_version':1,'visual_style':'scene_documentary','image_aspect_ratio':'9:16','content_line':'scene'},'image')

    def test_four_grid_prompt_and_invalid_plan_count(self):
        prompt=grid_prompt(['深圳湾海岸','莲花山俯瞰'])
        self.assertIn('2行2列四宫格',prompt)
        self.assertNotIn('3行3列',prompt)
        self.assertNotIn('4:3',prompt)
        with self.assertRaises(ValueError): validate_plan({'shots':[]},[{'index':0}])

    def test_scene_source_ratio_does_not_inherit_legacy_two_thirds_grid(self):
        import io
        from PIL import Image
        from stages.image import _split_grid
        source=Image.new('RGB',(1152,2048),'#4B7080')
        data=io.BytesIO();source.save(data,format='PNG')
        pieces=_split_grid(data.getvalue(),3,grid_cells=2,cell_ratio=9/16,source_ratio=9/16)
        self.assertEqual(3,len(pieces))
        for raw in pieces:
            with Image.open(io.BytesIO(raw)) as image:self.assertAlmostEqual(9/16,image.width/image.height,delta=0.003)

    def test_footer_is_full_duration_without_intro_offset_or_body_titles(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'subs.ass'
            write_ass([{'text':'深圳的山海','start':0,'end':2}],12,'图片由AI生成',str(path))
            text=path.read_text(encoding='utf-8-sig')
            self.assertIn('Dialogue: 2,0:00:00.00,0:00:12.00,Footnote',text)
            self.assertIn('Dialogue: 1,0:00:00.50,0:00:02.00,Narration',text)
            self.assertNotIn('Heading',text)

    def test_default_cover_has_three_intentional_line_lengths_and_fullscreen(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.png';output=Path(temp)/'cover.png'
            Image.new('RGB',(720,1280),'#4B7080').save(source)
            make_cover(str(source),str(output),'深圳的另一面','在山海之间慢下来','图片由AI生成')
            with Image.open(output) as result:self.assertEqual((1080,1920),result.size)

    def test_legacy_db_category_requires_explicit_consistent_scene_snapshots(self):
        client=MagicMock()
        rows=[{'kind':'rewrite','params':{'content_line':'scene','rewrite_domain':'scene'}},
              {'kind':'image','params':{'production_template':'scene-v1','template_version':1,'content_line':'scene','visual_style':'scene_documentary','image_aspect_ratio':'9:16'}},
              {'kind':'render','params':{'production_template':'scene-v1','template_version':1,'content_line':'scene','frame_mode':'scene_fullscreen'}}]
        client.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value.data=rows
        client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data={'content_category':'education'}
        with patch('db.get_client',return_value=client):
            validate_task_template({'task_id':'task','params':rows[1]['params']})
            rows[0]['params']['rewrite_domain']='health'
            with self.assertRaises(ValueError):validate_task_template({'task_id':'task','params':rows[1]['params']})


if __name__=='__main__':unittest.main()
