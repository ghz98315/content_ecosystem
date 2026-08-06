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

# ── 语义分镜 ───────────────────────────────────────────────────────────────
_MAJOR_BREAKS = set("。！？!?…")
_MINOR_BREAKS = set("，,；;：:")


def _char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _preferred_cut(text: str, min_chars: int, target_chars: int, max_chars: int) -> int:
    upper = min(max_chars, len(text))
    candidates: list[tuple[int, int]] = []
    for cut in range(min_chars, upper + 1):
        char = text[cut - 1]
        if char in _MAJOR_BREAKS:
            candidates.append((0, cut))
        elif char in _MINOR_BREAKS:
            candidates.append((1, cut))
    if candidates:
        _, cut = min(candidates, key=lambda item: (item[0], abs(item[1] - target_chars)))
        return cut

    cut = min(target_chars, upper)
    # Avoid splitting a book title when a nearby closing bracket fits the range.
    left = text.rfind("《", 0, cut)
    right = text.find("》", cut)
    if left >= 0 and right >= cut:
        after_title = right + 1
        if after_title <= upper:
            cut = after_title
        elif left >= min_chars:
            cut = left
    return max(1, cut)


def _split_storyboard(
    text: str,
    min_chars: int = 24,
    target_chars: int = 28,
    max_chars: int = 32,
) -> list[dict]:
    """Split narration into semantic shots averaging about eight seconds."""
    remaining = re.sub(r"\s+", "", text or "").strip()
    if not remaining:
        return []
    parts: list[str] = []
    while len(remaining) > max_chars:
        cut = _preferred_cut(remaining, min_chars, target_chars, max_chars)
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        if parts and len(remaining) < min_chars:
            combined = parts[-1] + remaining
            if len(combined) <= max_chars + 2:
                parts[-1] = combined
            elif len(combined) >= min_chars * 2:
                split_at = len(combined) // 2
                parts[-1] = combined[:split_at]
                parts.append(combined[split_at:])
            else:
                parts.append(remaining)
        else:
            parts.append(remaining)

    return [
        {
            "index": i,
            "text": part,
            "char_count": _char_count(part),
            "estimated_duration": round(max(1.0, _char_count(part) / 3.5), 2),
            "motion": "zoom_in",
            "transition": "dissolve",
            "transition_duration": 0.5,
        }
        for i, part in enumerate(parts)
    ]

# ── 9宫格生图 ─────────────────────────────────────────────────────────────
_GRID = 3   # 3×3 = 9
_CELL_RATIO = 4 / 3
_GRID_SIZE = config.IMAGE_GRID_SIZE

def _build_grid_prompt(scenes: list[str]) -> str:
    """构建9宫格提示词：1张图包含3×3=9个独立场景，从左到右从上到下编号。"""
    padded = list(scenes[:_GRID * _GRID])
    while len(padded) < _GRID * _GRID:
        padded.append("安静明亮的书房或自然生活空镜，主体居中，画面简洁")
    numbered = "\n".join(f"{i+1}. {_medical_safe(s)}" for i, s in enumerate(padded))
    return (
        "请生成一张横向九宫格总图，将画面平均分为3×3共9个等大的格子，从左到右从上到下对应1-9。"
        "每个格子描绘对应的独立场景，画面风格统一、写意温暖、适合图书养生内容带货。"
        "每格按4:3画面构图，主体完整并保持在格子中央安全区域；格子之间只允许极细分隔线，禁止宽白边、拼贴边框和文字。\n\n"
        f"各格场景描述：\n{numbered}"
    )

def _grid_bounds(length: int) -> list[tuple[int, int]]:
    """Return exact 3-way pixel bounds, distributing remainder pixels safely."""
    return [(round(i * length / _GRID), round((i + 1) * length / _GRID)) for i in range(_GRID)]


def _validate_grid_source(width: int, height: int) -> None:
    """Fail closed when the provider returns a canvas with an unexpected ratio."""
    try:
        expected_width, expected_height = (int(value) for value in _GRID_SIZE.lower().split("x", 1))
    except (TypeError, ValueError):
        raise ValueError(f"无效的 IMAGE_GRID_SIZE 配置：{_GRID_SIZE}") from None
    expected_ratio = expected_width / expected_height
    actual_ratio = width / height if height else 0
    if width < _GRID or height < _GRID or abs(actual_ratio - expected_ratio) > 0.02:
        raise ValueError(
            f"九宫格源图尺寸异常：实际 {width}x{height}，期望比例来自 {_GRID_SIZE}；"
            "已停止切图以避免错误图片进入自动剪辑"
        )


def _crop_to_cell_ratio(piece, ratio: float = _CELL_RATIO):
    """Center-crop one source cell to 4:3 without changing its pixel geometry."""
    width, height = piece.size
    current = width / height
    if abs(current - ratio) < 0.005:
        return piece
    if current > ratio:
        target_width = max(1, round(height * ratio))
        left = max(0, (width - target_width) // 2)
        return piece.crop((left, 0, left + target_width, height))
    target_height = max(1, round(width / ratio))
    top = max(0, (height - target_height) // 2)
    return piece.crop((0, top, width, top + target_height))


def _split_grid(img_bytes: bytes, n: int) -> list[bytes]:
    """切成 n 张4:3小图；边界使用同一组精确像素坐标，避免累计误差。"""
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    _validate_grid_source(w, h)
    x_bounds = _grid_bounds(w)
    y_bounds = _grid_bounds(h)
    pieces = []
    for r in range(_GRID):
        for c in range(_GRID):
            if len(pieces) >= n:
                break
            x0, x1 = x_bounds[c]
            y0, y1 = y_bounds[r]
            piece = _crop_to_cell_ratio(img.crop((x0, y0, x1, y1)))
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
    if rw.get("final_text"):
        return str(rw["final_text"])
    params = stage.get("params") or {}
    raw_idx = params.get("chosen_index")
    if raw_idx is None:
        raw_idx = rw.get("chosen")
    if raw_idx is None:
        # chosen_index is written to the rewrite stage's params by the frontend
        res2 = (
            db.get_client().table("stages").select("params")
            .eq("task_id", task_id).eq("kind", "rewrite")
            .limit(1).execute()
        )
        if res2.data:
            raw_idx = (res2.data[0].get("params") or {}).get("chosen_index")
    candidates = rw.get("candidates", [])
    if raw_idx is None or not candidates:
        return None
    return candidates[int(raw_idx)] if int(raw_idx) < len(candidates) else None


def run(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    text = _find_chosen_text(task_id, stage)
    if not text:
        db.set_stage(stage["id"], "failed",
                     error="未找到选定改写稿（请先完成改写阶段）")
        return "failed", None

    client, image_model = config.image_client()
    storyboard = _split_storyboard(text)
    if not storyboard:
        db.set_stage(stage["id"], "failed", error="最终文案无法生成分镜")
        return "failed", None
    scenes = [shot["text"] for shot in storyboard]
    image_paths: list[str] = []
    meta_list: list[dict] = []

    # 按9个分镜一批生成
    for batch_start in range(0, len(scenes), _GRID * _GRID):
        batch = scenes[batch_start: batch_start + _GRID * _GRID]
        prompt = _build_grid_prompt(batch)

        resp = client.images.generate(
            model=image_model,
            prompt=prompt,
            n=1,
            size=_GRID_SIZE,
            # response_format 不硬编码：gpt-image-* 默认 b64_json，dall-e-3 默认 url
        )
        # gpt-image-2 返回 b64_json；doubao / dall-e-3 返回 url
        item = resp.data[0]
        if getattr(item, "b64_json", None):
            import base64
            raw = base64.b64decode(item.b64_json)
        else:
            raw = _download_image(item.url)

        # Keep the original grid for audit/debugging and to prove the cut source.
        grid_path = f"{task_id}/grid_{batch_start // (_GRID * _GRID):03d}.png"
        storage.upload_bytes(grid_path, raw, "image/png")
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as grid_image:
            grid_size = grid_image.size
        _validate_grid_source(*grid_size)
        storage.add_artifact(task_id, "image", "image_grid", grid_path, meta={
            "source_size": list(grid_size),
            "grid": "3x3",
            "cell_ratio": "4:3",
            "cell_bounds_x": _grid_bounds(grid_size[0]),
            "cell_bounds_y": _grid_bounds(grid_size[1]),
            "validated": True,
        })

        pieces = _split_grid(raw, len(batch))
        for i, piece_bytes in enumerate(pieces):
            idx = batch_start + i
            sp = f"{task_id}/img_{idx:03d}.png"
            storage.upload_bytes(sp, piece_bytes, "image/png")
            shot = storyboard[idx]
            storage.add_artifact(task_id, "image", "image", sp, meta={
                "sentence": shot["text"],
                "index": idx,
                "batch": batch_start // (_GRID * _GRID),
                "char_count": shot["char_count"],
                "estimated_duration": shot["estimated_duration"],
                "motion": shot["motion"],
                "source_grid": grid_path,
                "cell_ratio": "4:3",
            })
            image_paths.append(sp)
            meta_list.append({**shot, "path": sp, "sentence": shot["text"], "source_grid": grid_path})

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
