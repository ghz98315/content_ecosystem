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
CONTEXT={'category':'education','keyword':'虚构主题','title':'测试'}
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
 def test_incidental_classic_quote_respects_the_selected_health_line(self):
  context = '遇到意见不合时，她先分清自己能改变什么，再决定下一步怎么走。' * 12
  source = context + '庄子说：井蛙不可以语于海。'
  profile = resolve_domain(source, 'health', ('health-v1',))
  self.assertEqual('health', profile['domain'])
  self.assertEqual('庄子', profile['evidence']['incidental_classic_quote'])
  with self.assertRaises(DomainConflict):
   resolve_domain(source + '接下来讲庄子的三个故事。', 'health', ('health-v1',))
  with self.assertRaises(DomainConflict):
   resolve_domain(context + '《庄子》是本期要读的书。', 'health', ('health-v1',))
 def test_prompts_load_only_selected_rules_and_hash(self):
  for domain,files in [('guoxue',['guoxue.md']),('health',['health.md']),('mixed',['guoxue.md','health.md']),('general',[])]:
   prompt,profile=prompt_extension(resolve_domain('虚构主题。',domain))
   self.assertEqual(profile['rule_files'],files);self.assertEqual(len(profile['rules_sha256']),64)
   self.assertIn('information_card',prompt)
 def test_history_rules_keep_narrative_and_move_disclaimers_to_review(self):
  prompt,profile=prompt_extension(resolve_domain('荣格在塔楼里讲了一个故事。',category='social_science'))
  self.assertEqual('history-1.3',profile['version'])
  self.assertIn('场景、人物动作、家庭或心理案例',prompt)
  self.assertIn('对话可以改写',prompt)
  self.assertIn('口播中删除免责',prompt)
  self.assertIn('必须深度塑造阅读价值',prompt)
  self.assertIn('至少结合三种方法',prompt)
  self.assertIn('不要求逐项举证',prompt)
  self.assertIn('直接按可靠依据修正文稿',prompt)
  self.assertIn('retention_beats',prompt)
  self.assertIn('每450—550字',prompt)
  self.assertGreater(prompt.rfind('口播中删除免责'),prompt.find('附加交付约定'))
 def test_health_audience_and_attribution_rules_are_domain_scoped(self):
  health,_=prompt_extension(resolve_domain('关注血糖变化。','health'))
  mixed,_=prompt_extension(resolve_domain('谈《黄帝内经》与血压。','mixed'))
  guoxue,_=prompt_extension(resolve_domain('读《道德经》谈处世。','guoxue'))
  for prompt in (health,mixed):
   self.assertIn('50岁以上',prompt)
   self.assertIn('银发女性',prompt)
   self.assertIn('只有涉及诊断、用药、治疗',prompt)
  self.assertNotIn('银发女性',guoxue)
 def test_health_rules_follow_shared_contract_and_keep_literary_narrative(self):
  prompt,profile=prompt_extension(resolve_domain('《局外人》写孤独和选择。','health'))
  self.assertEqual('1.6.2',profile['version'])
  self.assertIn('故事冲突、生活场景、对话、意象',prompt)
  self.assertIn('把阅读价值讲透',prompt)
  self.assertIn('逐句降调',prompt)
  self.assertIn('至少组合三种方法',prompt)
  self.assertIn('不要求逐项举证',prompt)
  self.assertIn('retention_beats',prompt)
  self.assertIn('每450—550字',prompt)
  self.assertGreater(prompt.rfind('逐句降调'),prompt.find('附加交付约定'))
 def test_fact_and_output_anchors(self):
  obj={'information_card':[{'id':'F01','source_quote':'孩子更换工作','summary':'换工作'}],
       'rewrite_outline':[{'purpose':'先说担忧','fact_ids':['F01'],'target_quote':'工作要换的时候'}]}
  report=audit_output('孩子更换工作，家人担忧。','工作要换的时候，收入安排要解释。',obj)
  self.assertFalse(report['issues']);self.assertEqual(report['external_originality_status'],'未实测')
  obj['information_card'][0]['source_quote']='不存在的事件'
  self.assertTrue(audit_output('孩子更换工作。','工作要换的时候。',obj)['issues'])
 def test_retention_beats_are_grounded_and_distributed(self):
  blocks=['甲乙丙丁戊己庚辛壬癸'*35,'春夏秋冬东西南北山川'*35,'琴棋书画梅兰竹菊松柏'*35]
  anchors=['先看第一处转折','再看中间的反差','最后留下一个问题']
  text=blocks[0]+anchors[0]+blocks[1]+anchors[1]+blocks[2]+anchors[2]
  source='家人开始重新安排生活。'+text
  obj={'information_card':[{'id':'F01','source_quote':'家人开始重新安排生活','summary':'家庭生活变化'}],
       'rewrite_outline':[{'purpose':'说明生活变化','fact_ids':['F01'],'target_quote':'先看第一处转折'}],
       'retention_beats':[
        {'target_quote':anchors[0],'function':'悬念发起','next_pull':'接下来会看到这个选择带来的意外变化'},
        {'target_quote':anchors[1],'function':'反差揭示','next_pull':'下一段会解释反差为什么会发生'},
        {'target_quote':anchors[2],'function':'价值预告','next_pull':'后文会给出可以带走的具体启发'}]}
  report=audit_output(source,text,obj,require_retention=True)
  self.assertFalse(report['issues'],report['issues'])
  self.assertEqual(3,len(report['retention_beats']))
 def test_retention_beats_reject_shortage_and_clustering(self):
  text=('甲乙丙丁戊己庚辛壬癸'*110)+'结尾提示'
  obj={'information_card':[{'id':'F01','source_quote':'甲乙丙丁戊己','summary':'虚构信息'}],
       'rewrite_outline':[{'purpose':'说明信息','fact_ids':['F01'],'target_quote':'甲乙丙丁戊己'}],
       'retention_beats':[{'target_quote':'结尾提示','function':'价值预告','next_pull':'继续听会得到结论'}]}
  issues=audit_output(text,text,obj,require_retention=True)['issues']
  self.assertTrue(any('留存抓手不足' in issue for issue in issues))
  clustered='第一处抓手第二处抓手第三处抓手'+text
  obj['rewrite_outline'][0]['target_quote']='第一处抓手'
  obj['retention_beats']=[
   {'target_quote':'第一处抓手','function':'悬念发起','next_pull':'继续听第一个变化'},
   {'target_quote':'第二处抓手','function':'反差揭示','next_pull':'继续听第二个变化'},
   {'target_quote':'第三处抓手','function':'价值预告','next_pull':'继续听最后的答案'}]
  clustered_issues=audit_output(clustered,clustered,obj,require_retention=True)['issues']
  self.assertTrue(any('分布不均' in issue for issue in clustered_issues))
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
