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
from prompt_profiles import (
    author_name,
    derive_keyword,
    load_prompt,
    normalize_category,
    protected_terms,
    rewrite_prompt_kind,
)

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


def _rewrite_structure(raw: str, text: str) -> dict:
    """Optional presentation metadata; the plain text contract stays canonical."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        payload = {}
    hook = str(payload.get("hook") or "").strip() if isinstance(payload, dict) else ""
    strategy = str(payload.get("hook_strategy") or "").strip() if isinstance(payload, dict) else ""
    paragraphs = payload.get("paragraphs") if isinstance(payload, dict) else None
    if not isinstance(paragraphs, list) or not all(isinstance(item, str) and item.strip() for item in paragraphs):
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n|\n", text) if item.strip()]
    if not hook:
        hook = paragraphs[0] if paragraphs else text[:120]
    return {"hook": hook, "hook_strategy": strategy or "counter_intuitive", "paragraphs": paragraphs}


def _candidate_issues(
    candidates: list[str],
    source: str,
    finish_reason: str | None,
    mode: str = "initial_dedup",
) -> list[str]:
    issues: list[str] = []
    if finish_reason == "length":
        issues.append("模型输出达到长度上限")
    if len(candidates) != 1:
        issues.append("未生成一个完整改写稿")
        return issues

    source_len = _text_len(source)
    tolerance = 0.08 if mode == "repost_dedup" else 0.12
    min_len = max(40, round(source_len * (1 - tolerance)))
    max_len = max(min_len + 20, round(source_len * (1 + tolerance)))
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


def _generate_candidates(
    source: str,
    context: dict[str, str],
    rewrite_notes: str = "",
    mode: str = "initial_dedup",
) -> tuple[list[str], list[int], dict]:
    source_len = _text_len(source)
    prompt = load_prompt(context["category"], rewrite_prompt_kind(mode))
    source_label = "首发版本最终确认稿" if mode == "repost_dedup" else "已清洗正文"
    tolerance_label = "8%" if mode == "repost_dedup" else "12%"
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
                        f"原文有效字数约 {source_len} 字。目标差异控制在 {tolerance_label} 以内。"
                        f"{correction}\n\n待处理的{source_label}：\n{source}"
                    ),
                },
            ],
            temperature=0.35 if mode == "repost_dedup" else 0.7,
            response_format={"type": "json_object"},
        )
        choice = resp.choices[0]
        raw = (choice.message.content or "").strip()
        candidates = _parse_candidates(raw)
        last_issues = _candidate_issues(
            candidates, source, getattr(choice, "finish_reason", None), mode
        )
        if not last_issues:
            return (
                candidates,
                [_text_len(text) for text in candidates],
                _rewrite_structure(raw, candidates[0]),
            )
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
    stage_res = (
        db.get_client().table("stages")
        .select("params")
        .eq("task_id", task_id)
        .eq("kind", "clean")
        .limit(1)
        .execute()
    )
    stage_data = stage_res.data if isinstance(stage_res.data, list) else []
    params = (stage_data[0].get("params") or {}) if stage_data and isinstance(stage_data[0], dict) else {}
    if isinstance(params, dict) and params.get("manual_clean_confirmed") and params.get("manual_clean_text"):
        return str(params["manual_clean_text"]).strip()

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
        "rewrite_mode": str(task.get("rewrite_mode") or "initial_dedup"),
        "source_task_id": str(task.get("source_task_id") or ""),
    }


def _load_final_text(task_id: str) -> str:
    res = (
        db.get_client().table("artifacts")
        .select("storage_path")
        .eq("task_id", task_id)
        .eq("type", "rewrite")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return ""
    local = storage.download_artifact(res.data[0]["storage_path"], ".json")
    try:
        payload = json.load(open(local, encoding="utf-8"))
        return str(payload.get("final_text") or "").strip()
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def _upload_rewrite(path: str, payload: dict) -> None:
    storage.upload_bytes(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json",
    )


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    # A reviewer can confirm while a worker is polling. Reload the stage
    # instead of relying on the pre-claim snapshot returned by PostgREST.
    latest = db.retry(
        lambda: db.get_client().table("stages")
        .select("params")
        .eq("id", stage["id"])
        .single()
        .execute()
    ).data or {}
    params = latest.get("params") or stage.get("params") or {}
    chosen = params.get("chosen_index")
    task_context = db.get_task_prompt_context(task_id)
    mode = str(task_context.get("rewrite_mode") or params.get("rewrite_mode") or "initial_dedup")
    source_task_id = str(task_context.get("source_task_id") or params.get("source_task_id") or "")
    source = _load_final_text(source_task_id) if mode == "repost_dedup" else _load_clean_text(task_id)
    if not source:
        message = "未找到首发最终文案（源任务改写阶段未完成）" if mode == "repost_dedup" else "未找到清洗产物（clean 未完成？）"
        db.set_stage(stage["id"], "failed", error=message)
        return "failed", None
    context = _task_context(task_id, source)
    narration_mode = str(params.get("narration_mode") or "single")

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
                with open(local, encoding="utf-8") as handle:
                    rw = json.load(handle)
                candidates = rw.get("candidates", [])
                idx = int(chosen)
                if idx < 0 or idx >= len(candidates):
                    raise ValueError("改写稿不存在")
                final_text = str(params.get("final_text") or candidates[idx]).strip()
                if not final_text:
                    raise ValueError("最终文案不能为空")
                rw.update({
                    "chosen": idx,
                    "final_text": final_text,
                    "final_length": _text_len(final_text),
                })
                _upload_rewrite(sp, rw)
            finally:
                try:
                    os.remove(local)
                except OSError:
                    pass
            db.get_client().table("stages").update({"error": None}).eq("id", stage["id"]).execute()
            return "done", sp

    rewrite_notes = str(params.get("rewrite_notes") or "").strip()
    if narration_mode == "dual_dialogue":
        rewrite_notes = (rewrite_notes + "\n改为双人播客对话：使用“主持人：”和“嘉宾：”交替开头；保留事实边界，首段仍须有反差、反常识或悬念钩子。不要增加角色设定以外的事实。 ").strip()
    candidates, lengths, structure = _generate_candidates(
        source,
        context,
        rewrite_notes,
        mode,
    )
    report = compliance.check_text(
        _llm(), config.REWRITE_MODEL, context["category"], candidates[0], context
    )
    payload = {
        "candidates": candidates,
        "styles": [mode],
        "candidate_lengths": lengths,
        "source_length": _text_len(source),
        "complete": True,
        "chosen": None,
        "final_text": None,
        "content_category": context["category"],
        "rewrite_mode": mode,
        "narration_mode": narration_mode,
        "source_task_id": source_task_id or None,
        "compliance": report,
        **structure,
    }
    sp = f"{task_id}/rewrite.json"
    _upload_rewrite(sp, payload)
    storage.add_artifact(task_id, "rewrite", "rewrite", sp, meta={
        "candidate_count": len(candidates),
        "candidate_lengths": lengths,
        "source_length": payload["source_length"],
        "rewrite_mode": mode,
        "source_task_id": source_task_id or None,
        "model": config.REWRITE_MODEL,
        "complete": True,
        "content_category": context["category"],
        "compliance_status": report["status"],
        "hook_strategy": structure["hook_strategy"],
    })
    db.get_client().table("stages").update({
        "status": "needs_review",
        "output_ref": sp,
        "error": "存在高风险合规项，请修改后重新确认" if report["status"] == "blocked" else None,
    }).eq("id", stage["id"]).execute()
    return "needs_review", sp
