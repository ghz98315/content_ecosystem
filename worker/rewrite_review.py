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
HEALTH_MIN_LENGTH_RATIO = 0.85
HEALTH_MAX_LENGTH_RATIO = 0.90
HEALTH_TARGET_LENGTH_RATIO = 0.88


def length_bounds(source: str, category: str | None = None) -> tuple[int, int]:
    size = effective_length(source)
    if category == 'health':
        return math.ceil(size * HEALTH_MIN_LENGTH_RATIO), math.floor(size * HEALTH_MAX_LENGTH_RATIO)
    return math.ceil(size * MIN_LENGTH_RATIO), math.floor(size * MAX_LENGTH_RATIO)


def attempt_rank(attempt: dict) -> tuple:
    """Prefer usable length and fewer issues before lower phrase reuse."""
    report = attempt['similarity']
    incomplete = not attempt.get('complete', True) or any(
        '长度上限' in issue or '被截断' in issue or '结尾不完整' in issue
        for issue in attempt.get('issues', []))
    too_short = report['candidate_chars'] < report['min_chars']
    too_long = report['candidate_chars'] > report['max_chars']
    return (incomplete, too_short or too_long,
            len(attempt.get('issues', [])), report['unlocked']['score'],
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


def opening_hook(source: str) -> str:
    """Freeze three complete opening sentences, or one on very short scripts."""
    spans = list(re.finditer(r'[^。！？!?；;]+[。！？!?；;]+|[^。！？!?；;]+$', source))
    if not spans:
        return source.strip()
    count = 3 if len(spans) > 3 else 1
    return source[:spans[min(count, len(spans)) - 1].end()].strip()


def remainder(text: str, hook: str) -> str:
    # Exact prefix removal prevents subtracting a matching quote in the body.
    return text.lstrip()[len(hook):].strip() if text.lstrip().startswith(hook) else text.strip()


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


def evaluate(source: str, text: str, hook: str | None = None, category: str | None = None) -> dict:
    hook = opening_hook(source) if hook is None else hook
    original_body = remainder(source, hook)
    new_body = remainder(text, hook)
    full, unlocked = _measure(source, text), _measure(original_body, new_body)
    hook_kept = text.lstrip().startswith(hook)
    locked_floor = sum(_grams(normalized(hook)).values()) / max(1, sum(_grams(normalized(source)).values()))
    issues = []
    if not hook_kept:
        issues.append('开头钩子未逐字保留')
    if not normalized(new_body):
        issues.append('钩子以外没有完整正文')
    if unlocked['score'] >= TARGET:
        issues.append(f"可改写部分重复指标 {unlocked['score']:.1%}，需低于 {TARGET:.0%}")
    # A frozen opening can alone exceed the whole-script threshold.
    if full['score'] >= TARGET and locked_floor < TARGET:
        issues.append(f"全文重复指标 {full['score']:.1%}，需低于 {TARGET:.0%}")
    ratio = effective_length(text) / max(1, effective_length(source))
    minimum, maximum = length_bounds(source, category)
    if not minimum <= effective_length(text) <= maximum:
        label = '85%-90%' if category == 'health' else '85%-110%'
        issues.append(f'有效字数偏差 {(ratio - 1):+.1%}，应在原稿{label}范围（{minimum}-{maximum}字）')
    if not hook_kept or not original_body:
        # Missing rewrite space is actionable manually, never labelled a pass.
        if not original_body:
            issues.append('原文缺少可改写正文，请人工划分钩子范围')
    return {
        'method': 'phrase_reuse_v1', 'threshold': TARGET,
        'full': full, 'unlocked': unlocked,
        'hook_preserved': hook_kept, 'locked_floor': locked_floor,
        'source_chars': effective_length(source), 'candidate_chars': effective_length(text),
        'length_deviation': ratio - 1, 'retry_issues': issues,
        'min_chars': minimum, 'max_chars': maximum,
        'status': 'passed' if not issues and full['score'] < TARGET else 'manual_review',
        'notice': '与本次来源稿进行本地字面比较：5字片段重合与整句复用取较高值；字符序列相似度仅供参考。未检索全网文库，不是文皮皮分数，也不判断事实真实性。',
    }
