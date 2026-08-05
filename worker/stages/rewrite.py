"""④ 改写 rewrite：清洗稿 -> 单个轻度改写稿 -> 人工确认 final_text。"""
from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher

import config
import compliance
import db
import storage
from prompt_profiles import author_name, derive_keyword, load_prompt, normalize_category, protected_terms

_CAND_RE = re.compile(r"【候选[ABC]】\s*(.*?)(?=【候选[ABC]】|$)", re.DOTALL)
_client = None


def _llm():
    global _client
    if not _client:
        _client = config.openai_client()
    return _client


def _text_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _normalized(text: str) -> str:
    return re.sub(r"[\s，。！？；：、,.!?;:'\"“”‘’（）()《》]+", "", text or "")


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalized(left), _normalized(right)).ratio()


def _parse_candidates(raw: str) -> list[str]:
    """Parse a new single draft while retaining legacy artifact compatibility."""
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and str(payload.get("text", "")).strip():
            return [str(payload["text"]).strip()]
        items = payload.get("candidates", []) if isinstance(payload, dict) else []
        parsed = [
            str(item.get("text", "")).strip() if isinstance(item, dict) else str(item).strip()
            for item in items
        ]
        if parsed and all(parsed):
            return parsed
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    matches = [m.strip() for m in _CAND_RE.findall(raw)]
    return matches if matches else []


def _candidate_issues(candidates: list[str], source: str, finish_reason: str | None) -> list[str]:
    issues: list[str] = []
    if finish_reason == "length":
        issues.append("模型输出达到长度上限")
    if len(candidates) != 1:
        issues.append("未生成一个完整改写稿")
        return issues

    source_len = _text_len(source)
    min_len = max(40, round(source_len * 0.88))
    max_len = max(min_len + 20, round(source_len * 1.12))
    for i, text in enumerate(candidates):
        length = _text_len(text)
        if length < min_len:
            issues.append(f"改写稿过短（{length}/{source_len} 字）")
        if length > max_len:
            issues.append(f"改写稿明显超出原文长度（{length}/{source_len} 字）")
        if re.search(r"(?:未完待续|请继续|继续输出|\.\.\.|……)\s*$", text):
            issues.append("改写稿疑似被截断")
        if text.rstrip().endswith(("，", ",", "：", ":", "；", ";", "、")):
            issues.append("改写稿结尾不完整")
        if _similarity(source, text) < 0.4:
            issues.append("改写幅度过大，未保持原文主体")
        if _similarity(source[:50], text[:50]) < 0.35:
            issues.append("开头钩子改动过大")
        if _similarity(source[-50:], text[-50:]) < 0.35:
            issues.append("结尾改动过大")
        for title in re.findall(r"《([^》]+)》", source):
            if f"《{title}》" not in text:
                issues.append(f"未完整保留书名《{title}》")
    return issues


def _generate_candidates(source: str, context: dict[str, str], rewrite_notes: str = "") -> tuple[list[str], list[int]]:
    source_len = _text_len(source)
    prompt = load_prompt(context["category"], "rewrite")
    terms = "、".join(protected_terms(source)) or "无额外词语"
    last_issues: list[str] = []
    for attempt in range(2):
        correction = ""
        if attempt:
            correction = "\n上一次输出不合格：" + "；".join(last_issues) + "。请完整重写并严格输出 JSON。"
        resp = _llm().chat.completions.create(
            model=config.REWRITE_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"主题关键词：{context['keyword']}\n"
                        f"原视频标题：{context['title']}\n"
                        f"原作者标识：{context['author']}\n"
                        f"补充要求：{rewrite_notes or '无'}\n"
                        f"必须原样保留的词：{terms}\n"
                        f"原文有效字数约 {source_len} 字。目标差异控制在 8% 以内。"
                        f"{correction}\n\n待改写的已清洗正文：\n{source}"
                    ),
                },
            ],
            temperature=0.7,
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


def _load_clean_text(task_id: str) -> str:
    cl_path = _find_clean(task_id)
    if not cl_path:
        return ""
    local = storage.download_artifact(cl_path, ".json")
    try:
        cleaned = json.load(open(local, encoding="utf-8"))
        return str(cleaned.get("cleaned") or cleaned.get("raw", "")).strip()
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def _task_context(task_id: str, source: str) -> dict[str, str]:
    task = db.get_task_prompt_context(task_id)
    category = normalize_category(task.get("content_category"))
    title = str(task.get("title") or "")
    return {
        "category": category,
        "title": title,
        "author": author_name(task.get("author")),
        "keyword": derive_keyword(title, source),
    }


def _upload_rewrite(path: str, payload: dict) -> None:
    storage.upload_bytes(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json",
    )


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    params = stage.get("params") or {}
    chosen = params.get("chosen_index")
    cleaned_text = _load_clean_text(task_id)
    if not cleaned_text:
        db.set_stage(stage["id"], "failed", error="未找到清洗产物（clean 未完成？）")
        return "failed", None
    context = _task_context(task_id, cleaned_text)

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
                    raise ValueError("改写稿不存在")
                final_text = str(params.get("final_text") or candidates[idx]).strip()
                if not final_text:
                    raise ValueError("最终文案不能为空")
                report = compliance.check_text(
                    _llm(), config.REWRITE_MODEL, context["category"], final_text, context
                )
                rw.update({
                    "chosen": idx,
                    "final_text": final_text,
                    "final_length": _text_len(final_text),
                    "compliance": report,
                })
                _upload_rewrite(sp, rw)
            finally:
                try:
                    os.remove(local)
                except OSError:
                    pass
            if report["status"] == "blocked":
                db.set_stage(stage["id"], "needs_review", output_ref=sp, error="存在高风险合规项，请修改后重新确认")
                return "needs_review", sp
            db.get_client().table("stages").update({"error": None}).eq("id", stage["id"]).execute()
            return "done", sp

    candidates, lengths = _generate_candidates(
        cleaned_text,
        context,
        str(params.get("rewrite_notes") or "").strip(),
    )
    report = compliance.check_text(
        _llm(), config.REWRITE_MODEL, context["category"], candidates[0], context
    )
    payload = {
        "candidates": candidates,
        "styles": ["light_rewrite"],
        "candidate_lengths": lengths,
        "source_length": _text_len(cleaned_text),
        "complete": True,
        "chosen": None,
        "final_text": None,
        "content_category": context["category"],
        "compliance": report,
    }
    sp = f"{task_id}/rewrite.json"
    _upload_rewrite(sp, payload)
    storage.add_artifact(task_id, "rewrite", "rewrite", sp, meta={
        "candidate_count": len(candidates),
        "candidate_lengths": lengths,
        "source_length": payload["source_length"],
        "model": config.REWRITE_MODEL,
        "complete": True,
        "content_category": context["category"],
        "compliance_status": report["status"],
    })
    db.get_client().table("stages").update({
        "status": "needs_review",
        "output_ref": sp,
        "error": "存在高风险合规项，请修改后重新确认" if report["status"] == "blocked" else None,
    }).eq("id", stage["id"]).execute()
    return "needs_review", sp
