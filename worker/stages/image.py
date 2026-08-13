"""⑥ 生图 image：改写文案按句切片 → gpt-image 9宫格批量生图 → Pillow切割 → 上传各分图。

9宫格省钱：一次 API 请求生成包含9个场景的大图，本地切割，成本降约90%。
医疗安全：敏感病症描述转为日常生活隐喻，避免生成病房/ICU画面被平台限流。
"""
from __future__ import annotations
import io
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request

import httpx

import config
import db
import storage
from narration import clean_tts_text

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
    "医院": "明亮舒适的居家生活场景",
    "器官": "日常生活方式的抽象隐喻场景",
    "伤口": "温和克制的日常生活场景",
    "监护仪": "安静的居家关怀场景",
    "心脏": "关爱生活状态的温馨家庭场景",
    "肾脏": "均衡饮食与规律生活的场景",
    "肝脏": "均衡饮食与规律生活的场景",
    "胃": "清淡饮食与舒适生活的场景",
    "手术": "健康检查与积极生活态度的场景",
    "疾病": "关注生活状态的日常场景",
    "症状": "关注身体信号的日常场景",
    "治疗": "积极生活方式的日常场景",
    "药物": "日常健康管理的生活场景",
    "用药": "日常健康管理的生活场景",
    "服药": "日常健康管理的生活场景",
    "诊断": "了解身体状态的日常场景",
    "处方": "日常健康管理的生活场景",
    "化疗": "温暖家庭关怀的生活场景",
    "注射": "健康检查与积极生活态度的场景",
    "降压": "舒缓压力的平静日常生活场景",
    "降糖": "清淡饮食健康生活的日常场景",
    "减肥药": "均衡饮食与规律生活的日常场景",
}

_SELF_HARM_MAP = {
    "自我伤害": "情绪支持与日常陪伴的温暖生活场景",
    "自残": "情绪支持与日常陪伴的温暖生活场景",
    "自伤": "情绪支持与日常陪伴的温暖生活场景",
    "自杀": "珍惜生命、获得支持与温暖陪伴的生活场景",
    "轻生": "珍惜生命、获得支持与温暖陪伴的生活场景",
    "寻死": "珍惜生命、获得支持与温暖陪伴的生活场景",
    "结束生命": "珍惜生命、获得支持与温暖陪伴的生活场景",
    "割腕": "安静陪伴、舒缓情绪的居家生活场景",
    "跳楼": "安静陪伴、舒缓情绪的居家生活场景",
}

_UNIFORM_MAP = {
    "警察": "社区里平和交流的普通成年人",
    "民警": "社区里平和交流的普通成年人",
    "警官": "社区里平和交流的普通成年人",
    "制服": "简洁得体的日常便装",
    "警服": "简洁得体的日常便装",
    "军装": "简洁得体的日常便装",
    "制帽": "自然整洁的日常发型",
    "警帽": "自然整洁的日常发型",
    "徽章": "简洁无标识的衣物细节",
    "执法": "理性沟通与生活秩序的抽象场景",
    "巡逻": "安静散步与社区关怀场景",
}

def _medical_safe(sentence: str) -> str:
    """把敏感病症替换为生活隐喻，避免平台限流。"""
    desc = sentence
    for kw in sorted(_MEDICAL_MAP, key=len, reverse=True):
        if kw in desc:
            desc = desc.replace(kw, _MEDICAL_MAP[kw])
    for kw in sorted(_SELF_HARM_MAP, key=len, reverse=True):
        if kw in desc:
            desc = desc.replace(kw, _SELF_HARM_MAP[kw])
    for kw in sorted(_UNIFORM_MAP, key=len, reverse=True):
        if kw in desc:
            desc = desc.replace(kw, _UNIFORM_MAP[kw])
    return desc


def _is_safety_block(error: Exception) -> bool:
    message = str(error).lower()
    return any(token in message for token in ("safety_violation", "moderation_blocked", "self-harm"))


def _safe_fallback_scenes(count: int, category: str) -> list[str]:
    if category == "social_science":
        scene = "明亮书房中的史料阅读与安静思考场景"
    elif category == "education":
        scene = "现代工作空间中的阅读、笔记与理性交流场景"
    else:
        scene = "明亮居家环境中的情绪支持、家人陪伴与规律生活场景"
    return [scene] * count


def _dialogue_visual_scene(category: str) -> str:
    """Stable, reusable visual for a two-person dialogue render."""
    directions = {
        "social_science": "安静书房中的两位成年人隔桌对谈，桌上只有无字书籍和档案，克制纪实感",
        "education": "明亮现代工作室中的两位成年人隔桌交流，桌上只有无字书籍和笔记本，理性可信赖",
    }
    return directions.get(
        category,
        "明亮温暖的居家书房中两位成年人隔桌交流，桌上只有无字书籍和茶杯，舒缓可信赖",
    )

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
    min_chars: int = 32,
    target_chars: int = 36,
    max_chars: int = 42,
) -> list[dict]:
    """Split narration into longer semantic shots averaging about ten seconds."""
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

    shots: list[dict] = []
    char_start = 0
    for i, part in enumerate(parts):
        char_count = _char_count(part)
        shots.append({
            "index": i,
            "text": part,
            "char_count": char_count,
            "char_start": char_start,
            "char_end": char_start + char_count,
            "estimated_duration": round(max(1.0, char_count / 3.5), 2),
            "motion": "zoom_in",
            "transition": "dissolve",
            "transition_duration": 0.5,
        })
        char_start += char_count
    return shots

# ── 9宫格生图 ─────────────────────────────────────────────────────────────
_GRID = max(1, int(os.environ.get("IMAGE_GRID_CELLS", "3")))
_CELL_RATIO = 4 / 3
_GRID_SIZE = config.IMAGE_GRID_SIZE
_CELL_EDGE_INSET_RATIO = 0.02
_IMAGE_SPLIT_VERSION = 2


def _visual_scene(scene: str) -> str:
    """Reduce prompt fragments that commonly make image models draw garbled text."""
    scene = re.sub(r"《[^》]*》", "一本素色无字封面的书", scene or "")
    scene = re.sub(r"[“”‘’\"']", "", scene)
    scene = re.sub(r"\d+(?:\.\d+)?", "", scene)
    return _medical_safe(scene).strip() or "安静明亮的自然生活空镜"

def _build_grid_prompt(scenes: list[str], category: str = "health") -> str:
    """构建9宫格提示词：1张图包含3×3=9个独立场景，从左到右从上到下编号。"""
    padded = list(scenes[:_GRID * _GRID])
    while len(padded) < _GRID * _GRID:
        padded.append("安静明亮的书房或自然生活空镜，主体居中，画面简洁")
    numbered = "\n".join(f"场景{i+1}：{_visual_scene(s)}" for i, s in enumerate(padded))
    category_direction = {
        "social_science": "整体改为清晰、克制、有史料感的当代纪实摄影风格；可使用书房、档案、城市、人文场景，避免戏剧化战争、仇恨符号和伪造史料文字。",
        "education": "整体改为清爽、现代、可信赖的商业阅读与工作场景；可使用书桌、会议、图表隐喻和城市办公空间，避免股票涨跌画面、财富炫耀和保证收益暗示。",
    }.get(category, "整体采用温暖叙事油画插画风，细腻可见的油画笔触与高级编辑插画质感，不追求照片级写实。主体绝对突出、背景简洁；使用温暖窗边侧光和柔和明暗层次，色彩中等饱和且明亮通透。适合中老年观众：暖白、浅木色、鼠尾草绿、低饱和砖红和雾蓝为主，可点缀现代轻英伦的格纹织物、木质书架与花园元素。人物为泛化的普通中老年人与家人，优先侧脸、背影、手部和生活动作，不做可识别真人。画面保持现代日常、轻松平和、衣着无标识、人物不戴制式帽子；不使用昏暗、破败、厚重古典暗影、卡通或夸张广告化效果。若场景涉及情绪危机或生命风险，只表现明亮安全的日常支持、家人陪伴、舒缓活动和规律生活；画面保持积极、平和、完整、无危险暗示，不呈现任何令人不安的细节、工具或姿态。")
    return (
        "请生成一张横向九宫格总图，将画面平均分为3×3共9个等大的格子，从左到右从上到下对应1-9。"
        "每个格子描绘对应的独立场景，所有格子共享同一套色彩、光线、镜头、材质和时代感。"
        f"{category_direction}"
        "每格按4:3画面构图，主体完整并保持在格子中央安全区域。"
        "九个画面必须无缝、无间距地铺满画布，格子之间不要绘制任何分隔线、白线、黑线、边框或留白。"
        "只生成视觉画面，不得把场景描述绘制进图片；所有书籍封面、屏幕、招牌、包装和背景均保持无字。"
        "整张图禁止出现中文、外文、字母、数字、标点、字幕、标签、徽标、水印和界面文字。\n\n"
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


def _trim_cell_edges(piece, inset_ratio: float = _CELL_EDGE_INSET_RATIO):
    """Remove a small inner border where providers may draw grid separators."""
    width, height = piece.size
    inset_x = min(max(1, round(width * inset_ratio)), max(1, width // 4))
    inset_y = min(max(1, round(height * inset_ratio)), max(1, height // 4))
    if width - inset_x * 2 < 2 or height - inset_y * 2 < 2:
        return piece
    return piece.crop((inset_x, inset_y, width - inset_x, height - inset_y))


def _split_grid(img_bytes: bytes, n: int, grid_cells: int | None = None) -> list[bytes]:
    """切成 n 张4:3小图；边界使用同一组精确像素坐标，避免累计误差。"""
    from PIL import Image
    cells = max(1, int(grid_cells or _GRID))
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    _validate_grid_source(w, h)
    x_bounds = [(round(i * w / cells), round((i + 1) * w / cells)) for i in range(cells)]
    y_bounds = [(round(i * h / cells), round((i + 1) * h / cells)) for i in range(cells)]
    pieces = []
    for r in range(cells):
        for c in range(cells):
            if len(pieces) >= n:
                break
            x0, x1 = x_bounds[c]
            y0, y1 = y_bounds[r]
            piece = img.crop((x0, y0, x1, y1))
            piece = _crop_to_cell_ratio(_trim_cell_edges(piece))
            buf = io.BytesIO()
            piece.save(buf, format="PNG")
            pieces.append(buf.getvalue())
    return pieces

def _download_image(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read()
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise last_error or RuntimeError("image download failed")


def _apimart_result_url(payload: dict) -> str | None:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    status = str(data.get("status") or "").lower()
    if status in ("failed", "error"):
        raise RuntimeError(f"APIMart image task failed: {data.get('error') or status}")
    if status not in ("completed", "succeeded"):
        return None
    result = data.get("result") or {}
    images = result.get("images") if isinstance(result, dict) else None
    first = images[0] if isinstance(images, list) and images else None
    if isinstance(first, dict) and first.get("url"):
        url = first["url"]
        if isinstance(url, list) and url:
            url = url[0]
        if isinstance(url, str) and url:
            return url
    raise ValueError("APIMart image task completed without an image URL")


def _load_image_provider_jobs(stage_id: str) -> dict[str, dict]:
    result = db.retry(
        lambda: db.get_client().table("stages")
        .select("params")
        .eq("id", stage_id)
        .single()
        .execute()
    )
    params = (result.data or {}).get("params") or {}
    jobs = params.get("image_provider_jobs") or {}
    return jobs if isinstance(jobs, dict) else {}


def _save_image_provider_job(stage_id: str, batch_key: str, job: dict) -> None:
    def save() -> None:
        client = db.get_client()
        result = (
            client.table("stages").select("params")
            .eq("id", stage_id).single().execute()
        )
        params = dict((result.data or {}).get("params") or {})
        jobs = dict(params.get("image_provider_jobs") or {})
        jobs[batch_key] = job
        params["image_provider_jobs"] = jobs
        client.table("stages").update({"params": params}).eq("id", stage_id).execute()

    db.retry(save)


def _generate_grid_bytes(
    client,
    image_model: str,
    prompt: str,
    *,
    stage_id: str = "",
    batch_key: str = "",
) -> bytes:
    base_url = (config.IMAGE_BASE_URL or config.OPENAI_BASE_URL).rstrip("/")
    if "api.apimart.ai" in base_url:
        if not stage_id or not batch_key:
            raise ValueError("APIMart image generation requires a persistent stage and batch key")
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        job = _load_image_provider_jobs(stage_id).get(batch_key) or {}
        reusable = (
            job.get("provider_task_id")
            and job.get("prompt_sha256") == prompt_sha256
            and job.get("model") == image_model
            and job.get("size") == _GRID_SIZE
            and job.get("status") not in {"failed", "safety_blocked"}
        )
        if reusable:
            provider_task_id = str(job["provider_task_id"])
        else:
            idempotency_key = hashlib.sha256(
                f"{stage_id}:{batch_key}:{prompt_sha256}".encode("utf-8")
            ).hexdigest()
            raw_response = client.with_options(
                timeout=config.IMAGE_REQUEST_TIMEOUT
            ).images.with_raw_response.generate(
                model=image_model,
                prompt=prompt,
                n=1,
                size=_GRID_SIZE,
                extra_headers={"Idempotency-Key": idempotency_key},
            )
            initial = json.loads(raw_response.text)
            items = initial.get("data") if isinstance(initial, dict) else None
            provider_task_id = items[0].get("task_id") if isinstance(items, list) and items else None
            if not provider_task_id:
                raise ValueError("APIMart image response did not include task_id")
            job = {
                "provider": "apimart",
                "provider_task_id": str(provider_task_id),
                "prompt_sha256": prompt_sha256,
                "idempotency_key": idempotency_key,
                "model": image_model,
                "size": _GRID_SIZE,
                "status": "submitted",
            }
            _save_image_provider_job(stage_id, batch_key, job)
        api_key = config.IMAGE_API_KEY or config.OPENAI_API_KEY
        deadline = time.monotonic() + config.IMAGE_TASK_TIMEOUT
        with httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=30.0
        ) as http:
            while time.monotonic() < deadline:
                try:
                    response = http.get(f"{base_url}/tasks/{provider_task_id}")
                    response.raise_for_status()
                    url = _apimart_result_url(response.json())
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500:
                        raise
                    time.sleep(3)
                    continue
                except httpx.TransportError:
                    time.sleep(3)
                    continue
                if url:
                    _save_image_provider_job(stage_id, batch_key, {**job, "status": "completed"})
                    return _download_image(url)
                time.sleep(3)
        _save_image_provider_job(stage_id, batch_key, {**job, "status": "polling_timeout"})
        raise TimeoutError(
            f"APIMart image task {provider_task_id} timed out; retry will resume polling"
        )

    response = client.with_options(timeout=config.IMAGE_REQUEST_TIMEOUT).images.generate(
        model=image_model, prompt=prompt, n=1, size=_GRID_SIZE,
    )
    item = response.data[0]
    if getattr(item, "b64_json", None):
        import base64
        return base64.b64decode(item.b64_json)
    if getattr(item, "url", None):
        return _download_image(item.url)
    raise ValueError("Image provider returned neither b64_json nor url")

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


def _existing_image_artifacts(task_id: str) -> dict[str, dict]:
    rows = db.retry(
        lambda: db.get_client().table("artifacts")
        .select("storage_path,meta")
        .eq("task_id", task_id)
        .eq("stage_kind", "image")
        .execute()
    ).data or []
    return {
        str(row["storage_path"]): (row.get("meta") or {})
        for row in rows if row.get("storage_path")
    }


def _run_dialogue_visual(stage: dict, text: str, category: str, client, image_model: str) -> tuple[str, str | None]:
    """Generate one dialogue key visual; render reuses it for the full narration."""
    task_id = stage["task_id"]
    path = f"{task_id}/dialogue_key_visual.png"
    index_path = f"{task_id}/images_index.json"
    existing = _existing_image_artifacts(task_id)
    prompt = _build_grid_prompt([_dialogue_visual_scene(category)], category)
    if path not in existing:
        raw = _generate_grid_bytes(
            client, image_model, prompt, stage_id=stage["id"], batch_key="dialogue_key_visual",
        )
        piece = _split_grid(raw, 1)[0]
        storage.upload_bytes(path, piece, "image/png")
        storage.add_artifact(task_id, "image", "image", path, meta={
            "index": 0, "sentence": "双人对谈主视觉", "char_count": max(1, _char_count(text)),
            "char_start": 0, "char_end": max(1, _char_count(text)), "motion": "zoom_in",
            "narration_mode": "dual_dialogue", "visual_mode": "dialogue_key_visual",
            "prompt": prompt, "prompt_scene": _dialogue_visual_scene(category), "image_model": image_model,
        })
    entry = {
        "index": 0, "path": path, "sentence": "双人对谈主视觉",
        "char_count": max(1, _char_count(text)), "char_start": 0,
        "char_end": max(1, _char_count(text)), "motion": "zoom_in",
        "narration_mode": "dual_dialogue", "visual_mode": "dialogue_key_visual",
        "prompt": prompt, "prompt_scene": _dialogue_visual_scene(category), "image_model": image_model,
    }
    storage.upload_bytes(index_path, json.dumps([entry], ensure_ascii=False, indent=2).encode("utf-8"), "application/json")
    storage.add_artifact(task_id, "image", "image_index", index_path, meta={
        "total": 1, "narration_char_count": _char_count(text), "narration_mode": "dual_dialogue",
        "visual_mode": "dialogue_key_visual",
    })
    return "done", index_path


def _load_image_index(task_id: str) -> list[dict]:
    res = db.retry(lambda: db.get_client().table("artifacts").select("storage_path").eq("task_id", task_id).eq("stage_kind", "image").eq("type", "image_index").order("created_at", desc=True).limit(1).execute())
    if not res.data:
        raise ValueError("missing image index")
    local = storage.download_artifact(res.data[0]["storage_path"], ".json")
    try:
        data = json.load(open(local, encoding="utf-8"))
    finally:
        try:
            os.remove(local)
        except OSError:
            pass
    if not isinstance(data, list):
        raise ValueError("invalid image index")
    return data


def _replacement_path(task_id: str, image_index: int) -> str:
    rows = db.retry(lambda: db.get_client().table("image_replacement_requests").select("replacement_path").eq("task_id", task_id).eq("image_index", image_index).not_.is_("replacement_path", "null").execute()).data or []
    version = len([row for row in rows if row.get("replacement_path")]) + 1
    return f"{task_id}/replacements/img_{image_index:03d}_v{version:03d}.png"


def process_replacement_request(request: dict) -> str:
    task_id = request["task_id"]
    image_index = int(request["image_index"])
    note = str(request.get("note") or "").strip()
    entries = _load_image_index(task_id)
    if image_index >= len(entries):
        raise ValueError("image index out of range")
    entry = entries[image_index]
    scene = str(entry.get("sentence") or entry.get("text") or "").strip()
    if not scene:
        raise ValueError("image sentence missing")
    client, image_model = config.image_client()
    prompt_scene = scene if not note else f"{scene}。额外修正要求：{note}"
    prompt = _build_grid_prompt([prompt_scene])
    raw = _generate_grid_bytes(client, image_model, prompt, stage_id=request["stage_id"], batch_key=f"replacement_{image_index:03d}_{request['id']}")
    piece = _split_grid(raw, 1)[0]
    path = _replacement_path(task_id, image_index)
    storage.upload_bytes(path, piece, "image/png")
    storage.add_artifact(task_id, "image", "image_replacement", path, meta={"index": image_index, "source_image": entry.get("path"), "sentence": scene, "prompt_scene": prompt_scene, "prompt": prompt, "image_model": image_model, "replacement_request_id": request["id"], "note": note, "split_version": _IMAGE_SPLIT_VERSION})
    return path


def _legacy_run_before_resume(stage: dict) -> tuple[str, str | None]:
    task_id = stage["task_id"]
    text = clean_tts_text(_find_chosen_text(task_id, stage) or "")
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

        resp = client.with_options(timeout=config.IMAGE_REQUEST_TIMEOUT).images.generate(
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
            "cell_edge_inset_ratio": _CELL_EDGE_INSET_RATIO,
            "text_policy": "no_visible_text",
            "validated": True,
            "prompt": prompt,
            "prompt_scenes": batch,
            "image_model": image_model,
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
                "char_start": shot["char_start"],
                "char_end": shot["char_end"],
                "estimated_duration": shot["estimated_duration"],
                "motion": shot["motion"],
                "source_grid": grid_path,
                "cell_ratio": "4:3",
                "cell_edge_inset_ratio": _CELL_EDGE_INSET_RATIO,
                "split_version": _IMAGE_SPLIT_VERSION,
                "prompt": prompt,
                "prompt_scene": shot["text"],
                "image_model": image_model,
            })
            image_paths.append(sp)
            meta_list.append({**shot, "path": sp, "sentence": shot["text"], "source_grid": grid_path, "prompt": prompt, "prompt_scene": shot["text"], "image_model": image_model})

    # 存索引文件
    sp_idx = f"{task_id}/images_index.json"
    storage.upload_bytes(
        sp_idx,
        json.dumps(meta_list, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json",
    )
    storage.add_artifact(task_id, "image", "image_index", sp_idx, meta={
        "total": len(image_paths),
        "narration_char_count": sum(shot["char_count"] for shot in storyboard),
    })
    return "done", sp_idx


def run(stage: dict) -> tuple[str, str | None]:
    """Idempotent image stage: resume completed grids after an interruption."""
    task_id = stage["task_id"]
    text = clean_tts_text(_find_chosen_text(task_id, stage) or "")
    if not text:
        db.set_stage(stage["id"], "failed", error="未找到选定改写稿")
        return "failed", None

    client, image_model = config.image_client()
    task_context = db.get_task_prompt_context(task_id)
    content_category = str(task_context.get("content_category") or "health")
    if str(task_context.get("narration_mode") or "single") == "dual_dialogue":
        return _run_dialogue_visual(stage, text, content_category, client, image_model)
    storyboard = _split_storyboard(text)
    if not storyboard:
        db.set_stage(stage["id"], "failed", error="最终文案无法生成分镜")
        return "failed", None

    existing_artifacts = _existing_image_artifacts(task_id)
    existing_paths = set(existing_artifacts)
    image_paths: list[str] = []
    meta_list: list[dict] = []
    for batch_start in range(0, len(storyboard), _GRID * _GRID):
        batch = storyboard[batch_start: batch_start + _GRID * _GRID]
        grid_path = f"{task_id}/grid_{batch_start // (_GRID * _GRID):03d}.png"
        expected_paths = [f"{task_id}/img_{batch_start + i:03d}.png" for i in range(len(batch))]
        if all(
            path in existing_paths
            and int(existing_artifacts[path].get("split_version") or 0) >= _IMAGE_SPLIT_VERSION
            for path in expected_paths
        ):
            for shot, path in zip(batch, expected_paths):
                image_paths.append(path)
                artifact_meta = existing_artifacts[path]
                meta_list.append({**shot, "path": path, "sentence": shot["text"], "source_grid": artifact_meta.get("source_grid"), "prompt": artifact_meta.get("prompt"), "prompt_scene": artifact_meta.get("prompt_scene") or shot["text"], "image_model": artifact_meta.get("image_model")})
            continue

        raw: bytes | None = None
        grid_prompt: str | None = None
        if grid_path in existing_paths:
            local_grid = storage.download_artifact(grid_path, ".png")
            try:
                raw = open(local_grid, "rb").read()
            finally:
                try:
                    os.remove(local_grid)
                except OSError:
                    pass
        else:
            grid_prompt = _build_grid_prompt([shot["text"] for shot in batch], content_category)
            batch_key = f"grid_{batch_start // (_GRID * _GRID):03d}"
            try:
                raw = _generate_grid_bytes(
                    client, image_model, grid_prompt, stage_id=stage["id"], batch_key=batch_key,
                )
            except Exception as exc:
                if not _is_safety_block(exc):
                    raise
                grid_prompt = _build_grid_prompt(
                    _safe_fallback_scenes(len(batch), content_category), content_category
                )
                raw = _generate_grid_bytes(
                    client, image_model, grid_prompt, stage_id=stage["id"], batch_key=batch_key,
                )
            storage.upload_bytes(grid_path, raw, "image/png")
            storage.add_artifact(task_id, "image", "image_grid", grid_path, meta={
                "grid": f"{_GRID}x{_GRID}",
                "text_policy": "no_visible_text",
                "prompt": grid_prompt,
                "prompt_scenes": [shot["text"] for shot in batch],
                "image_model": image_model,
            })

        assert raw is not None
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as grid_image:
            grid_size = grid_image.size
        _validate_grid_source(*grid_size)
        source_meta = existing_artifacts.get(grid_path) or {}
        actual_prompt = grid_prompt or source_meta.get("prompt")
        storage.add_artifact(task_id, "image", "image_grid", grid_path, meta={
            "source_size": list(grid_size),
            "grid": "3x3",
            "cell_ratio": "4:3",
            "cell_bounds_x": _grid_bounds(grid_size[0]),
            "cell_bounds_y": _grid_bounds(grid_size[1]),
            "cell_edge_inset_ratio": _CELL_EDGE_INSET_RATIO,
            "text_policy": "no_visible_text",
            "validated": True,
            "prompt": actual_prompt,
            "prompt_scenes": [shot["text"] for shot in batch],
            "image_model": image_model,
        })
        source_cells = len(source_meta.get("cell_bounds_x") or []) or _GRID
        for i, piece_bytes in enumerate(_split_grid(raw, len(batch), source_cells)):
            idx = batch_start + i
            path = expected_paths[i]
            storage.upload_bytes(path, piece_bytes, "image/png")
            shot = batch[i]
            storage.add_artifact(task_id, "image", "image", path, meta={
                "sentence": shot["text"], "index": idx,
                "batch": batch_start // (_GRID * _GRID),
                "char_count": shot["char_count"], "char_start": shot["char_start"],
                "char_end": shot["char_end"], "estimated_duration": shot["estimated_duration"],
                "motion": shot["motion"], "source_grid": grid_path,
                "cell_ratio": "4:3",
                "cell_edge_inset_ratio": _CELL_EDGE_INSET_RATIO,
                "split_version": _IMAGE_SPLIT_VERSION,
                "prompt": actual_prompt,
                "prompt_scene": shot["text"],
                "image_model": image_model,
            })
            image_paths.append(path)
            meta_list.append({**shot, "path": path, "sentence": shot["text"], "source_grid": grid_path, "prompt": actual_prompt, "prompt_scene": shot["text"], "image_model": image_model})

    index_path = f"{task_id}/images_index.json"
    storage.upload_bytes(index_path, json.dumps(meta_list, ensure_ascii=False, indent=2).encode("utf-8"), "application/json")
    storage.add_artifact(task_id, "image", "image_index", index_path, meta={
        "total": len(image_paths),
        "narration_char_count": sum(shot["char_count"] for shot in storyboard),
    })
    return "done", index_path
