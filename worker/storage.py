"""下载 + Supabase Storage 封装。"""
from __future__ import annotations
import base64
import os
import subprocess
import tempfile
import urllib.request

import certifi
import httpx

import db
import config

BUCKET = os.environ.get("SUPABASE_BUCKET", "artifacts")
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_RESUMABLE_THRESHOLD = 49 * 1024 * 1024
_RESUMABLE_CHUNK_SIZE = 6 * 1024 * 1024


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


def download_artifact(storage_path: str, suffix: str = "") -> str:
    """从 Storage 下载到临时文件，返回本地路径。"""
    data = db.retry(
        lambda: db.get_client().storage.from_(BUCKET).download(storage_path)
    )
    fd, path = tempfile.mkstemp(suffix=suffix or os.path.splitext(storage_path)[1])
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def upload(storage_path: str, local_file: str, content_type: str = "video/mp4") -> str:
    """上传本地文件到 Storage，返回 storage_path。覆盖同名。"""
    file_size = os.path.getsize(local_file)
    if file_size >= _RESUMABLE_THRESHOLD:
        return _upload_resumable(storage_path, local_file, content_type, file_size)
    with open(local_file, "rb") as f:
        data = f.read()
    db.retry(
        lambda: db.get_client().storage.from_(BUCKET).upload(
            storage_path, data,
            {"content-type": content_type, "upsert": "true"},
        )
    )
    return storage_path


def _upload_resumable(
    storage_path: str, local_file: str, content_type: str, file_size: int
) -> str:
    """Upload large objects through Supabase Storage's TUS endpoint."""
    endpoint = config.SUPABASE_URL.rstrip("/") + "/storage/v1/upload/resumable"
    metadata = {
        "bucketName": BUCKET,
        "objectName": storage_path,
        "contentType": content_type,
        "cacheControl": "3600",
    }
    encoded_metadata = ",".join(
        f"{key} {base64.b64encode(value.encode('utf-8')).decode('ascii')}"
        for key, value in metadata.items()
    )
    headers = {
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
        "apikey": config.SUPABASE_SERVICE_KEY,
        "Tus-Resumable": "1.0.0",
        "Upload-Length": str(file_size),
        "Upload-Metadata": encoded_metadata,
        "x-upsert": "true",
    }
    with httpx.Client(verify=certifi.where(), timeout=httpx.Timeout(120.0, connect=20.0)) as client:
        response = db.retry(lambda: client.post(endpoint, headers=headers))
        if response.status_code not in (201, 204):
            raise RuntimeError(f"Supabase resumable upload init failed: {response.status_code} {response.text[:300]}")
        location = response.headers.get("location")
        if not location:
            raise RuntimeError("Supabase resumable upload did not return a location")
        if location.startswith("/"):
            location = config.SUPABASE_URL.rstrip("/") + location

        offset = 0
        with open(local_file, "rb") as source:
            while offset < file_size:
                source.seek(offset)
                chunk = source.read(min(_RESUMABLE_CHUNK_SIZE, file_size - offset))
                patch_headers = {
                    "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
                    "apikey": config.SUPABASE_SERVICE_KEY,
                    "Tus-Resumable": "1.0.0",
                    "Upload-Offset": str(offset),
                    "Content-Type": "application/offset+octet-stream",
                }
                response = db.retry(
                    lambda: client.patch(location, headers=patch_headers, content=chunk)
                )
                if response.status_code != 204:
                    raise RuntimeError(f"Supabase resumable upload failed: {response.status_code} {response.text[:300]}")
                next_offset = int(response.headers.get("Upload-Offset", offset + len(chunk)))
                if next_offset <= offset:
                    raise RuntimeError("Supabase resumable upload returned an invalid offset")
                offset = next_offset
    return storage_path


def upload_bytes(storage_path: str, data: bytes, content_type: str) -> str:
    """直接上传字节（用于 JSON 等动态内容）。覆盖同名。"""
    db.retry(
        lambda: db.get_client().storage.from_(BUCKET).upload(
            storage_path, data, {"content-type": content_type, "upsert": "true"},
        )
    )
    return storage_path


def add_artifact(task_id: str, stage_kind: str, type_: str,
                 storage_path: str, meta: dict | None = None) -> None:
    def _add() -> None:
        sb = db.get_client()
        existing = (
            sb.table("artifacts").select("id")
            .eq("task_id", task_id)
            .eq("type", type_)
            .eq("storage_path", storage_path)
            .limit(1)
            .execute()
        )
        if existing.data:
            sb.table("artifacts").update({
                "stage_kind": stage_kind,
                "meta": meta or {},
            }).eq("id", existing.data[0]["id"]).execute()
            return
        sb.table("artifacts").insert({
            "task_id": task_id,
            "stage_kind": stage_kind,
            "type": type_,
            "storage_path": storage_path,
            "meta": meta or {},
        }).execute()

    db.retry(_add)
