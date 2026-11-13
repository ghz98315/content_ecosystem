"""Lossless 90–120 character storyboard cuts shared by visual pipelines."""

MIN_CHARS = 90
MAX_CHARS = 120
VERSION = 'storyboard-90-120-v1'


def effective_count(text: str) -> int:
    return sum(char.isalnum() for char in text)


def split_shots(text: str) -> list[str]:
    if not text.strip():
        return []
    positions = [index for index, char in enumerate(text) if char.isalnum()]
    total = len(positions)
    shot_count = max(1, (total + MAX_CHARS - 1) // MAX_CHARS)
    final_minimum = MIN_CHARS if total >= shot_count * MIN_CHARS else 1
    parts = []
    start = consumed = 0
    for left in range(shot_count - 1, 0, -1):
        remaining = total - consumed
        low = max(MIN_CHARS, remaining - left * MAX_CHARS)
        high = min(MAX_CHARS, remaining - (left - 1) * MIN_CHARS - final_minimum)
        target = remaining / (left + 1) if final_minimum == MIN_CHARS else MIN_CHARS

        def boundary_score(size: int) -> float:
            boundary = text[positions[consumed + size - 1] + 1:positions[consumed + size]]
            penalty = (0 if any(c in boundary for c in '。！？!?…\n')
                       else 9 if any(c in boundary for c in '，,；;：:、')
                       else 18 if boundary else 24)
            return abs(size - target) + penalty

        size = min(range(low, high + 1), key=boundary_score)
        consumed += size
        end = positions[consumed]
        # Opening punctuation belongs with the next passage.
        while end > positions[consumed - 1] + 1 and text[end - 1] in '《“‘（【「『([{':
            end -= 1
        parts.append(text[start:end])
        start = end
    parts.append(text[start:])
    return parts
