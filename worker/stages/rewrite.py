"""④ 改写 rewrite：清洗稿 -> 单个轻度改写稿 -> 人工确认 final_text。"""
from __future__ import annotations

import json
import os
import re
import time
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
_MAX_COSYVOICE_INSTRUCTION_UNITS = 100


def _request_rewrite(**kwargs):
    """Retry proxy timeout responses without regenerating a different stage."""
    for attempt in range(config.REWRITE_RETRIES + 1):
        try:
            return _llm().chat.completions.create(**kwargs)
        except Exception as exc:
            if not any(code in str(exc) for code in ("502", "503", "504", "524")) or attempt >= config.REWRITE_RETRIES:
                raise
            time.sleep(min(60, 2 ** (attempt + 1)))


def _llm():
    global _client
    if not _client:
        _client = config.rewrite_client()
    return _client


def _text_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _normalized(text: str) -> str:
    return re.sub(r"[\s，。！？；：、,.!?;:'\"“”‘’（）()《》]+", "", text or "")


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalized(left), _normalized(right)).ratio()


def _dialogue_body(text: str) -> str:
    """Remove speaker labels before comparing a dialogue rewrite with its source script."""
    return re.sub(r"(?m)^\s*(?:主持人|嘉宾)\s*[：:]\s*", "", text or "").strip()


def _longest_common_run(left: str, right: str) -> int:
    """Return the longest verbatim normalized span shared by two scripts."""
    source = _normalized(left)
    rewritten = _normalized(right)
    if not source or not rewritten:
        return 0
    return SequenceMatcher(None, source, rewritten, autojunk=False).find_longest_match(
        0, len(source), 0, len(rewritten)
    ).size


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


def _instruction_units(value: str) -> int:
    """DashScope counts CJK characters as two instruction characters."""
    return sum(2 if "\u4e00" <= char <= "\u9fff" else 1 for char in value)


def _dialogue_delivery_plan(raw: str, text: str) -> list[dict] | None:
    """Validate editable text and machine-readable podcast direction stay aligned."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    plan = payload.get("delivery_plan") if isinstance(payload, dict) else None
    if not isinstance(plan, list) or not plan:
        return None
    normalized: list[dict] = []
    lines: list[str] = []
    for item in plan:
        if not isinstance(item, dict):
            return None
        speaker = str(item.get("speaker") or "").strip()
        turn_text = str(item.get("text") or "").strip()
        instruction = str(item.get("instruction") or "").strip()
        if speaker not in {"主持人", "嘉宾"} or not turn_text or not instruction:
            return None
        if _instruction_units(instruction) > _MAX_COSYVOICE_INSTRUCTION_UNITS:
            return None
        normalized.append({"speaker": speaker, "text": turn_text, "instruction": instruction})
        lines.append(f"{speaker}：{turn_text}")
    expected = "\n".join(lines)
    if re.sub(r"\s+", "", expected) != re.sub(r"\s+", "", text or ""):
        return None
    return normalized


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
    cta_original = str(payload.get("cta_original") or "").strip() if isinstance(payload, dict) else ""
    cta_revised = str(payload.get("cta_revised") or "").strip() if isinstance(payload, dict) else ""
    cta_range = payload.get("cta_range") if isinstance(payload, dict) else None
    if not isinstance(cta_range, dict):
        cta_range = {}
    book_title = str(payload.get("book_title") or "").strip() if isinstance(payload, dict) else ""
    book_title_source = str(payload.get("book_title_source") or ("reference_copy" if book_title else "absent")).strip()
    return {
        "hook": hook,
        "hook_strategy": strategy or "counter_intuitive",
        "paragraphs": paragraphs,
        "delivery_plan": _dialogue_delivery_plan(raw, text),
        "cta_original": cta_original,
        "cta_revised": cta_revised,
        "cta_range": {
            "start": max(0, int(cta_range.get("start") or 0)),
            "end": max(0, int(cta_range.get("end") or 0)),
        },
        "book_title": book_title,
        "book_title_source": book_title_source if book_title else "absent",
    }


def _dialogue_structure_issues(text: str) -> list[str]:
    """Keep podcast scripts conversational while leaving domain compliance unchanged."""
    turns: list[tuple[str, str]] = []
    for line in re.split(r"\n+", text or ""):
        match = re.match(r"^(主持人|嘉宾)\s*[：:]\s*(.+)$", line.strip())
        if not match:
            return ["双人播客每段必须以“主持人：”或“嘉宾：”开头"]
        content = match.group(2).strip()
        if len(re.sub(r"\s+", "", content)) < 6:
            return ["双人播客单轮发言过短，无法形成自然问答"]
        if len(re.sub(r"\s+", "", content)) > 90:
            return ["双人播客单轮发言过长，应控制在 90 字以内"]
        turns.append((match.group(1), content))
    if len(turns) < 4:
        return ["双人播客至少需要 4 个交替轮次"]
    if {speaker for speaker, _ in turns} != {"主持人", "嘉宾"}:
        return ["双人播客必须同时包含主持人和嘉宾"]
    if turns[0][0] != "主持人" or "?" not in turns[0][1] and "？" not in turns[0][1]:
        return ["双人播客首轮必须由主持人以问题或反差钩子开启"]
    if not any(speaker == "主持人" and ("?" in content or "？" in content) for speaker, content in turns):
        return ["主持人至少需要提出一个明确问题"]
    same_speaker_turns = 1
    for previous, current in zip(turns, turns[1:]):
        same_speaker_turns = same_speaker_turns + 1 if previous[0] == current[0] else 1
        if same_speaker_turns > 2:
            return ["双人播客同一角色不能连续超过 2 轮，应增加自然承接"]
    return []


def _candidate_issues(
    candidates: list[str],
    source: str,
    finish_reason: str | None,
    mode: str = "initial_dedup",
    category: str = "health",
    narration_mode: str = "single",
) -> list[str]:
    issues: list[str] = []
    if finish_reason == "length":
        issues.append("模型输出达到长度上限")
    if len(candidates) != 1:
        issues.append("未生成一个完整改写稿")
        return issues

    source_len = _text_len(source)
    tolerance = 0.15 if mode == "repost_dedup" else 0.25
    min_len = max(40, round(source_len * (1 - tolerance)))
    max_len = max(min_len + 20, round(source_len * (1 + tolerance)))
    for i, text in enumerate(candidates):
        if narration_mode == "dual_dialogue":
            issues.extend(_dialogue_structure_issues(text))
        comparison_text = _dialogue_body(text) if narration_mode == "dual_dialogue" else text
        length = _text_len(comparison_text)
        if narration_mode != "dual_dialogue":
            if length < min_len:
                issues.append(f"改写稿过短（{length}/{source_len} 字）")
            if length > max_len:
                issues.append(f"改写稿明显超出原文长度（{length}/{source_len} 字）")
        if re.search(r"(?:未完待续|请继续|继续输出|\.\.\.|……)\s*$", text):
            issues.append("改写稿疑似被截断")
        if text.rstrip().endswith(("，", ",", "：", ":", "；", ";", "、")):
            issues.append("改写稿结尾不完整")
        if narration_mode != "dual_dialogue" and _similarity(source, comparison_text) < 0.40:
            issues.append("改写幅度过大，未保持原文主体")
        for title in re.findall(r"《([^》]+)》", source):
            if f"《{title}》" not in text:
                issues.append(f"未完整保留书名《{title}》")
    return issues


def _candidate_warnings(
    text: str,
    source: str,
    mode: str = "initial_dedup",
    category: str = "health",
    narration_mode: str = "single",
) -> list[str]:
    """Expose style drift for review without blocking an otherwise complete draft."""
    if narration_mode == "dual_dialogue":
        return []
    warnings: list[str] = []
    if category == "health" and mode == "initial_dedup":
        similarity = _similarity(source, text)
        if similarity > 0.72:
            warnings.append(f"健康首发改写与原稿较近（相似度 {similarity:.2f}，建议不高于 0.72）")
        common_run = _longest_common_run(source, text)
        if common_run > 16:
            warnings.append(f"健康首发改写存在较长原句复用（连续 {common_run} 个有效字符）")
    if _similarity(source[:50], text[:50]) < 0.35:
        warnings.append("开头钩子改动较大")
    if _similarity(source[-50:], text[-50:]) < 0.35:
        warnings.append("结尾改动较大")
    return warnings


def _rewrite_prompt_kind(category: str, mode: str, narration_mode: str) -> str:
    prompt_kind = rewrite_prompt_kind(mode)
    if narration_mode == "dual_dialogue" and category == "health":
        return f"dual_dialogue_{prompt_kind}"
    return prompt_kind


def _generate_candidates(
    source: str,
    context: dict[str, str],
    rewrite_notes: str = "",
    mode: str = "initial_dedup",
    narration_mode: str = "single",
) -> tuple[list[str], list[int], dict]:
    source_len = _text_len(source)
    prompt_kind = _rewrite_prompt_kind(context["category"], mode, narration_mode)
    prompt = load_prompt(context["category"], prompt_kind)
    source_label = "首发版本最终确认稿" if mode == "repost_dedup" else "已清洗正文"
    tolerance_label = "8%" if mode == "repost_dedup" else "12%"
    terms = "、".join(protected_terms(source)) or "无额外词语"
    last_issues: list[str] = []
    attempts = 1
    for attempt in range(attempts):
        correction = ""
        if attempt:
            correction = "\n上一次输出不合格：" + "；".join(last_issues) + "。请完整重写并严格输出 JSON。"
            if narration_mode == "dual_dialogue":
                correction += (
                    "每轮正文控制在 12 到 70 字，绝不能超过 90 字；长回答必须拆成主持人追问和嘉宾续答。"
                    "角色标签不计入正文长度。保持原文开头钩子的核心反差、结尾核心语义、全部事实和书名，"
                    "只调整问答组织，不得新增原文没有的事实。"
                )
        if narration_mode == "dual_dialogue":
            temperature = (0.55, 0.40, 0.25)[attempt]
        else:
            temperature = 0.35 if mode == "repost_dedup" else 0.7
        resp = _request_rewrite(
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
                        "历史类规则：若原文存在 CTA，只允许在 cta_revised 中调整语序和口语表达，不得新增卖点、优惠、承诺或购买引导；若原文没有 CTA，cta_original 和 cta_revised 必须为空。若原文明确出现书名则保留，否则 book_title 必须为空且 book_title_source=absent。\n"
                        f"原文有效字数约 {source_len} 字。目标差异控制在 {tolerance_label} 以内。"
                        + (
                            f"双人播客必须保留开头钩子核心语义，可参考原文前 120 字：{source[:120]}；"
                            f"结尾收束可参考原文后 120 字：{source[-120:]}。"
                            if narration_mode == "dual_dialogue" else ""
                        )
                        + f"{correction}\n\n待处理的{source_label}：\n{source}"
                    ),
                },
            ],
            temperature=temperature,
            max_tokens=config.REWRITE_MAX_TOKENS if narration_mode == "dual_dialogue" else None,
            response_format={"type": "json_object"},
        )
        choice = resp.choices[0]
        raw = (choice.message.content or "").strip()
        candidates = _parse_candidates(raw)
        structure = _rewrite_structure(raw, candidates[0]) if candidates else {}
        last_issues = _candidate_issues(
            candidates, source, getattr(choice, "finish_reason", None), mode, context["category"], narration_mode
        )
        if narration_mode == "dual_dialogue" and not structure.get("delivery_plan"):
            last_issues.append("双人播客未输出与对话稿一致的逐轮语气指令")
        if candidates:
            structure["quality_warnings"] = last_issues + _candidate_warnings(
                candidates[0], source, mode, context["category"], narration_mode
            )
            return (
                candidates,
                [_text_len(text) for text in candidates],
                structure,
            )
    raise ValueError("改写模型未返回可解析的正文")


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
                plan = rw.get("delivery_plan")
                if (
                    str(task_context.get("narration_mode") or params.get("narration_mode") or "single") == "dual_dialogue"
                    and final_text == str(candidates[idx]).strip()
                    and isinstance(plan, list)
                ):
                    rw["final_delivery_plan"] = plan
                else:
                    rw.pop("final_delivery_plan", None)
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
        rewrite_notes = (rewrite_notes + "\n改为双人播客对话：每段以“主持人：”或“嘉宾：”开头，嘉宾可连续展开；保留事实边界，首段仍须有反差、反常识或悬念钩子。不要增加角色设定以外的事实。 ").strip()
    candidates, lengths, structure = _generate_candidates(
        source,
        context,
        rewrite_notes,
        mode,
        narration_mode,
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
        "delivery_plan": structure.get("delivery_plan"),
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
