"""⑦ 书籍信息 book：改写文案 → LLM反推书名/作者/国籍 + 生成视频号标题 + 生成CTA文案。

- 优先用 deepseek-v4-flash（按参考实现：便宜且准），没配 key 则 fallback OpenAI
- confidence=low 时进评审门，人工确认书名后继续
"""
from __future__ import annotations
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

import config
import db
import storage
from source_metadata import publication_title, split_source_description

_PROMPT = (Path(__file__).parent.parent / "prompts" / "book.txt").read_text(encoding="utf-8")
_CTA_PROMPT_TMPL = (Path(__file__).parent.parent / "prompts" / "cta.txt").read_text(encoding="utf-8")


def _llm_client():
    if config.DEEPSEEK_API_KEY:
        from openai import OpenAI
        return OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
        ), "deepseek-chat"
    return config.openai_client(), "gpt-4o-mini"


def _ending_context(rewrite_text: str, limit: int = 420) -> str:
    """Keep the final spoken thought visible so CTA is a continuation, not a recap."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", rewrite_text) if part.strip()]
    tail = "\n\n".join(paragraphs[-2:]) if paragraphs else rewrite_text.strip()
    return tail[-limit:]


def _normalized(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text or "")


def _repeats_ending(cta: str, ending_context: str) -> bool:
    """Reject CTA that repeats the close instead of adding the final action."""
    normalized_cta = _normalized(cta)
    normalized_tail = _normalized(ending_context)
    if not normalized_cta or not normalized_tail:
        return False
    similarity = SequenceMatcher(None, normalized_cta, normalized_tail, autojunk=False).ratio()
    return similarity > 0.42 or any(
        phrase in normalized_cta and phrase in normalized_tail
        for phrase in ("较劲", "气坏身体", "护好自己", "放过自己", "别生气")
    )


def _generate_cta(
    client, model: str, rewrite_text: str, book_name: str, author: str,
    dialogue_mode: bool = False,
) -> str:
    ending_context = _ending_context(rewrite_text)
    prompt = _CTA_PROMPT_TMPL.format(
        rewrite=rewrite_text,
        ending_context=ending_context,
        book_name=book_name,
        author=author,
    )
    if dialogue_mode:
        prompt += (
            "\n\n这是双人播客。CTA 会紧接在对话最后一轮之后由主持人朗读；"
            "必须承接最后一句的语气和落点，可用自然的转折或承接短语，不能像突然插入广告。"
        )
    for attempt in range(2):
        correction = "" if not attempt else (
            "\n\n上一版与正文结尾重复。请只写承接后的新 CTA，"
            "不得复述结尾的结论、关键词或句式。"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt + correction}],
            temperature=0.45,
        )
        cta = resp.choices[0].message.content.strip()
        if cta and not _repeats_ending(cta, ending_context):
            return cta
    raise ValueError("CTA 与改写稿结尾重复，未生成可用承接文案")


def _apply_manual_overrides(info: dict, params: dict) -> dict:
    """Keep reviewer-corrected book metadata authoritative over model output."""
    overrides = {
        "manual_book_name": "book_name",
        "manual_book_author": "author",
        "manual_book_nationality": "nationality",
        "manual_cta_text": "cta_text",
    }
    applied = False
    for param_key, info_key in overrides.items():
        value = str(params.get(param_key) or "").strip()
        if value:
            info[info_key] = value
            applied = True
    if applied:
        info["confidence"] = "high"
    return info


def _find_rewrite_text(task_id: str, stage: dict) -> str | None:
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
        return None
    local = storage.download_artifact(res.data[0]["storage_path"], ".json")
    try:
        rw = json.load(open(local, encoding="utf-8"))
    finally:
        try: os.remove(local)
        except OSError: pass
    if rw.get("final_text"):
        return str(rw["final_text"])
    params = stage.get("params") or {}
    raw_idx = params.get("chosen_index")
    idx = raw_idx if raw_idx is not None else rw.get("chosen")
    if idx is None:
        # chosen_index is written to rewrite stage params by the frontend
        db_res = (
            db.get_client().table("stages").select("params")
            .eq("task_id", task_id).eq("kind", "rewrite")
            .limit(1).execute()
        )
        if db_res.data:
            idx = (db_res.data[0].get("params") or {}).get("chosen_index")
    candidates = rw.get("candidates", [])
    if idx is None or not candidates:
        return rw.get("candidates", [""])[0]   # fallback: 第一个候选
    return candidates[int(idx)] if int(idx) < len(candidates) else None


def _dialogue_title_instruction(task_id: str) -> str:
    context = db.get_task_prompt_context(task_id)
    if str(context.get("narration_mode") or "single") != "dual_dialogue":
        return ""
    return (
        "\n\n本任务是双人对谈。title_long 和 title_short 均使用问题、追问、反差或争议式口吻，"
        "让标题体现两个人正在讨论一个反常识问题；不得虚构对话结论，也不得使用收益或疗效承诺。"
    )


def _publication_metadata(task_id: str, info: dict) -> dict:
    context = db.get_task_prompt_context(task_id)
    source_title, fallback_tags = split_source_description(context.get("title"))
    tags = context.get("source_tags")
    if not isinstance(tags, list) or not tags:
        tags = fallback_tags
    candidate = info.get("publish_title") or info.get("title_short") or info.get("theme")
    return {
        "source_title": source_title,
        "source_tags": [str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()],
        "publish_title": publication_title(candidate),
    }


def _sync_book_signal(task_id: str, info: dict, confirmed: bool) -> None:
    title = str(info.get("book_name") or "").strip().strip("《》")
    if not title or title == "未知":
        return
    payload = {
        "task_id": task_id,
        "detected_title": title,
        "detected_author": str(info.get("author") or "").strip() or None,
        "confidence": str(info.get("confidence") or "low"),
        "evidence": "book_stage_final",
        "source_stage": "book",
    }
    if confirmed:
        payload.update({"confirmed_title": title, "confirmed_author": payload["detected_author"]})
    try:
        db.get_client().table("task_book_signals").upsert(payload, on_conflict="task_id").execute()
    except Exception:
        pass


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    params = stage.get("params") or {}

    # 若人工已确认书名(从 params 里拿)
    text = _find_rewrite_text(task_id, stage)
    if not text:
        db.set_stage(stage["id"], "failed", error="未找到改写文案")
        return "failed", None

    client, model = _llm_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _PROMPT + _dialogue_title_instruction(task_id)},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        # 模型没完全遵守 JSON，尽量salvage
        import re
        m = re.search(r"\{.*\}", raw, re.S)
        info = json.loads(m.group(0)) if m else {}

    # 人工覆盖书名
    _apply_manual_overrides(info, params)

    # 生成 CTA：呼应改写稿内容 + 引出书名购买行动
    try:
        info["cta_text"] = _generate_cta(
            client, model,
            rewrite_text=text,
            book_name=info.get("book_name", ""),
            author=info.get("author", ""),
            dialogue_mode=str(db.get_task_prompt_context(task_id).get("narration_mode") or "single") == "dual_dialogue",
        )
    except Exception:
        info["cta_text"] = ""  # CTA 失败不阻断主流程

    # Apply reviewer edits after generation so a manual CTA is authoritative.
    _apply_manual_overrides(info, params)
    info.update(_publication_metadata(task_id, info))
    info["title_short"] = info["publish_title"]
    _sync_book_signal(task_id, info, bool(params.get("book_confirmed") or params.get("manual_book_name")))

    data = json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8")
    sp = f"{task_id}/book.json"
    storage.upload_bytes(sp, data, "application/json")
    storage.add_artifact(task_id, "book", "book", sp, meta={
        "book_name": info.get("book_name"),
        "confidence": info.get("confidence"),
        "model": model,
    })

    # confidence=low → 评审门，让用户手动确认书名
    if not params.get("book_confirmed"):
        db.set_stage(stage["id"], "needs_review",
                     output_ref=sp,
                     error="请在前端确认书名和作者信息后继续")
        return "needs_review", sp

    return "done", sp
