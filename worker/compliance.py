"""Deterministic and semantic compliance checks for book-video scripts."""
from __future__ import annotations

import json
import re
from typing import Any

from prompt_profiles import load_compliance_rules, load_prompt, normalize_category


_RULES = (
    (
        "high",
        "疗效承诺或替代医疗",
        re.compile(
            r"(?:根治|治愈|彻底(?:解决|治好|消除|清除)|立刻见效|马上见效|"
            r"(?:\d+|一|二|三|四|五|六|七|八|九|十)天(?:见效|治好|逆转)|"
            r"不用去医院|无需就医|替代(?:药物|吃药|治疗)|比(?:吃药|药物|医院).{0,8}(?:有效|管用)|"
            r"一定有效|100%有效|百分之百有效|无副作用|零风险)"
        ),
        "删除结果保证或替代医疗的表述，改为不承诺效果的一般性知识表达。",
    ),
    (
        "high",
        "虚假权威或诊疗导流",
        re.compile(
            r"(?:医生不会告诉你|医院内部方法|专家都在用|"
            r"(?:加微信|私信|到主页).{0,12}(?:看病|问诊|诊断|用药|治疗方案))"
        ),
        "删除虚假权威或诊疗导流，不提供个性化医疗建议。",
    ),
    (
        "medium",
        "疾病和诊疗敏感表达",
        re.compile(
            r"(?:癌症|肿瘤|心梗|脑梗|糖尿病|抑郁症|诊断|处方|化疗|手术|注射|抗癌|防癌|降血压|降血糖)"
        ),
        "核对是否为中性知识引用；不得形成诊断、治疗或功效承诺。",
    ),
    (
        "medium",
        "制造健康焦虑",
        re.compile(
            r"(?:已经很危险|慢性自杀|再这样下去.{0,8}(?:出大事|没救)|"
            r"符合.{0,8}(?:条|项).{0,8}(?:身体出问题|说明你有))"
        ),
        "删除恐吓和对号入座，客观描述信息边界。",
    ),
    (
        "medium",
        "绝对化或夸大宣传",
        re.compile(
            r"(?:全网第一|销量第一|世界领先|遥遥领先|独一无二|唯一|永久|万能|完美|"
            r"史无前例|万人疯抢|卖疯了|错过就没机会|再不抢就没了)"
        ),
        "删除无法证实的最高级、唯一性、稀缺性或抢购暗示。",
    ),
)


def scan_text(text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for level, category, pattern, suggestion in _RULES:
        for match in pattern.finditer(text or ""):
            key = (category, match.group(0))
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "level": level,
                "category": category,
                "text": match.group(0),
                "reason": f"命中{category}规则，需要结合完整语境复核。",
                "suggestion": suggestion,
                "source": "rule",
            })
    return issues


def _semantic_issues(client: Any, model: str, category: str, text: str, context: dict[str, str]) -> list[dict[str, str]]:
    prompt = load_prompt(category, "compliance")
    rules = load_compliance_rules(category)
    user = (
        f"内容分类：{category}\n"
        f"主题关键词：{context.get('keyword', '')}\n"
        f"原视频标题：{context.get('title', '')}\n"
        f"原作者标识：{context.get('author', '')}\n\n"
        "请逐条返回风险片段、风险等级、原因，以及一个不使用谐音规避、"
        "不做疗效承诺、可供人工确认的中性替代表达 replacement。\n"
        f"待检查最终文案：\n{text}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": f"{prompt}\n\n以下是本次必须使用的内部检查规则：\n{rules}"},
            {"role": "user", "content": user},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    payload = json.loads(raw)
    raw_issues = payload.get("issues", []) if isinstance(payload, dict) else []
    issues: list[dict[str, str]] = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level", "medium")).lower()
        if level not in {"high", "medium", "low"}:
            level = "medium"
        snippet = str(item.get("text", "")).strip()
        if not snippet or snippet not in text:
            continue
        issues.append({
            "level": level,
            "category": str(item.get("category", "语义风险")).strip() or "语义风险",
            "text": snippet,
            "reason": str(item.get("reason", "需要人工复核")).strip(),
            "suggestion": str(item.get("suggestion", "请做最小幅度修改")).strip(),
            "replacement": str(item.get("replacement", "")).strip(),
            "source": "semantic",
        })
    return issues


def check_text(client: Any, model: str, category: str, text: str, context: dict[str, str]) -> dict[str, Any]:
    category = normalize_category(category)
    issues = scan_text(text)
    try:
        issues.extend(_semantic_issues(client, model, category, text, context))
        semantic_complete = True
    except Exception:  # noqa: BLE001
        semantic_complete = False
        issues.append({
            "level": "high",
            "category": "合规检查未完成",
            "text": "",
            "reason": "语义检查服务未返回有效结果，本次检查不完整。",
            "suggestion": "请重试合规检查后再继续。",
            "source": "system",
        })

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (issue["category"], issue["text"])
        if key not in seen:
            deduped.append(issue)
            seen.add(key)

    levels = {item["level"] for item in deduped}
    status = "blocked" if "high" in levels else "warning" if levels else "pass"
    return {
        "status": status,
        "issues": deduped,
        "semantic_complete": semantic_complete,
        "category": category,
    }
