"""Text-constrained subtitle alignment for an unchanged external recording."""
from __future__ import annotations

import difflib
import math
import re

from narration import normalize_tts_numbers, split_semantic_units, strip_subtitle_punctuation


def comparable(text: str) -> str:
    return ''.join(c.lower() for c in normalize_tts_numbers(text) if c.isalnum())


def differences(expected: str, recognized: str) -> list[dict]:
    left, right = comparable(expected), comparable(recognized)
    result = []
    for kind, a, b, c, d in difflib.SequenceMatcher(None, left, right, autojunk=False).get_opcodes():
        if kind != 'equal':
            result.append({'kind': kind, 'expected': left[a:b], 'recognized': right[c:d], 'offset': a})
    return result


def align(text: str, words: list[dict], duration: float) -> tuple[list[dict], float]:
    units = split_semantic_units(text, max_chars=14)
    normalized = [comparable(unit['text']) for unit in units]
    source = ''.join(normalized)
    transcript = ''
    times: list[tuple[float, float]] = []
    for word in words:
        token = comparable(str(word.get('word') or ''))
        if not token:
            continue
        start, end = float(word['start']), float(word['end'])
        if not math.isfinite(start + end) or start < 0 or end < start or end > duration + .1:
            raise ValueError('识别返回无效时间戳')
        step = (end - start) / len(token)
        transcript += token
        times.extend((start + step * i, start + step * (i + 1)) for i in range(len(token)))
    matched: dict[int, int] = {}
    for block in difflib.SequenceMatcher(None, source, transcript, autojunk=False).get_matching_blocks():
        matched.update({block.a+i: block.b+i for i in range(block.size)})
    cues = []
    offset = 0
    for unit, token in zip(units, normalized):
        indices = [matched[i] for i in range(offset, offset + len(token)) if i in matched]
        ready = bool(indices) and offset in matched and offset + len(token)-1 in matched
        # Missing text stays visibly unresolved; do not manufacture timestamps.
        start = round(times[indices[0]][0], 3) if indices else None
        end = round(min(duration, times[indices[-1]][1]), 3) if indices else None
        cues.append({**unit, 'start': start, 'end': end,
                     'needs_timing_review': not ready or end is None or start is None or end <= start,
                     'matched_ratio': round(len(indices)/max(1,len(token)), 3)})
        offset += len(token)
    return cues, round(len(matched)/max(1,len(source)), 4)


def validate_cues(text: str, cues: list[dict], duration: float) -> list[dict]:
    if not cues or len(cues) > 10000:
        raise ValueError('字幕不能为空或超过上限')
    if ''.join(str(c.get('text') or '') for c in cues) != strip_subtitle_punctuation(text).replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', ''):
        raise ValueError('字幕文字与当前字幕稿不一致，请重新对齐')
    result = []
    previous = 0.0
    char_cursor = 0
    compact = re.sub(r'\s+', '', text)
    for cue in cues:
        caption = str(cue.get('text') or '')
        start, end = float(cue['start']), float(cue['end'])
        if not caption or len(caption)>14 or not math.isfinite(start+end) or start<previous or end<=start or end>duration+.001:
            raise ValueError('字幕时间须递增、不重叠、不超过音频末尾，每条最多14字')
        # Preserve original punctuation offsets for the existing image timeline.
        while char_cursor<len(compact) and not strip_subtitle_punctuation(compact[char_cursor]):
            char_cursor+=1
        begin=char_cursor
        count=0
        while char_cursor<len(compact) and count<len(caption):
            if strip_subtitle_punctuation(compact[char_cursor]): count+=1
            char_cursor+=1
        result.append({**cue,'start':round(start,3),'end':round(end,3),
                       'char_start':begin,'char_end':char_cursor,'needs_timing_review':False})
        previous=end
    return result
