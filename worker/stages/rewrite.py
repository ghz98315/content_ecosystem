"""④ 改写 rewrite：清洗稿 -> 三个完整候选 -> 人工确认唯一 final_text。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import config
import db
import storage

_PROMPT = (Path(__file__).parent.parent / "prompts" / "rewrite.txt").read_text(encoding="utf-8")
_CAND_RE = re.compile(r"【候选[ABC]】\s*(.*?)(?=【候选[ABC]】|$)", re.DOTALL)
_STYLE_KEYS = ("pain", "story", "knowledge")
_client = None


def _llm():
    global _client
    if not _client:
        _client = config.openai_client()
    return _client


def _text_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _parse_candidates(raw: str) -> list[str]:
    """Parse the structured response and retain legacy marker compatibility."""
    try:
        payload = json.loads(raw)
        items = payload.get("candidates", []) if isinstance(payload, dict) else []
        parsed = [
            str(item.get("text", "")).strip() if isinstance(item, dict) else str(item).strip()
            for item in items
        ]
        if len(parsed) == 3 and all(parsed):
            return parsed
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    matches = [m.strip() for m in _CAND_RE.findall(raw)]
    return matches if len(matches) == 3 else []


def _candidate_issues(candidates: list[str], source: str, finish_reason: str | None) -> list[str]:
    issues: list[str] = []
    if finish_reason == "length":
        issues.append("模型输出达到长度上限")
    if len(candidates) != 3:
        issues.append("未生成三个完整候选")
        return issues

    source_len = _text_len(source)
    min_len = max(40, round(source_len * 0.7))
    max_len = max(min_len + 20, round(source_len * 1.35))
    for i, text in enumerate(candidates):
        length = _text_len(text)
        if length < min_len:
            issues.append(f"候选 {i + 1} 过短（{length}/{source_len} 字）")
        if length > max_len:
            issues.append(f"候选 {i + 1} 明显超出原文长度（{length}/{source_len} 字）")
        if re.search(r"(?:未完待续|请继续|继续输出|\.\.\.|……)\s*$", text):
            issues.append(f"候选 {i + 1} 疑似被截断")
        if text.rstrip().endswith(("，", ",", "：", ":", "；", ";", "、")):
            issues.append(f"候选 {i + 1} 结尾不完整")
    return issues


def _generate_candidates(source: str) -> tuple[list[str], list[int]]:
    source_len = _text_len(source)
    last_issues: list[str] = []
    for attempt in range(2):
        correction = ""
        if attempt:
            correction = "\n上一次输出不合格：" + "；".join(last_issues) + "。请完整重写并严格输出 JSON。"
        resp = _llm().chat.completions.create(
            model=config.REWRITE_MODEL,
            messages=[
                {"role": "system", "content": _PROMPT},
                {
                    "role": "user",
                    "content": f"原文有效字数约 {source_len} 字，请尽量保持相近长度。{correction}\n\n{source}",
                },
            ],
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        choice = resp.choices[0]
        raw = (choice.message.content or "").strip()
        candidates = _parse_candidates(raw)
        last_issues = _candidate_issues(candidates, source, getattr(choice, "finish_reason", None))
        if not last_issues:
            return candidates, [_text_len(text) for text in candidates]
    raise ValueError("改写稿完整性检查失败：" + "；".join(last_issues))


def _find_clean(task_id: str) -> str | None:
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "clean")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["storage_path"] if res.data else None


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    params = stage.get("params") or {}
    chosen = params.get("chosen_index")

    if chosen is not None:
        res = (
            db.get_client().table("artifacts")
            .select("storage_path")
            .eq("task_id", task_id)
            .eq("type", "rewrite")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            sp = res.data[0]["storage_path"]
            local = storage.download_artifact(sp, ".json")
            try:
                rw = json.load(open(local, encoding="utf-8"))
                candidates = rw.get("candidates", [])
                idx = int(chosen)
                if idx < 0 or idx >= len(candidates):
                    raise ValueError("选中的改写候选不存在")
                final_text = str(params.get("final_text") or candidates[idx]).strip()
                if not final_text:
                    raise ValueError("最终文案不能为空")
                rw.update({
                    "chosen": idx,
                    "final_text": final_text,
                    "final_length": _text_len(final_text),
                })
                storage.upload_bytes(
                    sp,
                    json.dumps(rw, ensure_ascii=False, indent=2).encode("utf-8"),
                    "application/json",
                )
            finally:
                try:
                    os.remove(local)
                except OSError:
                    pass
            return "done", sp

    cl_path = _find_clean(task_id)
    if not cl_path:
        db.set_stage(stage["id"], "failed", error="未找到清洗产物（clean 未完成？）")
        return "failed", None

    local = storage.download_artifact(cl_path, ".json")
    try:
        cleaned = json.load(open(local, encoding="utf-8"))
        cleaned_text = str(cleaned.get("cleaned") or cleaned.get("raw", "")).strip()
    finally:
        try:
            os.remove(local)
        except OSError:
            pass
    if not cleaned_text:
        db.set_stage(stage["id"], "failed", error="清洗后的文案为空")
        return "failed", None

    candidates, lengths = _generate_candidates(cleaned_text)
    payload = {
        "candidates": candidates,
        "styles": list(_STYLE_KEYS),
        "candidate_lengths": lengths,
        "source_length": _text_len(cleaned_text),
        "complete": True,
        "chosen": None,
        "final_text": None,
    }
    sp = f"{task_id}/rewrite.json"
    storage.upload_bytes(
        sp,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json",
    )
    storage.add_artifact(task_id, "rewrite", "rewrite", sp, meta={
        "candidate_count": len(candidates),
        "candidate_lengths": lengths,
        "source_length": payload["source_length"],
        "model": config.REWRITE_MODEL,
        "complete": True,
    })
    db.set_stage(stage["id"], "needs_review", output_ref=sp)
    return "needs_review", sp
