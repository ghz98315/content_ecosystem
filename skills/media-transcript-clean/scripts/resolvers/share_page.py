"""Read public video metadata embedded in Douyin's mobile share page."""
from __future__ import annotations

import json
import re

import httpx

from . import ResolveResult

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)


def parse_page(html: str, video_id: str) -> ResolveResult:
    marker = re.search(r"(?:window\.)?_ROUTER_DATA\s*=\s*", html)
    if not marker:
        raise ValueError("分享页未返回作品数据，可能需要网页验证或稍后重试")
    data, _ = json.JSONDecoder().raw_decode(html[marker.end():])
    for loader in data.get("loaderData", {}).values():
        if not isinstance(loader, dict):
            continue
        info = loader.get("videoInfoRes") or {}
        for item in info.get("item_list") or []:
            if str(item.get("aweme_id")) != video_id:
                continue
            video = item.get("video") or {}
            urls = (video.get("play_addr") or {}).get("url_list") or []
            url = next((u for u in urls if isinstance(u, str) and u.startswith("https://")), None)
            if not url:
                raise ValueError("作品没有可下载的视频地址，请上传原视频或音频")
            author = item.get("author") or {}
            stats = item.get("statistics") or {}
            duration = video.get("duration")
            return ResolveResult(
                ok=True, aweme_id=video_id, title=item.get("desc"),
                video_url=url,
                duration=duration / 1000 if isinstance(duration, (int, float)) else None,
                play_count=stats.get("digg_count"),
                author={k: v for k, v in {
                    "name": author.get("nickname"), "sec_uid": author.get("sec_uid"),
                    "id": author.get("uid"),
                }.items() if v is not None},
                raw={"resolver": "share_page", **{k: stats.get(k) for k in (
                    "digg_count", "comment_count", "share_count", "collect_count")}},
            )
    raise ValueError("分享页未包含对应作品，可能已下架、仅自己可见或需要登录验证")


def resolve(video_id: str, cookie: str = "") -> ResolveResult:
    if not re.fullmatch(r"\d{1,30}", video_id):
        raise ValueError("作品编号无效")
    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"}
    if cookie:
        headers["Cookie"] = cookie
    # This host is fixed: never forward login cookies to a supplied URL or redirect.
    with httpx.Client(verify=True, trust_env=False, timeout=25, follow_redirects=False) as client:
        response = client.get(f"https://www.douyin.com/share/video/{video_id}/", headers=headers)
        response.raise_for_status()
        return parse_page(response.text, video_id)
