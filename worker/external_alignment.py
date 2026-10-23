"""Text-constrained subtitle alignment for an unchanged external recording."""
from __future__ import annotations

import difflib
import math
import re

from opencc import OpenCC

from narration import SUBTITLE_MAX_CHARS, normalize_tts_numbers, split_semantic_units, strip_subtitle_punctuation, visible_len

_SIMPLIFIED_CONVERTER = OpenCC('t2s')


def comparable(text: str) -> str:
    spoken = _SIMPLIFIED_CONVERTER.convert(normalize_tts_numbers(text))
    return ''.join(c.lower() for c in spoken if c.isalnum())


def _comparable_spans(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Track raw character spans through the existing speech-number cleanup."""
    spoken = normalize_tts_numbers(text)
    spans: list[tuple[int, int]] = [(0, 0)] * len(spoken)
    for kind, a, b, c, d in difflib.SequenceMatcher(None, text, spoken, autojunk=False).get_opcodes():
        for index in range(c, d):
            spans[index] = (a + index - c, a + index - c + 1) if kind == 'equal' else (a, b)
    simplified = _SIMPLIFIED_CONVERTER.convert(spoken)
    if len(simplified) == len(spoken):
        converted_spans = spans
    else:
        converted_spans = [(0, 0)] * len(simplified)
        for kind, a, b, c, d in difflib.SequenceMatcher(None, spoken, simplified, autojunk=False).get_opcodes():
            for index in range(c, d):
                if kind == 'equal':
                    converted_spans[index] = spans[a + index - c]
                elif a < b:
                    converted_spans[index] = (spans[a][0], spans[b - 1][1])
                else:
                    point = spans[a][0] if a < len(spans) else (spans[-1][1] if spans else 0)
                    converted_spans[index] = (point, point)
    indices = [index for index, char in enumerate(simplified) if char.isalnum()]
    return (''.join(simplified[i].lower() for i in indices),
            [converted_spans[i] for i in indices for _ in simplified[i].lower()])


def _raw_span(spans: list[tuple[int, int]], start: int, end: int, text: str) -> tuple[int, int] | None:
    if start == end:
        point = spans[start][0] if start < len(spans) else (spans[-1][1] if spans else 0)
        # Never insert halfway into a normalized numeric token.
        if 0 < start < len(spans) and spans[start - 1][1] > point:
            return None
        return point, point
    begin, finish = spans[start][0], spans[end - 1][1]
    if (start and spans[start - 1][1] > begin) or (end < len(spans) and spans[end][0] < finish):
        return None
    return begin, finish


def differences(expected: str, recognized: str, words: list[dict] | None = None) -> list[dict]:
    left, right = comparable(expected), comparable(recognized)
    mapped_left, left_spans = _comparable_spans(expected)
    mapped_right, right_spans = _comparable_spans(recognized)
    # Map recognized offsets to existing word timestamps; absent data stays absent.
    timed_chars: list[tuple[float, float]] = []
    timed_text = ''
    for word in words or []:
        token = comparable(str(word.get('word') or ''))
        timed_text += token
        timed_chars.extend([(float(word['start']), float(word['end']))] * len(token))
    timed_matches = {}
    if timed_chars:
        for block in difflib.SequenceMatcher(None, right, timed_text, autojunk=False).get_matching_blocks():
            timed_matches.update({block.a+i: block.b+i for i in range(block.size)})
    result = []
    for kind, a, b, c, d in difflib.SequenceMatcher(None, left, right, autojunk=False).get_opcodes():
        if kind != 'equal':
            item = {'kind': kind, 'expected': left[a:b], 'recognized': right[c:d], 'offset': a}
            raw_left = _raw_span(left_spans, a, b, expected) if mapped_left == left else None
            raw_right = _raw_span(right_spans, c, d, recognized) if mapped_right == right else None
            if raw_left is not None and raw_right is not None:
                begin, finish = raw_left
                rbegin, rfinish = raw_right
                # Python offsets are code points; the browser slices UTF-16 strings.
                item.update({'raw_start': len(expected[:begin].encode('utf-16-le')) // 2,
                             'raw_end': len(expected[:finish].encode('utf-16-le')) // 2,
                             'original': expected[begin:finish], 'suggestion': recognized[rbegin:rfinish],
                             'context_before': expected[max(0, begin-18):begin],
                             'context_after': expected[finish:finish+18]})
            positions = [timed_matches[i] for i in range(c, d) if i in timed_matches]
            if not positions:
                neighbor = timed_matches.get(c, timed_matches.get(c-1))
                positions = [neighbor] if neighbor is not None else []
            if positions:
                item['audio_start'] = max(0, timed_chars[min(positions)][0] - .5)
                item['audio_end'] = timed_chars[max(positions)][1] + .5
            item['review_hint'] = ('识别中未找到，可能漏读或漏识别；应用建议会删除字幕文字，请先试听'
                                   if kind == 'delete' else '识别结果可能有同音字、专名或数字错误，请试听后采用')
            result.append(item)
    return result


def align(text: str, words: list[dict], duration: float, *, repair: bool = False) -> tuple[list[dict], float]:
    units = split_semantic_units(text, max_chars=SUBTITLE_MAX_CHARS)
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
    matcher = difflib.SequenceMatcher(None, source, transcript, autojunk=False)
    matched: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        matched.update({block.a+i: block.b+i for i in range(block.size)})
    char_times = {i: times[j] for i, j in matched.items()}
    repaired: set[int] = set()
    if repair:
        coverage = len(matched) / max(1, max(len(source), len(transcript)))
        changes = [op for op in matcher.get_opcodes() if op[0] != 'equal']
        if coverage < .80 or any(max(b-a, d-c) > 24 for _,a,b,c,d in changes):
            raise ValueError('录音与字幕文案差异较大，不能作为普通识别误差自动纠正；请上传匹配的录音或字幕稿')
        for _, a, b, c, d in changes:
            if a == b:
                continue
            if c < d:
                left, right = times[c][0], times[d-1][1]
            else:
                left = times[c-1][1] if c else 0.0
                right = times[c][0] if c < len(times) else duration
                if right-left < .02:
                    # Share the immediate neighboring syllables rather than
                    # shifting all later captions after a short ASR omission.
                    left = times[c-1][0] if c else left
                    right = times[c][1] if c < len(times) else right
                    step = (right-left)/3
                    if a-1 in char_times:
                        char_times[a-1] = (char_times[a-1][0], left+step)
                    if b in char_times:
                        char_times[b] = (right-step, char_times[b][1])
                    left, right = left+step, right-step
                else:
                    # Keep long recorded pauses; do not stretch a missing
                    # character across the entire silence.
                    span = min(right-left, (b-a)*min(.3, duration/max(1,len(source))))
                    left = left + (right-left-span)/2
                    right = left + span
            if right <= left:
                # Whisper occasionally assigns one syllable a zero-length
                # timestamp. Keep it between its neighbours instead of
                # failing an otherwise well-matched recording.
                previous_end = times[c-1][1] if c else 0.0
                next_start = times[d][0] if d < len(times) else duration
                if next_start - previous_end <= .02:
                    raise ValueError('音频缺少可用时间范围，无法自动定位字幕')
                center = min(max(left, previous_end + .01), next_start - .01)
                half_width = min(.08, (center - previous_end) / 2, (next_start - center) / 2)
                if half_width <= 0:
                    raise ValueError('音频缺少可用时间范围，无法自动定位字幕')
                left, right = center - half_width, center + half_width
            step = (right-left)/(b-a)
            for i in range(a,b):
                char_times[i] = (left+(i-a)*step, left+(i-a+1)*step)
                repaired.add(i)
    cues = []
    offset = 0
    for unit, token in zip(units, normalized):
        indices = [i for i in range(offset, offset + len(token)) if i in char_times]
        ready = bool(indices) and offset in char_times and offset + len(token)-1 in char_times
        # Missing text stays visibly unresolved; do not manufacture timestamps.
        start = round(char_times[indices[0]][0], 3) if indices else None
        end = round(min(duration, char_times[indices[-1]][1]), 3) if indices else None
        cues.append({**unit, 'start': start, 'end': end,
                     'needs_timing_review': not ready or end is None or start is None or end <= start,
                     'matched_ratio': round(len(indices)/max(1,len(token)), 3)})
        if repair:
            cues[-1]['auto_repaired'] = any(i in repaired for i in range(offset, offset+len(token)))
            cues[-1]['matched_ratio'] = round(sum(i in matched for i in range(offset,offset+len(token)))/max(1,len(token)),3)
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
        if not caption or visible_len(caption.replace('《','').replace('》',''))>SUBTITLE_MAX_CHARS or not math.isfinite(start+end) or start<previous or end<=start or end>duration+.001:
            raise ValueError(f'字幕时间须递增、不重叠、不超过音频末尾，每条最多{SUBTITLE_MAX_CHARS}字')
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
