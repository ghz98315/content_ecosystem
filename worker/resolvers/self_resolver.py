"""自研解析：基于 f2（内置 a_bogus 签名，比 yt-dlp 对新版抖音更可靠）。

- URL 规范化拿 aweme_id（短链跟随，无需 cookie）
- f2 fetch_one_video 拿完整元数据 + 无水印直链（需要 cookie）
- 抖音不公开播放量，参考实现按点赞筛选，故 play_count 存点赞数(digg_count)
- f2 是 async，这里用 asyncio.run 包成同步供 worker 调用
"""
from __future__ import annotations
import asyncio
import os

from . import ResolveResult, normalize_douyin_url

# cookies.txt 路径（环境变量 DOUYIN_COOKIES，默认 worker/cookies.txt）
COOKIES_FILE = os.environ.get(
    "DOUYIN_COOKIES",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "cookies.txt"),
)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _load_cookie() -> str:
    """从 Netscape cookies.txt 里抽出抖音相关 cookie，拼成 Cookie 头。"""
    if not os.path.isfile(COOKIES_FILE):
        return ""
    parts = []
    with open(COOKIES_FILE, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or "\t" not in line:
                continue
            if "douyin" not in line.lower():
                continue
            cols = line.strip().split("\t")
            if len(cols) >= 7:
                parts.append(f"{cols[5]}={cols[6]}")
    return "; ".join(parts)


def _pick_url(play_addr) -> str | None:
    if isinstance(play_addr, list):
        return play_addr[0] if play_addr else None
    return play_addr or None


async def _fetch(aweme_id: str) -> dict:
    from f2.apps.douyin.handler import DouyinHandler

    conf = {
        "cookie": _load_cookie(),
        "headers": {"User-Agent": _UA, "Referer": "https://www.douyin.com/"},
        "proxies": {"http://": None, "https://": None},
    }
    h = DouyinHandler(conf)
    h.enable_bark = False  # 关掉 f2 的 Bark 推送（会报 405、拖慢）
    v = await h.fetch_one_video(aweme_id=aweme_id)
    return v._to_dict()


def resolve(share_text: str) -> ResolveResult:
    canonical, vid = normalize_douyin_url(share_text)
    if not vid:
        return ResolveResult(ok=False, error=f"没能从链接解析出 aweme_id：{canonical}")
    if not _load_cookie():
        return ResolveResult(ok=False, aweme_id=vid,
                             error="缺少 cookies.txt（抖音解析需要浏览器 cookie）")
    try:
        d = asyncio.run(_fetch(vid))
    except Exception as e:  # noqa: BLE001
        return ResolveResult(ok=False, aweme_id=vid, error=f"f2 解析失败: {e}")

    if not d or not d.get("aweme_id"):
        return ResolveResult(ok=False, aweme_id=vid,
                             error="f2 返回空（cookie 可能过期，重新导出 cookies.txt）")

    dur = d.get("duration")
    return ResolveResult(
        ok=True,
        title=d.get("desc"),
        play_count=d.get("digg_count"),   # 抖音无播放量，存点赞数（选题按点赞筛）
        author={k: v for k, v in {
            "name": d.get("nickname"),
            "id": d.get("uid"),
            "sec_uid": d.get("sec_uid"),
        }.items() if v},
        video_url=_pick_url(d.get("video_play_addr")),
        duration=(dur / 1000.0) if isinstance(dur, (int, float)) else None,  # ms→s
        aweme_id=str(d.get("aweme_id")),
        raw={
            "digg_count": d.get("digg_count"),
            "comment_count": d.get("comment_count"),
            "share_count": d.get("share_count"),
            "collect_count": d.get("collect_count"),
        },
    )
