"""Domain routing and auditable metadata for the project rewriting skill."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from rewrite_review import normalized

ROOT = Path(__file__).resolve().parent.parent / 'skills' / 'book-video-rewrite'
VERSION = '1.2.1'
DOMAINS = {'guoxue', 'health', 'mixed', 'general', 'scene'}
LABELS = {'guoxue':'国学','health':'健康','mixed':'国学与健康混合','general':'通用','scene':'山河人文'}
CLASSICS = ('道德经','论语','庄子','孟子','大学','中庸','易经','黄帝内经')
MEDICAL = ('血压','血糖','糖尿病','胆固醇','心血管','临床','药物','服药','治疗','疾病','营养','饮食','睡眠','运动')

class DomainConflict(ValueError):
    pass


def resolve_domain(source: str, explicit='auto', templates=(), category='health'):
    explicit = str(explicit or 'auto')
    if category == 'scene' and explicit not in {'auto','scene'}:
        raise DomainConflict('山河人文生产线请使用山河人文二创规则')
    if category == 'scene' and explicit == 'auto':
        explicit = 'scene'
    if explicit == 'scene' and category != 'scene':
        raise DomainConflict('山河人文规则仅用于山河人文生产线')
    if explicit not in DOMAINS | {'auto'}:
        raise DomainConflict('二创领域无效，请重新选择国学、健康、混合或通用。')
    classic_hits = [word for word in CLASSICS if word in source and (word != '大学' or '《大学》' in source)]
    medical_hits = [word for word in MEDICAL if word in source]
    health = any(word in source for word in MEDICAL[:10]) or len(medical_hits) >= 2
    guoxue = bool(classic_hits)
    evidence = {'classic_signals':classic_hits, 'health_signals':medical_hits, 'legacy_category':category,
                'templates':sorted(set(templates))}
    if explicit != 'auto':
        if explicit == 'general' and health:
            raise DomainConflict('正文包含健康主张，请选择“健康”或“混合”；通用领域不能跳过健康规则。')
        if explicit == 'guoxue' and health:
            raise DomainConflict('正文包含健康主张（'+ '、'.join(medical_hits[:4]) +'），请选“混合”或“健康”后重跑；不会静默套用纯国学规则。')
        if explicit == 'health' and guoxue:
            raise DomainConflict('正文包含经典主题，请选择“混合”以同时检查国学与健康规则；不会仅套用健康规则。')
        domain, reason = explicit, '用户明确选择'
    elif guoxue and health:
        domain, reason = 'mixed', '正文同时包含经典与健康信号'
    elif health:
        if 'guoxue-v1' in templates and not guoxue:
            raise DomainConflict('国学模板与正文健康主题冲突，请在二创领域选择“健康”或“混合”后重跑。')
        domain, reason = 'health', '正文健康主题'
    elif guoxue:
        if 'health-v1' in templates:
            raise DomainConflict('健康模板与正文经典主题冲突，请在二创领域确认“国学”“混合”或“通用”后重跑。')
        domain, reason = 'guoxue', '正文经典主题'
    elif 'guoxue-v1' in templates:
        domain, reason = 'guoxue', '所选国学模板推定，未检测到相反的健康主张；请在审稿时核对'
    elif 'health-v1' in templates:
        domain, reason = 'health', '所选健康模板推定，未检测到相反的经典主题；请在审稿时核对'
    else:
        domain, reason = 'general', '正文领域不明确，旧分类不足以决定领域，先使用通用框架'
    return {'domain':domain,'label':LABELS[domain],'reason':reason,'evidence':evidence,'version':VERSION}


def prompt_extension(profile):
    if profile['domain'] == 'scene':
        root = ROOT.parent / 'scene-video-pipeline'
        rules = (root / 'references' / 'rewrite.md').read_text(encoding='utf-8')
        contract = (Path(__file__).parent/'prompts'/'rewrite_skill_contract.txt').read_text(encoding='utf-8').strip()
        text = rules + '\n\n' + contract
        return text, {**profile, 'version':'scene-1.0', 'rule_files':['scene-video-pipeline/references/rewrite.md'], 'rules_sha256':hashlib.sha256(text.encode()).hexdigest()}
    references = ['guoxue.md','health.md'] if profile['domain']=='mixed' else (
        [profile['domain']+'.md'] if profile['domain'] in ('guoxue','health') else [])
    pieces = [(ROOT/'SKILL.md').read_text(encoding='utf-8')]
    rules = []
    for name in references:
        value = (ROOT/'references'/name).read_text(encoding='utf-8').strip()
        pieces.append(value);rules.append(value)
    contract = (Path(__file__).parent/'prompts'/'rewrite_skill_contract.txt').read_text(encoding='utf-8').strip()
    pieces.append(contract)
    digest = hashlib.sha256('\n'.join(pieces).encode()).hexdigest()
    profile = {**profile, 'rule_files':references, 'rules_sha256':digest}
    return '\n\n'.join([f"本次二创领域：{profile['label']}。依据：{profile['reason']}。",*rules,contract]), profile


def audit_output(source, text, obj):
    """Validate evidence/anchors. This is not independent semantic fact verification."""
    issues=[];facts=[];outline=[];source_norm=normalized(source);text_norm=normalized(text)
    raw_facts = obj.get('information_card', []) if isinstance(obj,dict) else []
    raw_outline = obj.get('rewrite_outline', []) if isinstance(obj,dict) else []
    if not isinstance(raw_facts,list) or not raw_facts:
        issues.append('缺少信息卡 information_card，请补充带原文依据的事实条目')
        raw_facts=[]
    if not isinstance(raw_outline,list) or not raw_outline:
        issues.append('缺少 rewrite_outline，请标记提纲功能、使用的信息卡及成稿锚点')
        raw_outline=[]
    if len(raw_facts)>24 or len(raw_outline)>16: issues.append('信息卡最多24项、提纲最多16项，请合并相近条目')
    ids=set();positions={}
    for item in raw_facts[:24]:
        if not isinstance(item,dict):issues.append('信息卡条目格式无效');continue
        key=str(item.get('id',''));quote=str(item.get('source_quote','')).strip();summary=str(item.get('summary','')).strip()
        if not re.fullmatch(r'F\d{1,2}',key) or key in ids or not quote or not summary or len(quote)>160 or len(summary)>200:
            issues.append('信息卡编号、原文依据或摘要无效');continue
        if not normalized(quote) or normalized(quote) not in source_norm:
            issues.append('信息卡'+key+'的依据不在原稿中');continue
        ids.add(key);positions[key]=source_norm.index(normalized(quote))
        facts.append({'id':key,'source_quote':quote,'summary':summary})
    used=set();observed_order=[]
    for item in raw_outline[:16]:
        if not isinstance(item,dict):issues.append('提纲条目格式无效');continue
        refs=item.get('fact_ids',[]);anchor=str(item.get('target_quote','')).strip();purpose=str(item.get('purpose','')).strip()
        if not isinstance(refs,list) or not refs or any(not isinstance(key,str) or key not in ids for key in refs) or not purpose or not anchor or len(anchor)>100 or len(purpose)>200:
            issues.append('提纲必须引用有效信息卡并给出简短功能及成稿锚点');continue
        if len(normalized(anchor))<4 or normalized(anchor) not in text_norm:
            issues.append('提纲的成稿锚点不在实际正文中');continue
        used.update(refs);observed_order.extend(positions[key] for key in refs)
        outline.append({'purpose':purpose,'fact_ids':refs,'target_quote':anchor})
    if ids-used:issues.append('部分信息卡未关联到提纲：'+'、'.join(sorted(ids-used)))
    return {'information_card':facts,'rewrite_outline':outline,'issues':list(dict.fromkeys(issues)),
            'evidence_status':'source_quotes_and_output_anchors_checked',
            'fact_semantics_status':'需人工核对完整事实与含义；锚点对应不等于语义已独立核验',
            'source_order_changed':any(a>b for a,b in zip(observed_order,observed_order[1:])),
            'external_originality_status':'未实测'}
