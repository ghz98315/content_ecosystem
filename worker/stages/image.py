"""⑥ 生图 image：改写文案按句切片 → gpt-image 9宫格批量生图 → Pillow切割 → 上传各分图。

9宫格省钱：一次 API 请求生成包含9个场景的大图，本地切割，成本降约90%。
医疗安全：敏感病症描述转为日常生活隐喻，避免生成病房/ICU画面被平台限流。
"""
from __future__ import annotations
import io
import json
import math
import os
import re
import urllib.request

import config
import db
import storage

# ── 医疗安全关键词 → 生活隐喻 ──────────────────────────────────────────────
_MEDICAL_MAP = {
    "糖尿病": "日常饮食管理的生活场景",
    "癌症": "珍惜生命、关注健康的日常场景",
    "肿瘤": "关注身体信号、调整生活方式的场景",
    "肾衰": "保护肾脏健康的日常生活场景",
    "心脏病": "关爱心脏健康的日常生活场景",
    "高血压": "舒缓压力的平静日常生活场景",
    "痛风": "清淡饮食健康生活的日常场景",
    "肝硬化": "保护肝脏、健康生活的日常场景",
    "中风": "预防意外、关爱老人的温馨家庭场景",
    "ICU": "温暖的家庭关怀场景",
    "病房": "明亮舒适的居家养生场景",
    "手术": "健康检查与积极生活态度的场景",
}

def _medical_safe(sentence: str) -> str:
    """把敏感病症替换为生活隐喻，避免平台限流。"""
    desc = sentence
    for kw, replace in _MEDICAL_MAP.items():
        if kw in desc:
            desc = replace
            break
    return desc

# ── 文案切句 ───────────────────────────────────────────────────────────────
_SPLIT_RE = re.compile(r"(?<=[。！？.!?…])\s*")

def _split_sentences(text: str) -> list[str]:
    sents = [s.strip() for s in _SPLIT_RE.split(text) if s.strip()]
    return sents or [text]

# ── 9宫格生图 ─────────────────────────────────────────────────────────────
_GRID = 3   # 3×3 = 9
_IMG_SIZE = "1024x1024"   # gpt-image 支持的方形尺寸

def _build_grid_prompt(scenes: list[str]) -> str:
    """构建9宫格提示词：1张图包含3×3=9个独立场景，从左到右从上到下编号。"""
    numbered = "\n".join(f"{i+1}. {_medical_safe(s)}" for i, s in enumerate(scenes))
    return (
        "请生成一张图片，将画面平均分为3×3共9个等大的格子，从左到右从上到下编号1-9。"
        "每个格子描绘对应的独立场景，画面风格统一、写意温暖、适合图书养生内容带货。"
        "格子之间无边框无文字，每格仅含画面。\n\n"
        f"各格场景描述：\n{numbered}"
    )

def _split_grid(img_bytes: bytes, n: int) -> list[bytes]:
    """把大图切成 n 张（最多9张），返回 PNG bytes 列表。"""
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    cols = rows = _GRID
    cw, ch = w // cols, h // rows
    pieces = []
    for r in range(rows):
        for c in range(cols):
            if len(pieces) >= n:
                break
            box = (c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)
            piece = img.crop(box)
            buf = io.BytesIO()
            piece.save(buf, format="PNG")
            pieces.append(buf.getvalue())
    return pieces

def _download_image(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

# ── Stage ─────────────────────────────────────────────────────────────────
def _find_chosen_text(task_id: str, stage: dict) -> str | None:
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
    params = stage.get("params") or {}
    raw_idx = params.get("chosen_index")
    idx = raw_idx if raw_idx is not None else rw.get("chosen")
    candidates = rw.get("candidates", [])
    if idx is None or not candidates:
        return None
    return candidates[int(idx)] if int(idx) < len(candidates) else None


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    text = _find_chosen_text(task_id, stage)
    if not text:
        db.set_stage(stage["id"], "failed",
                     error="未找到选定改写稿（请先完成改写阶段）")
        return "failed", None

    client, image_model = config.image_client()
    sentences = _split_sentences(text)
    image_paths: list[str] = []
    meta_list: list[dict] = []

    # 按9句一批生成
    for batch_start in range(0, len(sentences), _GRID * _GRID):
        batch = sentences[batch_start: batch_start + _GRID * _GRID]
        prompt = _build_grid_prompt(batch)

        resp = client.images.generate(
            model=image_model,
            prompt=prompt,
            n=1,
            size=_IMG_SIZE,
            response_format="b64_json",   # gpt-image-2 只返回 b64_json
        )
        import base64
        raw = base64.b64decode(resp.data[0].b64_json)

        pieces = _split_grid(raw, len(batch))
        for i, piece_bytes in enumerate(pieces):
            idx = batch_start + i
            sp = f"{task_id}/img_{idx:03d}.png"
            storage.upload_bytes(sp, piece_bytes, "image/png")
            storage.add_artifact(task_id, "image", "image", sp, meta={
                "sentence": sentences[idx],
                "index": idx,
                "batch": batch_start // (_GRID * _GRID),
            })
            image_paths.append(sp)
            meta_list.append({"index": idx, "path": sp, "sentence": sentences[idx]})

    # 存索引文件
    sp_idx = f"{task_id}/images_index.json"
    storage.upload_bytes(
        sp_idx,
        json.dumps(meta_list, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json",
    )
    storage.add_artifact(task_id, "image", "image_index", sp_idx, meta={
        "total": len(image_paths),
    })
    return "done", sp_idx
