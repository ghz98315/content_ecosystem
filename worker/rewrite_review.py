"""Local phrase-reuse checks; scores are not a third-party originality rating."""
from __future__ import annotations

import re
import math
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

TARGET = 0.10
MAX_REVISIONS = 3
MIN_LENGTH_RATIO = 0.85
MAX_LENGTH_RATIO = 1.10
PLANNED_MIN_LENGTH_RATIO = 0.95
PLANNED_TARGET_LENGTH_RATIO = 0.97
HEALTH_MIN_LENGTH_RATIO = 1.00
HEALTH_MAX_LENGTH_RATIO = 1.10
# Plan slightly above the original to offset long-form model undershoot.
HEALTH_TARGET_LENGTH_RATIO = 1.08
HISTORY_MIN_LENGTH_RATIO = 0.90


def length_bounds(source: str, category: str | None = None) -> tuple[int, int]:
    size = effective_length(source)
    if category == 'health':
        return math.ceil(size * HEALTH_MIN_LENGTH_RATIO), math.floor(size * HEALTH_MAX_LENGTH_RATIO)
    if category == 'scene':
        return math.ceil(size * .90), math.floor(size * MAX_LENGTH_RATIO)
    if category == 'social_science':
        return math.ceil(size * HISTORY_MIN_LENGTH_RATIO), math.floor(size * MAX_LENGTH_RATIO)
    return math.ceil(size * MIN_LENGTH_RATIO), math.floor(size * MAX_LENGTH_RATIO)


def length_plan(source: str, category: str | None = None) -> tuple[int, int, int, int]:
    """Return execution bounds, automatic minimum, and drafting target."""
    size = effective_length(source)
    minimum, maximum = length_bounds(source, category)
    planned_minimum = minimum if category in {'health', 'social_science'} else math.ceil(size * PLANNED_MIN_LENGTH_RATIO)
    target_ratio = HEALTH_TARGET_LENGTH_RATIO if category == 'health' else PLANNED_TARGET_LENGTH_RATIO
    return minimum, maximum, planned_minimum, min(maximum, math.ceil(size * target_ratio))


def attempt_rank(attempt: dict) -> tuple:
    """Prefer usable length and fewer issues before lower phrase reuse."""
    report = attempt['similarity']
    incomplete = not attempt.get('complete', True) or any(
        '长度上限' in issue or '被截断' in issue or '结尾不完整' in issue
        for issue in attempt.get('issues', []))
    too_short = report['candidate_chars'] < report['min_chars']
    too_long = report['candidate_chars'] > report['max_chars']
    length_distance = max(report['min_chars'] - report['candidate_chars'],
                          report['candidate_chars'] - report['max_chars'], 0)
    below_plan = report['candidate_chars'] < report.get('planned_min_chars', report['min_chars'])
    return (incomplete, too_short or too_long, length_distance,
            below_plan, len(attempt.get('issues', [])), report['unlocked']['score'],
            report['full']['score'], -attempt['attempt'])


def normalized(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKC', text or '') if c.isalnum())


def effective_length(text: str) -> int:
    return len(normalized(text))


def format_for_reading(text: str) -> str:
    """Only add paragraph whitespace; never substitute source characters."""
    paragraphs = []
    pending = ''
    merged = re.sub(r'\r?\n\s*', '', text.strip())
    for match in re.finditer(r'[^。！？!?]+[。！？!?]+[”’」』）)]*|[^。！？!?]+$', merged):
        sentence = match.group()
        if pending and effective_length(pending + sentence) > 180:
            paragraphs.append(pending.strip())
            pending = ''
        pending += sentence
        if effective_length(pending) >= 100:
            paragraphs.append(pending.strip())
            pending = ''
    if pending.strip():
        paragraphs.append(pending.strip())
    return '\n\n'.join(paragraphs)


_SENTENCE_END = re.compile(r"(?:[。！？!?]+|\.(?![\w.]))[”’」』）】》\"']*")
_CONVERSION_CUE = re.compile(
    r'橱窗|购物车|小黄车|下方链接|左下角|评论区(?:留言|告诉|聊聊)|(?:欢迎|记得|别忘了)(?:点赞|评论|关注|收藏)'
    r'|(?:推荐|建议|不妨|可以|值得)(?:您|你|大家)?(?:去|也|先)?(?:买|入手|带回家|读一读|读这本|翻一翻|翻翻|看看这本)'
    r'|(?:把|将)这本书带回家|这本书值得(?:读|翻|收藏)|(?:想|喜欢)(?:看这本书|了解这本书|深入读这本书)'
)
_CONVERSION_LEAD = re.compile(r'(?:最后|说到最后|这里|今天)?(?:我|想|给您|给大家|再)?(?:也|想)?(?:推荐|介绍)(?:一本|这本|一部|《)|^如果(?:您|你|大家).{0,25}(?:这本书|这套书)')


def history_conversion_tail(source: str) -> str:
    """Select a verbatim closing recommendation/action suffix from the source."""
    starts = [0] + [match.end() for match in _SENTENCE_END.finditer(source)]
    starts.append(len(source))
    sentences = [(start, source[start:end].strip()) for start, end in zip(starts, starts[1:]) if source[start:end].strip()]
    for offset, sentence in sentences[1:]:
        if offset >= len(source) * .55 and (_CONVERSION_CUE.search(sentence) or _CONVERSION_LEAD.search(sentence)):
            return source[offset:].strip()
    return ''


def opening_hook(source: str, category: str | None = None) -> str:
    """Select an exact source prefix using the production line's hook policy."""
    if category == 'social_science':
        tail = history_conversion_tail(source)
        if tail:
            source = source.rstrip().removesuffix(tail).rstrip()
    if category in {'health', 'social_science'}:
        # Leave a writable remainder. Semicolons and decimal points do not
        # end a sentence, and closing quotes belong to the locked prefix.
        boundaries = _SENTENCE_END.finditer(source)
        ends = []
        start = 0
        for boundary in boundaries:
            end = boundary.end()
            if normalized(source[start:end]):
                ends.append(end)
                start = end
            if len(ends) == 4:
                break
        while ends and not normalized(source[ends[-1]:]):
            ends.pop()
        return source[:ends[-1]].strip() if ends else ''
    spans = list(re.finditer(r'[^。！？!?；;]+[。！？!?；;]+|[^。！？!?；;]+$', source))
    if not spans:
        return source.strip()
    count = 3 if len(spans) > 3 else 1
    return source[:spans[min(count, len(spans)) - 1].end()].strip()


def remainder(text: str, hook: str) -> str:
    # Exact prefix removal prevents subtracting a matching quote in the body.
    return text.lstrip()[len(hook):].strip() if text.lstrip().startswith(hook) else text.strip()


def editable_middle(text: str, hook: str, tail: str = '') -> str:
    return remainder(text, hook).removesuffix(tail).strip()


def _grams(text: str, size: int = 5) -> Counter:
    if not text:
        return Counter()
    if len(text) < size:
        return Counter({text: 1})
    return Counter(text[i:i + size] for i in range(len(text) - size + 1))


def _measure(source: str, candidate: str) -> dict:
    left, right = normalized(source), normalized(candidate)
    a, b = _grams(left), _grams(right)
    overlap = sum((a & b).values())
    phrase = max(overlap / max(1, sum(a.values())), overlap / max(1, sum(b.values())))
    sentences = [normalized(s) for s in re.split(r'[。！？!?；;\n]+', source)]
    sentences = [s for s in sentences if len(s) >= 8]
    copied = [s for s in sentences if s in right]
    sentence = sum(len(s) for s in copied) / max(1, len(left))
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    blocks = sorted(matcher.get_matching_blocks(), key=lambda item: item.size, reverse=True)
    return {
        'score': max(phrase, sentence),
        'phrase_overlap': phrase,
        'sentence_reuse': min(1.0, sentence),
        'sequence_similarity': matcher.ratio(),
        'longest_match': max((item.size for item in blocks), default=0),
        'repeated_fragments': list(dict.fromkeys(left[item.a:item.a + min(item.size, 100)]
                                  for item in blocks if item.size >= 8))[:6],
    }


def evaluate(source: str, text: str, hook: str | None = None, category: str | None = None,
             *, target_reuse: bool = True, locked_tail: str = '') -> dict:
    hook = opening_hook(source, category) if hook is None else hook
    original_body = editable_middle(source, hook, locked_tail)
    new_body = editable_middle(text, hook, locked_tail)
    full, unlocked = _measure(source, text), _measure(original_body, new_body)
    hook_kept = text.lstrip().startswith(hook)
    tail_kept = bool(locked_tail and text.rstrip().endswith(locked_tail))
    locked_floor = (
        sum(sum(_grams(normalized(section)).values()) for section in (hook, locked_tail))
        / max(1, sum(_grams(normalized(source)).values()))
    )
    issues = []
    if not hook_kept:
        issues.append('开头钩子未逐字保留')
    if locked_tail and not tail_kept:
        issues.append('转化结尾未逐字保留')
    if not normalized(new_body):
        issues.append('钩子以外没有完整正文')
    if target_reuse and unlocked['score'] >= TARGET:
        issues.append(f"可改写部分重复指标 {unlocked['score']:.1%}，需低于 {TARGET:.0%}")
    # A frozen opening can alone exceed the whole-script threshold.
    if target_reuse and full['score'] >= TARGET and locked_floor < TARGET:
        issues.append(f"全文重复指标 {full['score']:.1%}，需低于 {TARGET:.0%}")
    source_chars, candidate_chars = effective_length(source), effective_length(text)
    ratio = candidate_chars / max(1, source_chars)
    minimum, maximum, planned_minimum, _ = length_plan(source, category)
    if not minimum <= candidate_chars <= maximum:
        label = '100%-110%' if category == 'health' else '90%-110%' if category in {'scene', 'social_science'} else '85%-110%'
        issues.append(f'有效字数偏差 {(ratio - 1):+.1%}，应在原稿{label}范围（{minimum}-{maximum}字）')
    if not hook_kept or not original_body:
        # Missing rewrite space is actionable manually, never labelled a pass.
        if not original_body:
            issues.append('原文缺少可改写正文，请人工划分钩子范围')
    return {
        'method': 'phrase_reuse_v1', 'threshold': TARGET,
        'reuse_target_applies': target_reuse,
        'full': full, 'unlocked': unlocked,
        'hook_preserved': hook_kept, 'locked_floor': locked_floor,
        'tail_locked': bool(locked_tail), 'tail_preserved': tail_kept,
        'source_chars': source_chars, 'candidate_chars': candidate_chars,
        'length_deviation': ratio - 1, 'retry_issues': issues,
        'min_chars': minimum, 'max_chars': maximum, 'planned_min_chars': planned_minimum,
        'status': 'passed' if not issues and (not target_reuse or full['score'] < TARGET) else 'manual_review',
        'notice': '与本次来源稿进行本地字面比较：5字片段重合与整句复用取较高值；字符序列相似度仅供参考。未检索全网文库，不是文皮皮分数，也不判断事实真实性。',
    }
