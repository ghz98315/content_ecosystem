"""Read-only local stock library adapter for approved, externally narrated tasks.

Only contact frames and the edit decision list are uploaded. Source MP4 files
remain on the Worker machine and are checked again immediately before render.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from urllib.parse import urlencode, urlsplit
from pathlib import Path

import httpx
import imageio_ffmpeg
from PIL import Image, ImageFilter, ImageOps, ImageStat

import db
import storage
from narration import clean_tts_text, visible_len
from stock_processing import motion_probe, settings
from stock_timing import timed_blocks

DEFAULT_ROOT = r"D:\Obsidian\99_剪映素材库\剪映公用素材库"
FOLDERS = {
    "guoxue": ("20_国学", "10_通用画面"),
    "health": ("30_健康", "10_通用画面"),
    "scene": ("40_城市场景", "10_通用画面"),
}
# Checked at three points in the source. These contain prominent baked-in
# lettering or a phone interface, so they must not enter automated selection.
EXCLUDED_NAMES = {
    "13437496578829092.mp4", "13437497502513749.mp4",
    "13437497479368540.mp4",
}
# Visual inspection of the 4:3 crop: soft-focus or prominent modern signs.
# Keep the originals on disk for other categories, but skip them for Guoxue.
EXCLUDED_FOR_GUOXUE = {
    # Dark, shallow-focus red flower dominated the first narrated shot in the
    # 2026-10-27 acceptance video; it does not fit the open scenic direction.
    "13437497285421121.mp4",
    "13437498054343706.mp4", "13437498388625108.mp4",
    "13437496983141845.mp4", "13437496799094888.mp4",
    "13437499187602832.mp4",
    "13437498192327096.mp4", "13437498919637988.mp4",
}


def library_root() -> Path:
    root = Path(os.environ.get("LOCAL_MEDIA_LIBRARY_ROOT", DEFAULT_ROOT)).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("本地素材库目录不存在")
    return root


def resolve_asset(asset: dict) -> Path:
    """Never trust a path supplied through task params or a saved edit list."""
    root = library_root()
    relative = str(asset.get("relative_path") or "")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("本地素材路径无效")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root) or path.suffix.lower() != ".mp4" or not path.is_file():
        raise ValueError("素材文件超出允许的本地素材库")
    if path.parent.name == "00_待整理":
        raise ValueError("待整理素材不能用于成片")
    expected_size = asset.get("bytes")
    if expected_size is not None and path.stat().st_size != int(expected_size):
        raise ValueError("本地素材已改变，请重新检查并选片")
    return path


def resolve_book_cover(asset: dict) -> Path:
    root = library_root()
    relative = str(asset.get("relative_path") or "")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("本地书籍封面路径无效")
    path = (root / relative).resolve(strict=True)
    health_root = (root / FOLDERS["health"][0]).resolve(strict=True)
    if (not path.is_relative_to(health_root) or path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp")
            or not path.is_file()):
        raise ValueError("书籍封面不在健康类素材目录")
    expected_size = asset.get("bytes")
    if expected_size is not None and path.stat().st_size != int(expected_size):
        raise ValueError("本地书籍封面已改变，请重新执行素材节点")
    return path


def _book_key(value: str) -> str:
    return re.sub(r"[\W_]+|第[一二三四五六七八九十百\d]+版$|(?:0?[1-9]|[12]\d)$", "", value,
                  flags=re.UNICODE).casefold()


def local_book_cover(book_name: str) -> dict | None:
    key = _book_key(book_name)
    if not key:
        return None
    folder = library_root() / FOLDERS["health"][0]
    candidates=[]
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        stem_key=_book_key(path.stem)
        if key not in stem_key and stem_key not in key:
            continue
        try:
            with Image.open(path) as picture:width,height=picture.size
        except (OSError,ValueError):
            continue
        exact=int(stem_key==key);first=int(bool(re.search(r"(?:^|\D)0?1$",path.stem)))
        candidates.append(((exact,first,width*height,-len(path.stem)),path,width,height))
    if not candidates:return None
    _,path,width,height=max(candidates,key=lambda item:item[0])
    relative=path.relative_to(library_root()).as_posix()
    return {"id":"local-book-"+hashlib.sha256(relative.encode()).hexdigest()[:12],
            "provider":"local_book_cover","media_type":"image","relative_path":relative,
            "title":f"《{book_name}》封面","page":"本地健康素材库","author":"用户提供",
            "license":"按本地素材库授权记录","license_url":"","duration":0,
            "width":width,"height":height,"bytes":path.stat().st_size}


def network_book_cover(book_name: str) -> dict | None:
    """Public bibliographic fallback; local covers always take precedence."""
    query=urlencode({"q":f'intitle:"{book_name}"',"maxResults":5,"printType":"books"})
    wanted=_book_key(book_name);ranked=[]
    headers={"User-Agent":"ContentEcosystem/1.0 (book-cover lookup)"}
    try:
        with httpx.Client(timeout=15,follow_redirects=False,headers=headers) as client:
            response=client.get("https://www.googleapis.com/books/v1/volumes?"+query)
            response.raise_for_status();items=response.json().get("items") or []
        for item in items:
            info=item.get("volumeInfo") or {};title=str(info.get("title") or "")
            links=info.get("imageLinks") or {};url=str(links.get("extraLarge") or links.get("large")
                or links.get("medium") or links.get("small") or links.get("thumbnail") or "").replace("http://","https://",1)
            parsed=urlsplit(url)
            if parsed.scheme!="https" or parsed.hostname not in {"books.google.com","books.googleusercontent.com"}:continue
            score=(int(_book_key(title)==wanted),int(wanted in _book_key(title)),-abs(len(title)-len(book_name)))
            ranked.append((score,item,info,url))
    except (httpx.HTTPError,ValueError,KeyError):
        ranked=[]
    if ranked:
        _,item,info,url=max(ranked,key=lambda row:row[0])
        return {"id":"google-books-"+str(item.get("id") or hashlib.sha256(url.encode()).hexdigest()[:12]),
                "provider":"network_book_cover","media_type":"image","url":url,
                "title":str(info.get("title") or book_name),"page":str(info.get("infoLink") or "https://books.google.com/"),
                "author":"、".join(info.get("authors") or []),"license":"书籍信息源封面；发布前请核对版本与使用权",
                "license_url":"https://developers.google.com/books/docs/v1/using","duration":0,"width":0,"height":0}
    # Open Library is an independent fallback when Google is unavailable or
    # rate-limited. Request only the fields needed for a single lookup.
    search=urlencode({"title":book_name,"fields":"key,title,author_name,cover_i","limit":5})
    with httpx.Client(timeout=15,follow_redirects=False,headers=headers) as client:
        response=client.get("https://openlibrary.org/search.json?"+search)
        response.raise_for_status();docs=response.json().get("docs") or []
    options=[]
    for doc in docs:
        cover=doc.get("cover_i");title=str(doc.get("title") or "")
        if not cover:continue
        score=(int(_book_key(title)==wanted),int(wanted in _book_key(title)),-abs(len(title)-len(book_name)))
        options.append((score,doc,title,int(cover)))
    if not options:return None
    _,doc,title,cover=max(options,key=lambda row:row[0])
    url=f"https://covers.openlibrary.org/b/id/{cover}-L.jpg?default=false"
    return {"id":f"openlibrary-{cover}","provider":"network_book_cover","media_type":"image","url":url,
            "title":title or book_name,"page":"https://openlibrary.org"+str(doc.get("key") or ""),
            "author":"、".join(doc.get("author_name") or []),"license":"Open Library 书籍目录封面；发布前请核对版本与使用权",
            "license_url":"https://openlibrary.org/dev/docs/api/covers","duration":0,"width":0,"height":0}


def probe(path: Path) -> tuple[float, int, int]:
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=12)
    duration = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    video = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", result.stderr)
    if not duration or not video:
        raise ValueError(f"素材视频无法读取：{path.name}")
    hours, minutes, seconds = duration.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds), int(video[1]), int(video[2])


def scan(category: str) -> list[dict]:
    root = library_root()
    folders = FOLDERS.get(category, FOLDERS["guoxue"])
    assets = []
    for folder in folders:
        for path in sorted((root / folder).glob("*.mp4")):
            if (path.name in EXCLUDED_NAMES
                    or (category == 'guoxue' and path.name in EXCLUDED_FOR_GUOXUE)
                    or path.is_symlink()):
                continue
            try:
                duration, width, height = probe(path)
                if duration < 8 or min(width, height) < 540:
                    continue
                relative = path.relative_to(root).as_posix()
                assets.append({
                    "id": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16],
                    "provider": "local_library", "media_type": "video",
                    "relative_path": relative, "title": f"{folder} · {path.stem}",
                    "tags": folder, "page": "本地素材库", "author": "用户提供",
                    "license": "按素材库授权记录", "license_url": "",
                    "duration": duration, "width": width, "height": height,
                    "bytes": path.stat().st_size,
                })
            except (OSError, ValueError, subprocess.TimeoutExpired):
                continue
    if not assets:
        raise ValueError("本地素材库没有可用视频")
    return assets


def native_crop_size(width: int, height: int, aspect: str) -> tuple[int, int]:
    """Size left after an aspect crop, before any interpolation."""
    ratio = {"1:1": 1.0, "4:3": 4 / 3}.get(aspect)
    if ratio is None:
        raise ValueError("本地视频画幅不支持")
    crop_width = min(width, int(height * ratio))
    return crop_width, min(height, int(crop_width / ratio))


def meets_native_resolution(asset: dict, aspect: str, target_width: int = 1080) -> bool:
    crop_width, _ = native_crop_size(int(asset["width"]), int(asset["height"]), aspect)
    return crop_width >= target_width


def _seed_value(*parts: object) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _unused_start(asset_duration: float, clip_duration: float,
                  occupied: list[tuple[float, float]], seed: str, index: int,
                  asset_id: str) -> float | None:
    """Choose a stable task-specific excerpt that does not repeat this task's source range."""
    maximum = asset_duration - clip_duration - .2
    if maximum < 0:
        return None
    free = [(0.0, maximum)]
    for start, end in occupied:
        blocked = (start - clip_duration - 1.0, end + 1.0)
        free = [(left, right) for low, high in free
                for left, right in ((low, min(high, blocked[0])),
                                    (max(low, blocked[1]), high)) if right >= left]
    if not free:
        return None
    # The source's useful window changes across tasks, but is reproducible
    # when a pending stage is retried for the same task.
    slot = min(len(free)-1, int(_seed_value(seed, index, asset_id, "slot") * len(free)))
    low, high = free[slot]
    return round(low + (high-low) * _seed_value(seed, index, asset_id, "offset"), 2)


def sequence_signature(entries: list[dict]) -> str:
    sequence = [(item["asset"].get("relative_path") or item["asset"].get("storage_path"), round(item["source_start"], 2),
                 round(item["source_end"], 2)) for item in entries]
    return hashlib.sha256(json.dumps(sequence, ensure_ascii=False).encode("utf-8")).hexdigest()


def _book_cover_settings(task_id: str) -> tuple[dict | None, str]:
    row = db.retry(lambda: db.get_client().table("stages").select("params")
                   .eq("task_id", task_id).eq("kind", "book").single().execute()).data or {}
    params = row.get("params") or {}
    cover_path = str(params.get("manual_book_cover_path") or "").strip()
    book_name = str(params.get("manual_book_name") or "").strip().strip("《》")
    if not book_name:
        from stages.render import _load_json_artifact
        payload = _load_json_artifact(task_id, "book") or {}
        book_name = str(payload.get("book_name") or "").strip().strip("《》")
        if not book_name:
            # The book stage is skipped for the current production workflow;
            # the confirmed rewrite carries the selected book title instead.
            rewrite = _load_json_artifact(task_id, "rewrite") or {}
            book_name = str(rewrite.get("book_title") or "").strip().strip("《》")
    if cover_path and params.get("book_confirmed") is True:
        return ({"id":hashlib.sha256(cover_path.encode()).hexdigest()[:16],
                 "provider":"task_artifact","media_type":"image","storage_path":cover_path,
                 "title":f"《{book_name}》封面","page":"任务书籍信息","author":"用户确认",
                 "license":"用户确认使用","license_url":"","duration":0,"width":0,"height":0},book_name)
    if not book_name:return None,""
    local=local_book_cover(book_name)
    if local:return local,book_name
    try:return network_book_cover(book_name),book_name
    except (httpx.HTTPError,ValueError,KeyError):return None,book_name


def _cover_ranges(text: str, subtitles: dict, book_name: str) -> list[tuple[int, int]]:
    """Use the first and last subtitle phrases that actually say the book name."""
    plain_name = clean_tts_text(book_name).replace("《", "").replace("》", "")
    if not plain_name:
        return []
    segments = subtitles.get("segments") or []
    ranges=[];cursor=0
    for cue in segments:
        cue_text=clean_tts_text(str(cue.get("text") or ""))
        count=visible_len(cue_text)
        start=int(cue.get("char_start",cursor));end=int(cue.get("char_end",start+count))
        if plain_name in cue_text.replace("《", "").replace("》", ""):
            ranges.append((start,max(start+1,end)))
        cursor=max(cursor,end)
    if not ranges:
        # Alignment may split a title across two short cues. Fall back to the
        # manuscript positions and keep a little surrounding spoken context.
        plain=clean_tts_text(text).replace("《", "").replace("》", "")
        positions=[];offset=0
        while True:
            found=plain.find(plain_name,offset)
            if found<0:break
            positions.append((max(0,found-4),min(visible_len(plain),found+len(plain_name)+6)))
            offset=found+len(plain_name)
        ranges=positions
    if not ranges:return []
    chosen=[ranges[0]]
    if ranges[-1]!=ranges[0]:chosen.append(ranges[-1])
    return chosen


def add_book_cover_inserts(entries: list[dict], text: str, subtitles: dict,
                           book_name: str, cover_asset: dict, preview_path: str) -> list[dict]:
    """Replace only the spoken book-title phrases with the confirmed cover."""
    ranges=_cover_ranges(text,subtitles,book_name)
    if not ranges:return entries
    from stages import render
    duration=float(subtitles.get("duration") or 0)
    output=[]
    for entry in entries:
        left=int(entry["char_start"]);right=int(entry["char_end"])
        cuts={left,right}
        for start,end in ranges:
            if start<right and end>left:cuts.update((max(left,start),min(right,end)))
        points=sorted(cuts)
        for start,end in zip(points,points[1:]):
            if end<=start:continue
            is_cover=any(start>=low and end<=high for low,high in ranges)
            piece={**entry,"char_start":start,"char_end":end,"char_count":end-start,
                   "sentence":f"《{book_name}》封面" if is_cover else entry.get("sentence","")}
            start_time=render._cue_time_at_char(start,subtitles.get("segments") or [],duration)
            end_time=render._cue_time_at_char(end,subtitles.get("segments") or [],duration)
            piece.update(start=start_time,end=end_time,duration=max(0.0,end_time-start_time))
            if is_cover:
                piece.update(asset=cover_asset,source_start=0.0,source_end=0.0,
                             playback_rate=1.0,path=preview_path,visual_type="image",
                             motion="still_photo",book_cover_insert=True,
                             processing=settings({"color_style":"natural_warm_v1","feather":36}))
            else:
                rate=float(entry.get("playback_rate",1))
                shift=max(0.0,start_time-float(entry.get("start",start_time)))*rate
                piece["source_start"]=float(entry["source_start"])+shift
                piece["source_end"]=piece["source_start"]+max(0.0,end_time-start_time)*rate
            output.append(piece)
    for index,item in enumerate(output):item["index"]=index
    return output


def plan(text: str, subtitles: dict, category: str, *, aspect: str = "1:1",
         require_native: bool = False, output_width: int = 1080,
         selection_seed: str = "") -> list[dict]:
    """Task-seeded excerpts; never overlap ranges from one source within a video."""
    from stages import render

    duration = float(subtitles["duration"])
    parts = timed_blocks(text, subtitles, target=43, minimum=34, maximum=55)
    # A tiny trailing clip feels like a glitch. Attach it to its predecessor.
    if len(parts) > 1:
        prefix = sum(visible_len(part) for part in parts[:-1])
        if duration - render._cue_time_at_char(prefix, subtitles["segments"], duration) < 12:
            parts[-2] += parts[-1]
            parts.pop()
    cursor = 0
    sketches = []
    for part in parts:
        size = visible_len(part)
        sketches.append({"index": len(sketches), "sentence": part, "char_start": cursor,
                         "char_end": cursor + size, "char_count": size, "path": "pending"})
        cursor += size
    timeline = render._build_timeline(sketches, subtitles["segments"], duration)
    for sketch, timing in zip(sketches, timeline):
        sketch.update(start=timing["start"], end=timing["end"], duration=timing["duration"])

    assets = scan(category)
    if require_native:
        assets = [asset for asset in assets if meets_native_resolution(asset, aspect, output_width)]
        if not assets:
            raise ValueError(
                f"本地素材在裁成{aspect}后均不足{output_width}像素宽，已暂停选片以避免模糊；"
                "请补充更清晰的视频素材"
            )
    used: dict[str, int] = {}
    occupied: dict[str, list[tuple[float, float]]] = {}
    result = []
    for index, sketch in enumerate(sketches):
        wanted = float(sketch["duration"])
        options = []
        for asset in assets:
            for rate in (1.0, 0.5, 0.3):
                if asset["duration"] >= wanted * rate + .25:
                    last = used.get(asset["id"], -100)
                    if index - last <= 2:
                        continue
                    source_duration = wanted * rate
                    source_start = _unused_start(asset["duration"], source_duration,
                                                 occupied.get(asset["id"], []), selection_seed,
                                                 index, asset["id"])
                    if source_start is None:
                        continue
                    # Prefer fresh footage, normal speed and diverse folders.
                    preferred = FOLDERS.get(category, FOLDERS["guoxue"])[index % 2]
                    native_width, _ = native_crop_size(asset["width"], asset["height"], aspect)
                    score = (int(last >= 0) * 20 + (0 if rate == 1 else 4 if rate == .5 else 12)
                             + (0 if asset["relative_path"].startswith(preferred) else 2)
                             + int(asset["duration"] < wanted + 2) * 2
                             + (0 if native_width >= output_width * 4 / 3 else 3))
                    options.append((score, _seed_value(selection_seed,index,asset["id"],"order"),
                                    asset["id"], asset, rate, source_start))
                    break
        if not options:
            raise ValueError(f"第 {index + 1} 段没有不重复的可用本地片段，请补充素材或缩短该段")
        _, _, _, asset, rate, source_start = min(options)
        used[asset["id"]] = index
        source_duration = wanted * rate
        occupied.setdefault(asset["id"], []).append((source_start, source_start + source_duration))
        result.append({**sketch, "asset": asset, "source_start": source_start,
                       "source_end": source_start + source_duration, "playback_rate": rate,
                       "require_native_crop": require_native,
                       "render_width": output_width,
                       "processing": settings({"color_style": "natural_warm_v1", "feather": 36})})
    return result


def check_excerpt(entry: dict) -> dict:
    path = resolve_asset(entry["asset"])
    actual, width, height = probe(path)
    source_duration = entry["duration"] * entry["playback_rate"]
    if actual - entry["source_start"] < source_duration - .05:
        raise ValueError(f"源片时长不足：{path.name}")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    start = float(entry["source_start"])
    probes = [motion_probe(path, ff, start, min(8, source_duration)),
              motion_probe(path, ff, start + max(0, source_duration - 8), min(8, source_duration))]
    if all(item.get("state") == "nearly_static" for item in probes):
        raise ValueError(f"所选片段几乎静止：{path.name}")
    return {"source_width": width, "source_height": height,
            "motion_check": probes, "source_duration": round(actual, 2)}


def cover_score(path: Path, entry: dict) -> float:
    """Favor a sharp, readable scenic frame over a dark or flat first shot."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        light = ImageStat.Stat(image.convert("L"))
        edge = ImageStat.Stat(image.convert("L").filter(ImageFilter.FIND_EDGES))
        saturation = ImageStat.Stat(image.convert("HSV").getchannel("S"))
    crop_width, _ = native_crop_size(entry["source_width"], entry["source_height"],
                                     entry["cell_ratio"])
    return (min(edge.stddev[0], 55) * .8 + min(light.stddev[0], 80) * .4
            + min(saturation.mean[0], 160) * .08
            - abs(light.mean[0] - 145) * .25 + min(crop_width / 100, 15))


def run(stage: dict) -> tuple[str, str | None]:
    from stages.image import _find_chosen_text
    from stock_media import load_audio_timeline

    task = stage["task_id"]
    text = clean_tts_text(_find_chosen_text(task, stage) or "")
    if not text:
        raise ValueError("缺少已确认文案")
    subtitles = load_audio_timeline(task)
    category = str((stage.get("params") or {}).get("content_line") or "guoxue")
    aspect = str((stage.get("params") or {}).get("image_aspect_ratio") or "4:3")
    # The local library is largely 720p. Keep the visible 4:3 crop at native
    # width for both content lines, rather than enlarging it to 1080p.
    require_native = category in {"guoxue", "health"}
    output_width = 720 if require_native else 1080
    cover_asset, book_name = _book_cover_settings(task) if category == "health" else (None, "")
    previous = db.retry(lambda: db.get_client().table("artifacts").select("meta")
                        .eq("type", "video_index").contains("meta", {"source": "local_library"})
                        .neq("task_id", task).order("created_at", desc=True).limit(500).execute()).data or []
    previous_signatures = {str((row.get("meta") or {}).get("sequence_signature"))
                           for row in previous if (row.get("meta") or {}).get("sequence_signature")}
    for attempt in range(12):
        entries = plan(text, subtitles, category, aspect=aspect, require_native=require_native,
                       output_width=output_width, selection_seed=f"{task}:{attempt}")
        signature = sequence_signature(entries)
        if signature not in previous_signatures:
            break
    else:
        raise ValueError("本地素材无法形成与已有任务不同的片段顺序，请补充可用视频")
    revision = uuid.uuid4().hex
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    width, height = (960, 720) if aspect == "4:3" else (720, 720)
    scratch = Path(__file__).resolve().parent / "output"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="local-materials-", dir=scratch) as directory:
        cover_options = []
        for entry in entries:
            entry.update(check_excerpt(entry))
            source = resolve_asset(entry["asset"])
            preview = Path(directory) / f"{entry['index']:03}.jpg"
            # Preview is the exact center-cropped composition used by the render.
            command = [ff, "-y", "-loglevel", "error", "-ss",
                       str(entry["source_start"] + entry["duration"] * entry["playback_rate"] / 2),
                       "-i", str(source), "-frames:v", "1", "-vf",
                       f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}", str(preview)]
            subprocess.run(command, check=True, capture_output=True, timeout=30)
            path = f"{task}/stock/local-{revision}/preview-{entry['index']:03}.jpg"
            storage.upload(path, str(preview), "image/jpeg")
            storage.add_artifact(task, "image", "image", path,
                                 meta={"visual_mode": "stock_video", "source": "local_library"})
            entry.update(path=path, cell_ratio=aspect, visual_type="video", motion="source_motion")
            cover_options.append((cover_score(preview, entry), entry["index"]))
        cover_index = max(cover_options)[1]
        entries[0]["cover_path"] = entries[cover_index]["path"]
        entries[0]["cover_source_index"] = cover_index
        if cover_asset and book_name:
            try:
                from stock_media import fetch_source
                source=fetch_source(cover_asset)
                preview=Path(directory)/"book-cover.jpg"
                with Image.open(source) as picture:
                    picture=ImageOps.exif_transpose(picture).convert("RGB")
                    picture.thumbnail((720,720),Image.Resampling.LANCZOS)
                    canvas=Image.new("RGB",(720,720),(236,229,215))
                    canvas.paste(picture,((720-picture.width)//2,(720-picture.height)//2))
                    canvas.save(preview,"JPEG",quality=90)
                preview_path=f"{task}/stock/local-{revision}/book-cover.jpg"
                storage.upload(preview_path,str(preview),"image/jpeg")
                storage.add_artifact(task,"image","image",preview_path,
                                     meta={"visual_mode":"stock_video","source":"book_cover",
                                           "provider":cover_asset.get("provider"),"book_name":book_name})
                entries = add_book_cover_inserts(entries, text, subtitles, book_name,
                                                 cover_asset, preview_path)
            except (OSError,ValueError,httpx.HTTPError) as exc:
                print(f"  [local-materials] 书封插片跳过：{type(exc).__name__}: {exc}",flush=True)
    prefix = f"{task}/stock/local-{revision}"
    index_path = prefix + "/index.json"
    storage.upload_bytes(index_path, json.dumps(entries, ensure_ascii=False).encode("utf-8"),
                         "application/json")
    storage.add_artifact(task, "image", "video_index", index_path,
                         meta={"visual_mode": "stock_video", "source": "local_library",
                               "count": len(entries), "sequence_signature": signature})
    db.set_stage(stage["id"], "needs_review", output_ref=index_path,
                 error="请预览并确认本地素材清单，确认后开始拼接")
    return "needs_review", index_path
