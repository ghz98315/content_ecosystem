import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from stock_query_planner import batched_queries

def response(items):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'items':items})))])
class QueryPlannerTests(unittest.TestCase):
 def run_plan(self,blocks,outputs,folder):
  client=MagicMock();client.chat.completions.create.side_effect=outputs
  return batched_queries(blocks,'health',{},client,'fake-model','instructions',Path(folder)),client
 def test_partial_long_output_preserves_every_paragraph(self):
  with tempfile.TemporaryDirectory() as folder:
   items,client=self.run_plan(['睡眠与作息']*10,[response([{'index':0,'query':'restful sleep'}]),response([{'index':9,'query':'sunny walk'}])],folder)
   self.assertEqual(10,len(items));self.assertEqual(2,client.chat.completions.create.call_count)
   self.assertEqual('restful sleep',items[0]['query']);self.assertEqual('sunny walk',items[9]['query']);self.assertTrue(items[8]['planning_fallback'])
 def test_duplicates_and_wrong_indices_never_shift_alignment(self):
  with tempfile.TemporaryDirectory() as folder:
   items,_=self.run_plan(['运动','睡眠'],[response([{'index':0,'query':'a'},{'index':0,'query':'b'},{'index':99,'query':'c'}])],folder)
   self.assertTrue(all(item['planning_fallback'] for item in items));self.assertIn('sleep',items[1]['query'])
 def test_invalid_json_falls_back_instead_of_failing_node(self):
  with tempfile.TemporaryDirectory() as folder:
   items,_=self.run_plan(['大脑细胞结构原理'],[SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='incomplete {'))])],folder)
   self.assertEqual('explanation',items[0]['role'])
 def test_complete_batch_reused_without_another_call(self):
  with tempfile.TemporaryDirectory() as folder:
   items,client=self.run_plan(['运动'],[response([{'index':0,'query':'walking park'}])],folder)
   again=batched_queries(['运动'],'health',{},client,'fake-model','instructions',Path(folder))
   self.assertEqual(items,again);self.assertEqual(1,client.chat.completions.create.call_count)

if __name__=='__main__':unittest.main()
