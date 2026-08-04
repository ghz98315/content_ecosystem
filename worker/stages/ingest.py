"""① 采集 ingest：解析抖音链接 → 下载视频 → 传 Storage → 回写元数据。

三级降级：
  1. 自研解析（f2）
  2. 第三方 API（未配则跳过）—— M1 先留占位
  3. 手动上传兜底 —— 前端上传后，worker 见 params.manual_video 直接用
"""
from __future__ import annotations

import os

import db
import storage
from resolvers import self_resolver


def _write_task_meta(task_id: str, res) -> None:
    patch = {}
    if res.title:
        patch["title"] = res.title
    if res.play_count is not None:
        patch["play_count"] = res.play_count
    if res.author:
        patch["author"] = res.author
    if patch:
        db.get_client().table("tasks").update(patch).eq("id", task_id).execute()


def run(stage: dict) -> tuple[str, str | None]:
    """处理 ingest。返回 (status, output_ref)。

    status: 'done' | 'needs_review'（三级都失败时等手动上传）
    """
    task_id = stage["task_id"]
    params = stage.get("params") or {}

    # 拿 source_url
    task = db.get_client().table("tasks").select("source_url").eq("id", task_id).single().execute()
    source_url = (task.data or {}).get("source_url") or ""

    # --- 手动上传兜底：前端已上传文件到 Storage，params 里带路径 ---
    if params.get("manual_file"):
        _write_task_meta(task_id, type("R", (), {
            "title": params.get("manual_title"),
            "play_count": params.get("manual_like"),
            "author": {"name": params.get("manual_author")} if params.get("manual_author") else {},
        })())
        src_path = params["manual_file"]          # e.g. {task_id}/manual.mp4
        storage.ensure_bucket()
        local = storage.download_artifact(src_path)
        audio = None
        try:
            # 视频→抽音频；已是音频→直接用
            audio = local if params.get("manual_is_audio") else storage.extract_audio(local)
            sp = f"{task_id}/audio.mp3"
            storage.upload(sp, audio, "audio/mpeg")
            storage.add_artifact(task_id, "ingest", "audio", sp, meta={
                "source": "manual_upload",
                "original": src_path,
            })
        finally:
            paths = {local}
            if audio:
                paths.add(audio)
            for p in paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
        return "done", sp

    # --- 一级：自研解析 ---
    res = self_resolver.resolve(source_url)
    if not res.ok or not res.video_url:
        # 二级第三方 API 未接入前，直接进评审门等手动上传
        db.set_stage(stage["id"], "needs_review",
                     error=(res.error or "解析未拿到视频，请手动上传"))
        return "needs_review", None

    _write_task_meta(task_id, res)

    # 热门评论（best-effort，失败不阻塞流程）
    comments = []
    if res.aweme_id:
        try:
            comments = self_resolver.fetch_hot_comments(res.aweme_id, limit=50)
        except Exception:
            pass

    # 下载视频 → 抽音频 → 只上传音频（免费档 50MB 限制；原视频仅用于出逐字稿）
    storage.ensure_bucket()
    local_video = storage.download(res.video_url, suffix=".mp4")
    try:
        audio = storage.extract_audio(local_video)
        sp = f"{task_id}/audio.mp3"
        storage.upload(sp, audio, "audio/mpeg")
        storage.add_artifact(task_id, "ingest", "audio", sp, meta={
            "aweme_id": res.aweme_id,
            "duration": res.duration,
            "video_url": res.video_url,
            "hot_comments": comments,
            "purchase_intent_comments": self_resolver.select_purchase_intent_comments(comments),
            **res.raw,
        })
    finally:
        for p in (local_video, locals().get("audio")):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass

    return "done", sp
