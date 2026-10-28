"""Production metadata checks and bounded paragraph repair, without external calls."""
from __future__ import annotations

import re
from rewrite_review import normalized, remainder


def scene_plan_audit(source: str, text: str, obj: dict) -> dict:
    plan = obj.get('scene_plan')
    issues = []
    if not isinstance(plan, dict):
        return {'issues': ['缺少 scene_plan：请比较两个提纲并绑定地点与事实'], 'plan': {}}
    if plan.get('content_shape') not in {'city', 'attraction', 'campus', 'roundup', 'heritage'}:
        issues.append('scene_plan 内容形态无效')
    alternatives = plan.get('alternatives')
    valid = isinstance(alternatives, list) and len(alternatives) == 2 and all(
        isinstance(item, dict) and isinstance(item.get('id'), str) and item['id']
        and isinstance(item.get('structure'), str) and item['structure'].strip()
        and isinstance(item.get('outline'), list) and 2 <= len(item['outline']) <= 8
        and all(isinstance(p, str) and p.strip() for p in item['outline'])
        and isinstance(item.get('reason'), str) and item['reason'].strip() for item in alternatives)
    if not valid:
        issues.append('scene_plan 必须提供两个完整简短提纲')
    else:
        ids = [item['id'] for item in alternatives]
        if (len(set(ids)) != 2 or plan.get('selected') not in ids
                or not isinstance(plan.get('selection_reason'), str) or not plan['selection_reason'].strip()):
            issues.append('scene_plan 需选择唯一有效提纲并说明理由')
        if alternatives[0]['outline'] == alternatives[1]['outline']:
            issues.append('两个提纲不能仅改名称而沿用相同组织')
    if plan.get('ranking_type') not in {'objective', 'subjective', 'unordered', 'none'}:
        issues.append('scene_plan 缺少排名性质')
    cards = obj.get('information_card') or []
    facts = {item.get('id'): item for item in cards if isinstance(item, dict)
             and isinstance(item.get('id'), str)}
    units = plan.get('units')
    if not isinstance(units, list) or not 1 <= len(units) <= 40:
        issues.append('scene_plan 需提供地点记忆点与事实绑定')
        units = []
    for unit in units:
        if not isinstance(unit, dict):
            issues.append('地点单元格式无效'); continue
        entity = str(unit.get('entity') or '').strip()
        refs = unit.get('fact_ids')
        anchor = normalized(str(unit.get('target_quote') or ''))
        if not entity or normalized(entity) not in normalized(source):
            issues.append('地点名称必须来自原稿，不可新增或错配校区')
        if any(not isinstance(unit.get(key), str) or not unit[key].strip()
               for key in ('entity', 'memory_point', 'entry_angle', 'target_quote')):
            issues.append('地点单元缺少记忆点或切入角度')
        if not isinstance(refs, list) or not refs or any(not isinstance(key, str) or key not in facts for key in refs):
            issues.append('地点单元必须关联有效信息卡')
        elif normalized(entity) not in normalized(''.join(str(facts[key].get('source_quote') or '') for key in refs)):
            issues.append('地点单元的信息卡依据未明确包含对应地点，请补全原稿引用')
        if len(anchor) < 4 or anchor not in normalized(text):
            issues.append('地点单元的成稿锚点不在实际正文中')
    risks = plan.get('hook_risks') or []
    if not isinstance(risks, list) or any(not isinstance(risk, dict) or
            any(not isinstance(risk.get(key), str) for key in ('quote', 'reason', 'suggestion')) for risk in risks):
        issues.append('钩子风险记录格式无效')
    elif any(normalized(risk['quote']) not in normalized(source) or not normalized(risk['quote']) for risk in risks):
        issues.append('钩子风险引用不在原稿中')
    return {'issues': list(dict.fromkeys(issues)), 'plan': plan if not issues else {},
            'notice': '已检查字段、原稿地点、信息卡引用与正文锚点；不代表独立事实核验或叙事质量评分。'}


def health_attribution_issues(text: str, hook: str) -> list[str]:
    body = remainder(text, hook)
    issues = []
    if re.search(r'原稿(?:中|里)?(?:说|提到|指出|认为)|参考文案|改写后的?文案', body):
        issues.append('口播含制作过程用语，请删除“原稿/参考文案”等归属')
    repeated = re.findall(r'(?:^|[。！？!?\n])\s*(?:而|另外|同时|接着)?(?:书中(?:说到|提到|说|指出)|这本书(?:说|告诉我们|提到))', body)
    if len(repeated) > 1:
        issues.append('多处以书籍报幕式起句，请开头统一交代来源，正文自然展开并保留必要医学归属')
    return issues


def repair_scope(previous: dict, hook: str) -> tuple[list[str], list[int]]:
    """Only local lexical issues qualify; global length/fact/structure needs a full draft."""
    paragraphs = [p for p in remainder(previous.get('text', ''), hook).split('\n\n') if p.strip()]
    issues = previous.get('issues') or []
    local_prefixes = ('可改写部分重复指标', '全文重复指标', '口播含制作过程', '多处以书籍报幕')
    if not paragraphs or not issues or any(not str(issue).startswith(local_prefixes) for issue in issues):
        return paragraphs, []
    fragments = previous.get('similarity', {}).get('unlocked', {}).get('repeated_fragments', [])
    editable = [i for i, paragraph in enumerate(paragraphs) if
                any(normalized(fragment) in normalized(paragraph) for fragment in fragments if fragment)
                or health_attribution_issues(paragraph, '')]
    # Include sentence-start source formulas spread across separate paragraphs.
    if any(str(issue).startswith('多处以书籍报幕') for issue in issues):
        editable += [i for i, paragraph in enumerate(paragraphs) if re.search(r'书中(?:说|提到|指出)|这本书(?:说|告诉我们|提到)', paragraph)]
    chosen = sorted(set(editable))
    return paragraphs, chosen if 0 < len(chosen) < len(paragraphs) else []


def apply_paragraph_edits(paragraphs: list[str], edits: object, editable: list[int]) -> str:
    if not isinstance(edits, list) or not edits:
        raise ValueError('局部返工须返回 paragraph_edits')
    result = list(paragraphs); seen = set()
    for edit in edits:
        if not isinstance(edit, dict): raise ValueError('局部修改格式无效')
        index = edit.get('index'); text = edit.get('text')
        if type(index) is not int or index not in editable or index in seen or not isinstance(text, str) or not text.strip():
            raise ValueError('局部修改越过允许段落或正文为空')
        seen.add(index); result[index] = text.strip()
    return '\n\n'.join(result)
