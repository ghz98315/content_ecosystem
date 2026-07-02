"""④ 改写 rewrite：清洗后文本 → OpenAI 生成多个改写候选 → needs_review 等确认。"""
from __future__ import annotations
import json
import os
from pathlib import Path

import config
import db
import storage

_PROMPT = (Path(__file__).parent.parent / "prompts" / "rewrite.txt").read_text(encoding="utf-8")
_client = None

def _llm():
    global _client
    if not _client:
        _client = config.openai_client()
    return _client


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

    # ── 用户已选定候选 → 直接 done，不再重新生成 ──────────────────────────
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
            return "done", res.data[0]["storage_path"]
        # 找不到 artifact 则继续重新生成（容错）

    cl_path = _find_clean(task_id)
    if not cl_path:
        db.set_stage(stage["id"], "failed", error="未找到清洗产物（clean 未完成？）")
        return "failed", None

    local = storage.download_artifact(cl_path, ".json")
    try:
        cl = json.load(open(local, encoding="utf-8"))
        cleaned_text = cl.get("cleaned") or cl.get("raw", "")
    finally:
        try:
            os.remove(local)
        except OSError:
            pass

    # 生成 3 个候选
    resp = _llm().chat.completions.create(
        model=config.REWRITE_MODEL,
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": cleaned_text},
        ],
        temperature=0.8,
        n=3,
    )
    candidates = [c.message.content.strip() for c in resp.choices]

    data = json.dumps(
        {"candidates": candidates, "chosen": chosen},
        ensure_ascii=False, indent=2,
    ).encode("utf-8")
    sp = f"{task_id}/rewrite.json"
    storage.upload_bytes(sp, data, "application/json")
    storage.add_artifact(task_id, "rewrite", "rewrite", sp, meta={
        "candidate_count": len(candidates),
        "model": config.REWRITE_MODEL,
    })

    # 进评审门：让用户挑一个候选后继续
    db.set_stage(stage["id"], "needs_review", output_ref=sp)
    return "needs_review", sp
