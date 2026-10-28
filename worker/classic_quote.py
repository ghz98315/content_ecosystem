"""Select attributed, short classical sayings for the Guoxue picture overlay."""

import re


def _plain(value: str) -> str:
    return ''.join(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]', value))


def quote_overlays(script: str, cues: list[dict], duration: float) -> list[dict]:
    """Only use a quoted saying present verbatim in the aligned narration."""
    if not script or not cues:
        return []
    paragraphs = [part.strip() for part in re.split(r'\n\s*\n|\n', script) if part.strip()]
    spoken = ''
    offsets: list[int] = []
    for index, cue in enumerate(cues):
        clean = _plain(str(cue.get('text', '')))
        spoken += clean
        offsets.extend([index] * len(clean))
    found: list[dict] = []
    search_from = 0
    for paragraph in paragraphs:
        for match in re.finditer(r'[“‘「]([^”’」]{8,36})[”’」]', paragraph):
            prefix = paragraph[:match.start()]
            if not re.search(r'《[^》]{1,18}》|古人[说言云]|原典|经典[说云]|先贤[说言云]', prefix[-65:]):
                continue
            quote = match.group(1).strip()
            parts = [part.strip() for part in re.split(r'[，,；;]', quote)]
            if len(parts) != 2 or any(not 4 <= len(_plain(part)) <= 13 for part in parts):
                continue
            clean = _plain(quote)
            position = spoken.find(clean, search_from)
            if position < 0:
                continue
            first = cues[offsets[position]]
            last_index = offsets[position + len(clean) - 1]
            last = cues[last_index]
            start = max(0.0, float(first.get('start', 0)))
            quote_end = float(last.get('end', start))
            # Hold through the explanation in this paragraph when its ending can
            # be aligned; never infer a timing from unrelated later narration.
            tail = _plain(paragraph[match.end():])
            end = min(duration, quote_end + 10.0)
            if len(tail) >= 6:
                needle = tail[-min(10, len(tail)):]
                tail_at = spoken.find(needle, position + len(clean))
                if 0 <= tail_at - position <= 260:
                    end = min(duration, float(cues[offsets[tail_at + len(needle) - 1]].get('end', end)))
            end = max(quote_end, end)
            if end - start < 1:
                continue
            found.append({'start': start, 'end': end, 'lines': parts})
            search_from = position + len(clean)
            if len(found) >= 3:
                return found
    return found
