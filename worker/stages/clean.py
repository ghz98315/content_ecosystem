"""③ 清洗 clean：按书籍分类修复 ASR 并删除非正文噪声。"""
from __future__ import annotations
import json
import os
from difflib import SequenceMatcher

import config
import db
import storage
from prompt_profiles import author_name, derive_keyword, load_prompt, normalize_category

_client = None


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
    return {
        "raw_chars": raw_chars,
        "clean_chars": clean_chars,
        "removed_chars": removed_chars,
        "removed_ratio": round(max(0, raw_chars - clean_chars) / raw_chars, 4) if raw_chars else 0,
        "segments": segments,
        "segments_truncated": len(segments) >= limit,
    }

def _llm():
    global _client
    if not _client:
        _client = config.openai_client()
    return _client


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
        f"请基于下面的原始逐字稿，返回修复清洗后的正文：\n{raw_text}"
    )

    resp = _llm().chat.completions.create(
        model=config.CLEAN_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    cleaned = resp.choices[0].message.content.strip()

    data = json.dumps(
        {
            "raw": raw_text,
            "cleaned": cleaned,
            "context": context,
            "change_summary": _summarize_changes(raw_text, cleaned),
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    sp = f"{task_id}/clean.json"
    storage.upload_bytes(sp, data, "application/json")
    storage.add_artifact(task_id, "clean", "clean", sp, meta={
        "raw_chars": len(raw_text),
        "clean_chars": len(cleaned),
        "model": config.CLEAN_MODEL,
        "content_category": context["category"],
    })
    return "done", sp
