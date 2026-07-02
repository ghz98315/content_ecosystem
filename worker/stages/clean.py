"""③ 清洗 clean：原始逐字稿 → OpenAI 修错字/断句/数字转中文/删引导/换书名。"""
from __future__ import annotations
import json
import os
from pathlib import Path

import config
import db
import storage

_PROMPT = (Path(__file__).parent.parent / "prompts" / "clean.txt").read_text(encoding="utf-8")
_client = None

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

    resp = _llm().chat.completions.create(
        model=config.CLEAN_MODEL,
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": raw_text},
        ],
        temperature=0.2,
    )
    cleaned = resp.choices[0].message.content.strip()

    data = json.dumps(
        {"raw": raw_text, "cleaned": cleaned},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    sp = f"{task_id}/clean.json"
    storage.upload_bytes(sp, data, "application/json")
    storage.add_artifact(task_id, "clean", "clean", sp, meta={
        "raw_chars": len(raw_text),
        "clean_chars": len(cleaned),
        "model": config.CLEAN_MODEL,
    })
    return "done", sp
