"""抖音解析：统一接口 + 多后端（三级降级）。

M1 先做自研解析（SelfResolver，基于 yt-dlp）。
第三方 API / 手动上传作为后续降级级别接入。
"""
from __future__ import annotations
import re
import urllib.request
from dataclasses import dataclass, field


@dataclass
class ResolveResult:
    ok: bool
    title: str | None = None
    play_count: int | None = None
    author: dict = field(default_factory=dict)
    video_url: str | None = None      # 无水印直链（下载用）
    duration: float | None = None
    aweme_id: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


# 从分享文案里抠出 URL（抖音分享是一段带链接的文字）
_URL_RE = re.compile(r"https?://[^\s，。、]+")
# 抖音视频 id（19 位数字）
_ID_RE = re.compile(r"/video/(\d+)")
_UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def extract_url(share_text: str) -> str | None:
    m = _URL_RE.search(share_text or "")
    return m.group(0) if m else None


def _follow_redirect(url: str) -> str:
    """跟随短链跳转，拿到最终 URL（v.douyin.com → iesdouyin.com/share/video/…）。"""
    req = urllib.request.Request(url, headers={"User-Agent": _UA_DESKTOP})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.geturl()
    except Exception:
        return url


def normalize_douyin_url(share_text: str) -> tuple[str | None, str | None]:
    """把分享链接规范化成 yt-dlp 认识的 douyin.com/video/{id}。

    返回 (canonical_url, aweme_id)。拿不到 id 时 canonical_url 用原始 URL 兜底。
    """
    url = extract_url(share_text) or share_text
    if not url:
        return None, None
    # 短链先跟随跳转
    if "v.douyin.com" in url:
        url = _follow_redirect(url)
    m = _ID_RE.search(url)
    if m:
        vid = m.group(1)
        return f"https://www.douyin.com/video/{vid}", vid
    return url, None
