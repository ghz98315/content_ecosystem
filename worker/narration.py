"""Canonical narration cleanup and semantic subtitle splitting."""
from __future__ import annotations

import html
import json
import logging
import re

import jieba
import jieba.posseg as pseg

jieba.setLogLevel(logging.WARNING)


_SUBTITLE_PUNCTUATION_RE = re.compile(
    r"[，。！？；：、,.!?;:“”‘’\"'（）()【】\[\]《》〈〉—…·~～\-]+"
)
_PAUSE_SECONDS = {
    "，": 0.3, ",": 0.3, "、": 0.3,
    "。": 0.8, ".": 0.8,
    "！": 0.9, "!": 0.9, "？": 0.9, "?": 0.9,
    "—": 0.7, "…": 0.9,
    "；": 0.45, ";": 0.45, "：": 0.45, ":": 0.45,
    "“": 0.15, "”": 0.15, "‘": 0.15, "’": 0.15,
    '"': 0.15, "'": 0.15,
}


def clean_tts_text(text: str) -> str:
    """Return plain narration, excluding screenplay and formatting instructions."""
    if not text:
        return ""
    source = str(text).strip()
    unfenced = re.sub(r"^```(?:json|text|markdown)?\s*|\s*```$", "", source, flags=re.I | re.S).strip()
    try:
        payload = json.loads(unfenced)
        if isinstance(payload, str):
            source = payload
        elif isinstance(payload, dict):
            for key in ("final_text", "text", "narration", "voiceover", "script", "content"):
                if str(payload.get(key) or "").strip():
                    source = str(payload[key])
                    break
    except (json.JSONDecodeError, TypeError, ValueError):
        source = unfenced

    lines: list[str] = []
    for raw in source.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("```") or re.fullmatch(r"[-_=*~#]{3,}", line):
            continue
        if re.match(r"^#{1,6}\s+", line):
            continue
        if re.fullmatch(r"(?:\[?\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:[-~]\s*\d{1,2}:\d{2}(?::\d{2})?)?\s*\]?)", line):
            continue
        line = re.sub(r"^\s*\[?\d{1,2}:\d{2}(?::\d{2})?\s*(?:[-~]\s*\d{1,2}:\d{2}(?::\d{2})?)?\]?\s*", "", line)
        narration = re.search(r"(?:旁白|画外音|口播|文案)\s*[:：]\s*(.+)$", line)
        if narration:
            line = narration.group(1).strip()
        elif re.match(r"^[【\[]?(?:画面|镜头|场景|时间|时间点|时长|字幕|转场|音效|配乐|分镜)[】\]]?\s*[:：-]", line):
            continue
        else:
            line = re.sub(r"^[【\[]?(?:正文|开头钩子|中间内容|结尾收束|结尾)[】\]]?\s*[:：-]\s*", "", line)
        line = re.sub(r"^(?:[-+*•]\s+|\d+[.、]\s*)", "", line)
        line = re.sub(r"^\s*(?:[-_=*~]){2,}\s*", "", line).strip()
        line = html.unescape(line)
        line = re.sub(r"</?(?:speak|voice)\b[^>]*>|<break\b[^>]*/?>", "", line, flags=re.I)
        line = re.sub(r"[*_`]+", "", line).strip()
        if line and not re.fullmatch(r"[\d\s:：,，.。-]+", line):
            lines.append(line)
    return "\n".join(lines).strip()


def visible_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


_DIGIT_ZH = "零一二三四五六七八九"
_NUMBER_UNITS = ("", "十", "百", "千")


def _integer_to_zh(value: str) -> str:
    """Read ordinary Arabic integers naturally for TTS without changing display text."""
    digits = str(value).lstrip("0") or "0"
    if len(digits) > 8:
        return "".join(_DIGIT_ZH[int(char)] for char in value)
    number = int(digits)
    if number == 0:
        return "零"
    result: list[str] = []
    zero_pending = False
    for index, char in enumerate(digits):
        digit = int(char)
        position = len(digits) - index - 1
        if digit == 0:
            if result:
                zero_pending = True
            continue
        if zero_pending:
            result.append("零")
            zero_pending = False
        if not (digit == 1 and position == 1 and not result):
            result.append(_DIGIT_ZH[digit])
        if position:
            result.append(_NUMBER_UNITS[position])
    return "".join(result)


def normalize_tts_numbers(text: str) -> str:
    """Convert ordinary numbers for speech while preserving versions and identifiers."""
    source = str(text or "")

    def version(match: re.Match[str]) -> str:
        token = match.group(0)
        return "点".join("".join(_DIGIT_ZH[int(char)] for char in part) for part in token.split("."))

    def percent(match: re.Match[str]) -> str:
        token = match.group(0)[:-1]
        return f"百分之{_decimal_to_zh(token)}"

    def year(match: re.Match[str]) -> str:
        digits = match.group(0)[:4]
        # Use cardinal reading for round millennia such as 5000年. Digit-wise
        # "五〇〇〇年" is often collapsed by TTS to "五年".
        spoken = _integer_to_zh(digits) if digits[1:] == "000" else "".join(
            "〇" if char == "0" else _DIGIT_ZH[int(char)] for char in digits
        )
        return spoken + "年"

    def decimal(match: re.Match[str]) -> str:
        token = match.group(0)
        suffix = ""
        while token and token[-1] in "万亿千百岁元天人次倍":
            suffix = token[-1] + suffix
            token = token[:-1]
        return _decimal_to_zh(token) + suffix

    def integer(match: re.Match[str]) -> str:
        token = match.group(0)
        suffix = ""
        while token and token[-1] in "万亿千百岁元天人次倍个种年月日":
            suffix = token[-1] + suffix
            token = token[:-1]
        return _integer_to_zh(token) + suffix

    def _replace(pattern: str, callback, value: str) -> str:
        return re.sub(pattern, callback, value)

    source = _replace(r"(?<![A-Za-z])\d+(?:\.\d+)+(?![A-Za-z])", version, source)
    source = _replace(r"(?<![A-Za-z])\d+(?:\.\d+)?%", percent, source)
    source = _replace(r"(?<!\d)\d{4}年", year, source)
    source = _replace(r"(?<![A-Za-z])\d+\.\d+(?:[万亿千百岁元天人次倍])?", decimal, source)
    return _replace(r"(?<![A-Za-z])\d+(?:[万亿千百岁元天人次倍个种年月日])?", integer, source)


def _decimal_to_zh(value: str) -> str:
    if "." not in value:
        return _integer_to_zh(value)
    whole, fraction = value.split(".", 1)
    return f"{_integer_to_zh(whole)}点{''.join(_DIGIT_ZH[int(char)] for char in fraction)}"


def strip_subtitle_punctuation(text: str) -> str:
    """Remove punctuation from on-screen subtitles while retaining words."""
    return re.sub(r"\s+", "", _SUBTITLE_PUNCTUATION_RE.sub("", text or ""))


def has_disallowed_subtitle_punctuation(text: str) -> bool:
    """Allow paired Chinese book-title marks, but reject other subtitle punctuation."""
    value = str(text or "")
    if re.fullmatch(r"(?:[^《》]|《[^《》]+》)*", value) is None:
        return True
    unmarked = value.replace("《", "").replace("》", "")
    return unmarked != strip_subtitle_punctuation(value)


def pause_after_text(text: str) -> float:
    """Return the requested pause represented by trailing punctuation."""
    compact = re.sub(r"\s+", "", text or "")
    trailing = re.search(r"([，。！？；：、,.!?;:“”‘’\"'—…]+)$", compact)
    if not trailing:
        return 0.0
    marks = trailing.group(1)
    pause = 0.0
    index = 0
    while index < len(marks):
        if marks[index:index + 2] in ("……", "——"):
            pause += 0.9 if marks[index] == "…" else 0.7
            index += 2
            continue
        pause += _PAUSE_SECONDS.get(marks[index], 0.0)
        index += 1
    return round(min(1.1, pause), 2)


_NO_BREAK_WORDS = (
    "人工智能", "内容创作", "短视频", "图书视频", "配音字幕", "视频画面",
    "播放时长", "时间轴", "根据语义", "合理计算", "用户可以", "需要确认",
    "不会出现", "是否能够", "最后一步", "同时保证", "如果没有", "因为这样",
    "所以需要", "但是不能", "图片播放", "字幕切分", "语义边界", "字幕画面",
    "画面对应", "字幕对应", "相互对应", "对应关系", "上下居中", "完整性",
    "语气停顿", "标点符号", "播放时间", "播放效果", "分段配音", "最终成片",
    "图书内容", "健康知识", "专业建议", "免责声明", "重新生成", "人工确认",
)

_MAJOR_SUBTITLE_BREAKS = set("。！？!?；;…")
_MINOR_SUBTITLE_BREAKS = set("，,：:")
_AWKWARD_LINE_END = set("的了着过和与及或而但并把被在对从向给将以为")
_AWKWARD_LINE_START = set("的了着过吗呢吧啊呀和与及或而但并")
_NUMBER_UNIT_RE = re.compile(
    r"(?:第\d+(?:\.\d+)?[章节步点项]|\d+(?:\.\d+)?(?:%|％|年|月|天|小时|分钟|秒|次|个|条|页|章|岁|元|万元|公斤|千克|克|毫克|厘米|毫米|米|倍))"
)
_LATIN_NUMBER_RE = re.compile(r"[A-Za-z0-9]+(?:[._%+/-][A-Za-z0-9]+)*")


def _protected_boundaries(text: str, protected_terms: tuple[str, ...] = ()) -> set[int]:
    protected: set[int] = set()

    # Jieba provides the general Chinese word boundaries. Every position inside
    # a token is protected; punctuation remains a standalone boundary.
    for word, start, end in jieba.tokenize(text, mode="default"):
        if strip_subtitle_punctuation(word):
            protected.update(range(start + 1, end))

    # Jieba intentionally separates adjacent lexical items. Protect common
    # Chinese compound-noun joins such as 健康+管理 and 人工智能+技术 as well.
    tagged: list[tuple[str, str, int, int]] = []
    cursor = 0
    for token in pseg.cut(text):
        start = text.find(token.word, cursor)
        if start < 0:
            start = cursor
        end = start + len(token.word)
        tagged.append((token.word, token.flag, start, end))
        cursor = end
    for left, right in zip(tagged, tagged[1:]):
        left_word, left_flag, _left_start, left_end = left
        right_word, right_flag, right_start, _right_end = right
        if left_end != right_start:
            continue
        left_nominal = left_flag.startswith(("n", "a", "b", "j"))
        right_nominal = right_flag.startswith(("n", "vn"))
        if left_nominal and right_nominal and strip_subtitle_punctuation(left_word + right_word):
            protected.add(left_end)

    for word in (*_NO_BREAK_WORDS, *protected_terms):
        if not word:
            continue
        offset = text.find(word)
        while offset >= 0:
            protected.update(range(offset + 1, offset + len(word)))
            offset = text.find(word, offset + 1)

    for pattern in (r"《[^》]+》", _NUMBER_UNIT_RE, _LATIN_NUMBER_RE):
        for match in re.finditer(pattern, text) if isinstance(pattern, str) else pattern.finditer(text):
            protected.update(range(match.start() + 1, match.end()))
    return protected


def _word_boundaries(text: str) -> set[int]:
    boundaries = {len(text)}
    for word, _start, end in jieba.tokenize(text, mode="default"):
        if strip_subtitle_punctuation(word):
            boundaries.add(end)
    return boundaries


def _boundary_kind(text: str, end: int, word_boundaries: set[int]) -> str:
    if end >= len(text):
        return "end"
    previous = text[end - 1]
    if previous in _MAJOR_SUBTITLE_BREAKS:
        return "major"
    if previous in _MINOR_SUBTITLE_BREAKS:
        return "minor"
    if end in word_boundaries:
        return "word"
    return "forced"


def _split_cost(text: str, start: int, end: int, max_chars: int,
                kind: str, protected: set[int]) -> float:
    display = strip_subtitle_punctuation(text[start:end])
    length = visible_len(display)
    base = {"end": 0.0, "major": 0.0, "minor": 2.0, "word": 8.0, "forced": 100.0}[kind]
    if end < len(text) and end in protected:
        base += 1000.0

    # Natural punctuation is allowed to make a short screen. Word cuts should
    # stay close to the limit while leaving enough text for the next screen.
    length_weight = 0.03 if kind in {"end", "major", "minor"} else 0.3
    cost = base + (max_chars - length) ** 2 * length_weight
    if length < 4 and (end < len(text) or start > 0):
        cost += 14.0
    if display and display[-1] in _AWKWARD_LINE_END and end < len(text):
        cost += 8.0
    next_display = strip_subtitle_punctuation(text[end:])
    if next_display and next_display[0] in _AWKWARD_LINE_START:
        cost += 8.0

    interior = text[start:max(start, end - 1)]
    cost += sum(char in _MAJOR_SUBTITLE_BREAKS for char in interior) * 40.0
    cost += sum(char in _MINOR_SUBTITLE_BREAKS for char in interior) * 8.0
    return cost


def _semantic_cuts(
    text: str,
    max_chars: int,
    protected_terms: tuple[str, ...] = (),
) -> list[tuple[int, str]]:
    """Choose globally balanced cuts without breaking normal Chinese words."""
    protected = _protected_boundaries(text, protected_terms)
    word_boundaries = _word_boundaries(text)
    size = len(text)
    best: list[tuple[float, list[tuple[int, str]]] | None] = [None] * (size + 1)
    best[size] = (0.0, [])

    for start in range(size - 1, -1, -1):
        winner: tuple[float, list[tuple[int, str]]] | None = None
        for end in range(start + 1, size + 1):
            display_len = visible_len(strip_subtitle_punctuation(text[start:end]))
            if display_len > max_chars:
                break
            if display_len == 0 or best[end] is None:
                continue
            kind = _boundary_kind(text, end, word_boundaries)
            cost = _split_cost(text, start, end, max_chars, kind, protected) + best[end][0]
            candidate = (cost, [(end, kind), *best[end][1]])
            if winner is None or candidate[0] < winner[0]:
                winner = candidate
        best[start] = winner

    if best[0] is None:
        raise ValueError("字幕无法在限定字数内完成切分")
    return best[0][1]


def split_semantic_units(
    text: str,
    max_chars: int = 14,
    protected_terms: tuple[str, ...] = (),
) -> list[dict]:
    """Split at punctuation or Chinese word boundaries, never raw width first."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return []

    units: list[dict] = []
    start = 0
    for cut, kind in _semantic_cuts(compact, max_chars, protected_terms):
        raw = compact[start:cut]
        source_length = visible_len(raw)
        display = strip_subtitle_punctuation(raw)
        display_length = visible_len(display)
        if kind == "forced":
            preview = display[:max_chars + 2]
            raise ValueError(f"字幕存在超过{max_chars}字且无法保持完整的词语：{preview}")
        if display and source_length:
            units.append({
                "text": display,
                "source_text": raw,
                "char_start": start,
                "char_end": cut,
                "char_count": display_length,
                "pause_after": pause_after_text(raw),
                "boundary": kind,
            })
        start = cut
    return units
