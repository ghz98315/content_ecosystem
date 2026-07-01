"""下载 + Supabase Storage 封装。"""
from __future__ import annotations
import os
import subprocess
import tempfile
import urllib.request

import db

BUCKET = os.environ.get("SUPABASE_BUCKET", "artifacts")
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(video_path: str, bitrate: str = "64k") -> str:
    """从视频抽音频为 mp3（单声道、够 ASR 用即可，体积小）。返回音频路径。"""
    out = os.path.splitext(video_path)[0] + ".mp3"
    cmd = [
        _ffmpeg(), "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", bitrate,
        out,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def ensure_bucket() -> None:
    """确保 bucket 存在（幂等）。用 service_role 建，私有。"""
    sb = db.get_client()
    try:
        sb.storage.get_bucket(BUCKET)
    except Exception:
        try:
            sb.storage.create_bucket(BUCKET, options={"public": False})
        except Exception:
            pass  # 并发或已存在


def download(url: str, suffix: str = ".mp4", referer: str = "https://www.douyin.com/") -> str:
    """下载到临时文件，返回本地路径。"""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=120) as resp, open(path, "wb") as f:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return path


def upload(storage_path: str, local_file: str, content_type: str = "video/mp4") -> str:
    """上传本地文件到 Storage，返回 storage_path。覆盖同名。"""
    sb = db.get_client()
    with open(local_file, "rb") as f:
        data = f.read()
    sb.storage.from_(BUCKET).upload(
        storage_path, data,
        {"content-type": content_type, "upsert": "true"},
    )
    return storage_path


def add_artifact(task_id: str, stage_kind: str, type_: str,
                 storage_path: str, meta: dict | None = None) -> None:
    db.get_client().table("artifacts").insert({
        "task_id": task_id,
        "stage_kind": stage_kind,
        "type": type_,
        "storage_path": storage_path,
        "meta": meta or {},
    }).execute()
