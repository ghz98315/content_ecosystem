import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from rewrite_skill import resolve_domain,prompt_extension,audit_output,DomainConflict
from stages import rewrite
import rewrite_checkpoint
HOOK='您是否也遇到过？先别急着下结论。咱们慢慢说清楚。'
SOURCE=HOOK+'甲乙丙丁戊己庚辛壬癸'*60+'。'
NEW='春夏秋冬东西南北山川'*60+'。'
CONTEXT={'category':'social_science','keyword':'虚构主题','title':'测试'}
def response(body):
 return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps({'rewritten_remainder':body,'rewrite_strategy':['重组表达']})))])

class RewriteSkillTests(unittest.TestCase):
 def test_old_health_category_is_not_medical_routing(self):
  self.assertEqual(resolve_domain('读《道德经》谈处世。',category='health')['domain'],'guoxue')
  self.assertEqual(resolve_domain('一本书讲如何经营小店。')['domain'],'general')
  self.assertEqual(resolve_domain('大学毕业后去工作。')['domain'],'general')
 def test_medical_and_mixed(self):
  self.assertEqual(resolve_domain('关注血糖变化。')['domain'],'health')
  self.assertEqual(resolve_domain('谈《黄帝内经》与血压。')['domain'],'mixed')
  self.assertEqual(resolve_domain('谈日常习惯。',templates=('health-v1',))['domain'],'health')
 def test_conflicts_do_not_silently_bypass_rules(self):
  for explicit,templates in [('guoxue',()),('general',()),('auto',('guoxue-v1',))]:
   with self.assertRaises(DomainConflict):resolve_domain('血糖相关知识。',explicit,templates)
  with self.assertRaises(DomainConflict):resolve_domain('谈《黄帝内经》与血压。','health',('health-v1',))
 def test_prompts_load_only_selected_rules_and_hash(self):
  for domain,files in [('guoxue',['guoxue.md']),('health',['health.md']),('mixed',['guoxue.md','health.md']),('general',[])]:
   prompt,profile=prompt_extension(resolve_domain('虚构主题。',domain))
   self.assertEqual(profile['rule_files'],files);self.assertEqual(len(profile['rules_sha256']),64)
   self.assertIn('information_card',prompt)
 def test_health_audience_and_attribution_rules_are_domain_scoped(self):
  health,_=prompt_extension(resolve_domain('关注血糖变化。','health'))
  mixed,_=prompt_extension(resolve_domain('谈《黄帝内经》与血压。','mixed'))
  guoxue,_=prompt_extension(resolve_domain('读《道德经》谈处世。','guoxue'))
  for prompt in (health,mixed):
   self.assertIn('50岁以上',prompt)
   self.assertIn('银发女性',prompt)
   self.assertIn('不能为了口播自然省掉证据边界',prompt)
  self.assertNotIn('银发女性',guoxue)
 def test_fact_and_output_anchors(self):
  obj={'information_card':[{'id':'F01','source_quote':'孩子更换工作','summary':'换工作'}],
       'rewrite_outline':[{'purpose':'先说担忧','fact_ids':['F01'],'target_quote':'工作要换的时候'}]}
  report=audit_output('孩子更换工作，家人担忧。','工作要换的时候，收入安排要解释。',obj)
  self.assertFalse(report['issues']);self.assertEqual(report['external_originality_status'],'未实测')
  obj['information_card'][0]['source_quote']='不存在的事件'
  self.assertTrue(audit_output('孩子更换工作。','工作要换的时候。',obj)['issues'])
 def test_saved_attempts_resume_within_four_slots(self):
  history=[{'attempt':1,'revision':0,'state':'reserved','text':'','issues':['中断']}]
  calls=[]
  context={**CONTEXT,'rewrite_resume':history,'rewrite_checkpoint':lambda value:calls.append(json.loads(json.dumps(value)))}
  with patch.object(rewrite,'_request_rewrite',return_value=response(NEW)) as request:
   _,_,structure=rewrite._generate_single_candidates(SOURCE,context,'','initial_dedup')
  self.assertEqual(request.call_count,1)
  self.assertEqual(structure['rewrite_review']['selected_attempt'],2)
  self.assertEqual(calls[0][-1]['state'],'reserved')
  json.dumps(structure)
 def test_exhausted_reservations_never_send_fifth_request(self):
  context={**CONTEXT,'rewrite_resume':[{'attempt':i+1,'text':'','issues':['中断']} for i in range(4)]}
  with patch.object(rewrite,'_request_rewrite') as request:
   with self.assertRaises(ValueError):rewrite._generate_single_candidates(SOURCE,context,'','initial_dedup')
  request.assert_not_called()
 def test_checkpoint_created_before_stage_pointer_and_resumed(self):
  events=[];objects={};stage={'task_id':'task','id':'stage'};profile=resolve_domain('虚构文案')
  def upload(path,data,*args):objects[path]=data;events.append('upload')
  client=MagicMock();query=client.table.return_value
  for name in ('update','eq','select'):getattr(query,name).return_value=query
  query.execute.side_effect=lambda:(events.append('pointer') or SimpleNamespace(data=[{'id':'stage'}]))
  with tempfile.TemporaryDirectory() as tmp,patch.object(rewrite_checkpoint.storage,'upload_bytes',side_effect=upload),patch.object(rewrite_checkpoint.storage,'add_artifact'),patch.object(rewrite_checkpoint.db,'get_client',return_value=client):
   history,save=rewrite_checkpoint.prepare(stage,{},'虚构',profile,'','initial_dedup')
   self.assertEqual(events[:2],['upload','pointer']);self.assertEqual(history,[])
   save([{'attempt':1,'state':'reserved'}])
   path=next(iter(objects));generation=path.split('/')[-1][:-5]
   local=Path(tmp)/'progress.json';local.write_bytes(objects[path])
   with patch.object(rewrite_checkpoint.storage,'download_artifact',return_value=str(local)):
    resumed,_=rewrite_checkpoint.prepare(stage,{'rewrite_generation':generation},'虚构',profile,'','initial_dedup')
   self.assertEqual(resumed[0]['attempt'],1)
 def test_unavailable_checkpoint_cannot_restart_count(self):
  with patch.object(rewrite_checkpoint.storage,'download_artifact',side_effect=RuntimeError('offline')),patch.object(rewrite_checkpoint.storage,'upload_bytes') as upload:
   with self.assertRaises(RuntimeError):rewrite_checkpoint.prepare({'task_id':'t','id':'s'},{'rewrite_generation':'11111111-1111-4111-8111-111111111111'},'虚构',{},'','initial_dedup')
  upload.assert_not_called()

if __name__=='__main__':unittest.main()
