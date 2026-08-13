"""Normalize source descriptions into a clean title and reusable topic tags."""
from __future__ import annotations

import re


_TAG_RE = re.compile(r"#([^#]+?)(?=(?:[_\s]*#)|$)")


def split_source_description(value: object) -> tuple[str, list[str]]:
    raw = str(value or "").strip()
    tags = []
    for match in _TAG_RE.findall(raw):
        tag = re.sub(r"[_\s]+", "", match).strip("#，。！？；：,!?;:、")
        if tag and tag not in tags:
            tags.append(tag)
    title = raw[: raw.find("#")] if "#" in raw else raw
    title = re.sub(r"_+", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" _，。！？；：,!?;:、")
    return title, tags


def publication_title(value: object, limit: int = 16) -> str:
    text = re.sub(r"[\s\W_]+", "", str(value or ""), flags=re.UNICODE)
    return text[:limit]
