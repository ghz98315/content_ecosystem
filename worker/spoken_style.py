"""Check production or audit language in editable narration."""
import re

PATTERN = re.compile(
    r'原稿|参考文案|改写后(?:的)?文案|作者转述|依据原稿保留|未独立核验|医学事实|因果证据'
    r'|(?:出处|来源|归属|作者身份|原文版本)(?:\s|[，、：])*'
    r'(?:尚不详|尚不明|不详|不明|'
    r'(?:(?:尚|仍)?(?:有待|待|未(?:能)?|需(?:要)?)|无法|难以)'
    r'(?:进一步|独立)?(?:核实|核验|查证|考证|确认|证实|确定))'
)

HISTORY_DISCLAIMER_PATTERN = re.compile(
    r'不能反过来说|不能简单(?:概括|说|认为|理解|归因|断定)|不能只凭(?:这一点|这些)|'
    r'这里不能简单说|更不能(?:因此|因为|靠|把)|并不等于|这不等于|不是说[^。！？]{0,50}(?:而是|只是|就)'
)
HISTORY_TRANSITION_START = re.compile(r'^\s*(?:但|不过|因此|所以|与此同时|尤其|与其)')
HEALTH_REVIEW_PATTERN = re.compile(
    r'具体出处(?:尚|仍)?(?:有待|待)(?:核实|查证|考证)|'
    r'不能简单(?:断定|认为|理解|归因)|不能据此(?:断定|认为|推断)|'
    r'这(?:并)?不代表(?:所有人|每个人)|(?:尚无|缺乏)因果证据'
)
HEALTH_DEFENSIVE_PATTERN = re.compile(
    r'未必|不必|并不等于|这不等于|不意味着|不一定|不能保证|并非[^。！？]{0,35}而是'
)
MEDICAL_RISK_PATTERN = re.compile(r'诊断|用药|药物|治疗|疗效|治愈|疾病|临床|检查结果|替代(?:就医|治疗)')


def spoken_style_issues(text: str, hook: str = '', tail: str = '') -> list[str]:
    body = text.strip()
    if hook:
        body = body.removeprefix(hook)
    if tail:
        body = body.rstrip().removesuffix(tail)
    found = list(dict.fromkeys(PATTERN.findall(body)))
    return ['口播含制作或审稿用语：' + '、'.join(found) + '；仅改写正文，保留必要事实边界'] if found else []


def history_style_issues(text: str, hook: str = '') -> list[str]:
    """Catch review-language patterns that make history narration sound defensive."""
    body = text.strip().removeprefix(hook).strip() if hook else text.strip()
    issues = []
    disclaimers = list(dict.fromkeys(HISTORY_DISCLAIMER_PATTERN.findall(body)))
    if disclaimers:
        issues.append('历史哲科口播仍含免责或自我辩护句式，请把疑点移到审核信息并直接讲故事：'
                      + '、'.join(disclaimers[:5]))
    paragraphs = [part.strip() for part in body.split('\n\n') if part.strip()]
    transition_starts = sum(bool(HISTORY_TRANSITION_START.search(part)) for part in paragraphs)
    if transition_starts >= 3 and transition_starts * 3 >= max(1, len(paragraphs)):
        issues.append('历史哲科多段以转折词开头，请改用人物动作、生活场景或上一段结果自然承接')
    if len(re.findall(r'不是[^。！？]{0,45}而是', body)) >= 3:
        issues.append('历史哲科反复使用“不是……而是……”，请改成自然口语并保留原有意思')
    return issues


def health_conversational_issues(text: str, hook: str = '', source: str = '') -> list[str]:
    """Keep growth narration warm without deleting required medical boundaries."""
    body = text.strip().removeprefix(hook).strip() if hook else text.strip()
    issues = []
    review_terms = list(dict.fromkeys(HEALTH_REVIEW_PATTERN.findall(body)))
    if review_terms:
        issues.append('女性成长与健康口播仍含考证或免责腔，请把疑点移到审核信息：'
                      + '、'.join(review_terms[:5]))
    # Medical drafts can legitimately need concise safety qualifiers. Literary,
    # relationship and growth drafts should not hedge nearly every paragraph.
    if not MEDICAL_RISK_PATTERN.search(source):
        defensive = HEALTH_DEFENSIVE_PATTERN.findall(body)
        paragraphs = [part for part in body.split('\n\n') if part.strip()]
        if len(defensive) >= 6 and len(defensive) * 2 >= max(1, len(paragraphs)):
            issues.append('女性成长口播防御性限定过密，请保留故事、对话和意象，减少“未必/不必/不等于”等逐句降调')
    return issues
