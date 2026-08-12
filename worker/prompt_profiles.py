"""Book-category prompt loading and shared prompt context helpers."""
from __future__ import annotations

import re
from pathlib import Path


PROMPT_ROOT = Path(__file__).parent / "prompts" / "categories"
SKILL_REFERENCE_ROOT = (
    Path(__file__).parent.parent
    / "skills"
    / "wechat-video-book-compliance"
    / "references"
)
ACTIVE_CATEGORIES = {"health", "social_science", "education"}


def normalize_category(value: object) -> str:
    category = str(value or "health").strip().lower()
    if category not in ACTIVE_CATEGORIES:
        raise ValueError(f"内容分类尚未开放：{category}")
    return category


def load_prompt(category: str, kind: str) -> str:
    category = normalize_category(category)
    path = PROMPT_ROOT / category / f"{kind}.txt"
    if not path.is_file():
        raise ValueError(f"未配置 {category} 分类的 {kind} 提示词")
    return path.read_text(encoding="utf-8").strip()


def rewrite_prompt_kind(mode: object) -> str:
    """Map task mode to an explicit first- or second-publication prompt."""
    return "repost_dedup" if str(mode or "initial_dedup") == "repost_dedup" else "initial_dedup"


def load_compliance_rules(category: str) -> str:
    category = normalize_category(category)
    if category != "health":
        path = PROMPT_ROOT / category / "compliance.txt"
        if not path.is_file():
            raise ValueError(f"未配置 {category} 分类的合规规则")
        return path.read_text(encoding="utf-8").strip()
    paths = (
        SKILL_REFERENCE_ROOT / "health-rules.md",
        SKILL_REFERENCE_ROOT / "prohibited-terms.md",
    )
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("合规 Skill 规则文件缺失：" + "、".join(missing))
    return "\n\n".join(path.read_text(encoding="utf-8").strip() for path in paths)


def author_name(author: object) -> str:
    if not isinstance(author, dict):
        return "未知"
    return str(author.get("name") or author.get("nickname") or author.get("author") or "未知").strip()


def derive_keyword(title: object, text: str) -> str:
    title_text = str(title or "").strip()
    hashtags = re.findall(r"#([^#\s，。！？,;；]{2,20})", title_text)
    books = re.findall(r"《([^》]{1,40})》", f"{title_text}\n{text}")
    terms = list(dict.fromkeys(hashtags + books))
    if terms:
        return "、".join(terms[:4])
    short_title = re.split(r"[。！？!?|｜]", title_text, maxsplit=1)[0].strip()
    return short_title[:40] or "书籍内容"


def protected_terms(text: str) -> list[str]:
    patterns = (
        r"《[^》]{1,40}》",
        r"\d+(?:\.\d+)?%?",
        r"\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?",
    )
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text or ""))
    return list(dict.fromkeys(found))[:80]
