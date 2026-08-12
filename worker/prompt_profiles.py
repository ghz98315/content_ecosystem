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
_CATEGORY_APPENDIX = {
    "social_science": "\n\n当前为历史社科流程：保持史实、年代、人物与引文边界；不得把推测写成事实，不煽动对立，不用群体刻板印象。叙事应克制、清晰、有史料感。",
    "education": "\n\n当前为经管书籍流程：保持企业、人物、数据和因果边界；不得承诺收益、预测市场、给出个性化投资建议或把个案包装为必然规律。叙事应强调方法、条件和适用边界。",
}


def normalize_category(value: object) -> str:
    category = str(value or "health").strip().lower()
    if category not in ACTIVE_CATEGORIES:
        raise ValueError(f"内容分类尚未开放：{category}")
    return category


def load_prompt(category: str, kind: str) -> str:
    category = normalize_category(category)
    path = PROMPT_ROOT / category / f"{kind}.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    fallback = PROMPT_ROOT / "health" / f"{kind}.txt"
    if not fallback.is_file():
        raise ValueError(f"未配置 {category} 分类的 {kind} 提示词")
    return fallback.read_text(encoding="utf-8").strip() + _CATEGORY_APPENDIX.get(category, "")


def rewrite_prompt_kind(mode: object) -> str:
    """Map task mode to an explicit first- or second-publication prompt."""
    return "repost_dedup" if str(mode or "initial_dedup") == "repost_dedup" else "initial_dedup"


def load_compliance_rules(category: str) -> str:
    category = normalize_category(category)
    if category != "health":
        return _CATEGORY_APPENDIX[category]
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
