"""⑦ 书籍信息 book：改写文案 → LLM反推书名/作者/国籍 + 生成视频号标题 + 生成CTA文案。

- 优先用 deepseek-v4-flash（按参考实现：便宜且准），没配 key 则 fallback OpenAI
- confidence=low 时进评审门，人工确认书名后继续
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import config
import db
import storage

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


def _generate_cta(client, model: str, rewrite_text: str, book_name: str, author: str) -> str:
    prompt = _CTA_PROMPT_TMPL.format(
        rewrite=rewrite_text,
        book_name=book_name,
        author=author,
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


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
            {"role": "system", "content": _PROMPT},
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
        )
    except Exception:
        info["cta_text"] = ""  # CTA 失败不阻断主流程

    # Apply reviewer edits after generation so a manual CTA is authoritative.
    _apply_manual_overrides(info, params)

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
