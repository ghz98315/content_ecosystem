"""③ 清洗 clean：按书籍分类修复 ASR 并删除非正文噪声。"""
from __future__ import annotations
import json
import os
import re
import time
from difflib import SequenceMatcher

from opencc import OpenCC

import config
import db
import storage
from prompt_profiles import author_name, derive_keyword, load_prompt, normalize_category

_client = None
_MAX_EXPANSION_RATIO = max(0.0, float(os.environ.get("CLEAN_MAX_EXPANSION_RATIO", "0.10")))
_EXPANSION_RETRY = os.environ.get("CLEAN_EXPANSION_RETRY", "1").strip() != "0"
_SIMPLIFIED_CONVERTER = OpenCC("t2s")


def _to_simplified_chinese(text: str) -> str:
    """Normalize model output so downstream review and rewriting always use Simplified Chinese."""
    return _SIMPLIFIED_CONVERTER.convert(text or "")


def _effective_chars(text: str) -> int:
    """Count content characters while ignoring whitespace and punctuation."""
    return len(re.sub(r"[\s\.,，。！？!?；;：:、（）()【】\[\]「」『』“”\"'‘’…—\-_/\\·~@#$%^&*+=<>|`]", "", text or ""))


def _clean_output_issue(raw: str, cleaned: str) -> str | None:
    """Reject empty output and silent model expansion beyond the review limit."""
    raw_chars = len((raw or "").strip())
    clean_chars = len((cleaned or "").strip())
    raw_effective = _effective_chars(raw)
    clean_effective = _effective_chars(cleaned)
    if not clean_chars:
        return "清洗模型返回空正文"
    if raw_effective and clean_effective > raw_effective * (1 + _MAX_EXPANSION_RATIO):
        ratio = (clean_effective - raw_effective) / raw_effective
        return (
            f"清洗结果异常扩写：原文 {raw_chars} 字，清洗后 {clean_chars} 字，"
            f"增加 {ratio:.1%}，超过允许上限 {_MAX_EXPANSION_RATIO:.1%}"
        )
    return None


def _extract_opening_hook(transcript: dict, seconds: float = 10.0) -> str:
    """Use transcript timestamps to preserve the tested opening hook."""
    parts = []
    for segment in transcript.get("segments") or []:
        if float(segment.get("start") or 0) >= seconds:
            break
        text = str(segment.get("text") or "").strip()
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _hook_preservation_issue(hook: str, cleaned: str) -> str | None:
    if not hook:
        return None
    hook_key = "".join(hook.split())
    opening_key = "".join((cleaned or "")[: max(len(hook) * 2, 80)].split())
    if SequenceMatcher(None, hook_key, opening_key, autojunk=False).ratio() < 0.45:
        return "清洗结果疑似删除或重写了前约 10 秒的开头钩子"
    return None


def _summarize_changes(raw: str, cleaned: str, limit: int = 24) -> dict:
    """Keep a compact, reviewable record of deleted/replaced source spans."""
    segments = []
    removed_chars = 0
    matcher = SequenceMatcher(None, raw or "", cleaned or "", autojunk=True)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        before = (raw or "")[i1:i2].strip()
        after = (cleaned or "")[j1:j2].strip()
        if not before:
            continue
        removed_chars += max(0, len(before) - len(after))
        if len(segments) < limit:
            segments.append({
                "kind": "delete" if not after else "replace",
                "before": before[:240],
                "after": after[:240],
            })
    raw_chars = len(raw or "")
    clean_chars = len(cleaned or "")
    raw_effective_chars = _effective_chars(raw)
    clean_effective_chars = _effective_chars(cleaned)
    return {
        "raw_chars": raw_chars,
        "clean_chars": clean_chars,
        "raw_effective_chars": raw_effective_chars,
        "clean_effective_chars": clean_effective_chars,
        "punctuation_chars_added": max(0, (clean_chars - clean_effective_chars) - (raw_chars - raw_effective_chars)),
        "removed_chars": removed_chars,
        "removed_ratio": round(max(0, raw_chars - clean_chars) / raw_chars, 4) if raw_chars else 0,
        "segments": segments,
        "segments_truncated": len(segments) >= limit,
    }

def _llm():
    global _client
    if not _client:
        _client = config.clean_client()
    return _client


def _request_clean(system_prompt: str, user_prompt: str) -> str:
    kwargs = {
        "model": config.CLEAN_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    for attempt in range(config.DEEPSEEK_RETRIES + 1):
        try:
            resp = _llm().chat.completions.create(**kwargs)
            break
        except Exception as exc:
            if attempt >= config.DEEPSEEK_RETRIES or "524" not in str(exc):
                raise
            time.sleep(min(10, 2 ** attempt))
    return (resp.choices[0].message.content or "").strip()


def _find_transcript(task_id: str) -> str | None:
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "transcript")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["storage_path"] if res.data else None


def _task_context(task_id: str, raw_text: str) -> dict[str, str]:
    task = db.get_task_prompt_context(task_id)
    category = normalize_category(task.get("content_category"))
    title = str(task.get("title") or "")
    return {
        "category": category,
        "title": title,
        "author": author_name(task.get("author")),
        "keyword": derive_keyword(title, raw_text),
    }


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    tr_path = _find_transcript(task_id)
    if not tr_path:
        db.set_stage(stage["id"], "failed", error="未找到逐字稿产物（transcribe 未完成？）")
        return "failed", None

    local = storage.download_artifact(tr_path, ".json")
    try:
        tr = json.load(open(local, encoding="utf-8"))
        raw_text = tr.get("text", "")
        opening_hook = _extract_opening_hook(tr)
    finally:
        try:
            os.remove(local)
        except OSError:
            pass

    if not raw_text.strip():
        db.set_stage(stage["id"], "failed", error="逐字稿正文为空")
        return "failed", None

    context = _task_context(task_id, raw_text)
    prompt = load_prompt(context["category"], "clean")
    user_prompt = (
        f"主题关键词：{context['keyword']}\n"
        f"原视频标题：{context['title']}\n"
        f"原作者标识：{context['author']}\n\n"
        f"前约 10 秒开头钩子（必须保留，只允许修复 ASR 错字和标点）：\n{opening_hook or '未取得时间戳钩子'}\n\n"
        f"请基于下面的原始逐字稿，返回修复清洗后的正文。硬性长度约束：逐句对应原文，"
        f"不得新增任何原文没有的语义内容；除必要标点外，清洗稿字符数应不超过原文。\n{raw_text}"
    )

    cleaned = _to_simplified_chinese(_request_clean(prompt, user_prompt))
    quality_issue = _clean_output_issue(raw_text, cleaned) or _hook_preservation_issue(opening_hook, cleaned)
    if quality_issue and _EXPANSION_RETRY and "异常扩写" in quality_issue:
        retry_prompt = (
            prompt
            + "\n\n这是一次严格纠偏重试。上一版输出超过原文长度，说明加入了未经确认的内容。"
            "现在只允许复制原文字符、删除噪声、替换有明确上下文依据的 ASR 错字和补必要标点。"
            "任何新增的医学术语、解释、句子或对话都必须删除；输出长度必须不超过原文。"
        )
        retry_user = user_prompt + "\n\n上一版超长输出（仅用于定位新增内容，不得照抄）：\n" + cleaned
        cleaned = _to_simplified_chinese(_request_clean(retry_prompt, retry_user))
        quality_issue = _clean_output_issue(raw_text, cleaned) or _hook_preservation_issue(opening_hook, cleaned)

    data = json.dumps(
        {
            "raw": raw_text,
            "cleaned": cleaned,
            "context": context,
            "opening_hook": opening_hook,
            "opening_hook_seconds": 10,
            "change_summary": _summarize_changes(raw_text, cleaned),
            "quality_issue": quality_issue,
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    sp = f"{task_id}/clean.json"
    storage.upload_bytes(sp, data, "application/json")
    storage.add_artifact(task_id, "clean", "clean", sp, meta={
        "raw_chars": len(raw_text),
        "clean_chars": len(cleaned),
        "raw_effective_chars": _effective_chars(raw_text),
        "clean_effective_chars": _effective_chars(cleaned),
        "model": config.CLEAN_MODEL,
        "content_category": context["category"],
        "opening_hook": opening_hook[:500],
        "quality_issue": quality_issue,
    })
    if quality_issue:
        db.set_stage(stage["id"], "failed", output_ref=sp, error=quality_issue)
        return "failed", sp
    return "done", sp
