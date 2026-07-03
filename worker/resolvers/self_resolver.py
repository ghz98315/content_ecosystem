"""自研解析：基于 f2（内置 a_bogus 签名，比 yt-dlp 对新版抖音更可靠）。

cookie 策略（双保险，默认不用手动导出）：
  1. 自动生成匿名 token（ttwid/msToken/verify_fp/s_v_web_id）—— 每次运行自动抓，你只给链接
  2. 若自动生成解析失败，回退到 cookies.txt（手动导出的浏览器 cookie）

- URL 规范化拿 aweme_id（短链跟随，无需 cookie）
- 抖音不公开播放量，参考实现按点赞筛选，故 play_count 存点赞数(digg_count)
- f2 是 async，这里用 asyncio.run 包成同步供 worker 调用
"""
from __future__ import annotations
import asyncio
import os

from . import ResolveResult, normalize_douyin_url

# cookies.txt 路径（仅作回退，环境变量 DOUYIN_COOKIES 覆盖，默认 worker/cookies.txt）
COOKIES_FILE = os.environ.get(
    "DOUYIN_COOKIES",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "cookies.txt"),
)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def gen_anon_cookie() -> str:
    """用 f2 的 TokenManager 自动生成一套匿名 cookie（免手动导出）。"""
    from f2.apps.douyin.utils import TokenManager, VerifyFpManager
    parts = []
    try:
        parts.append(f"ttwid={TokenManager.gen_ttwid()}")
    except Exception:
        pass
    try:
        parts.append(f"msToken={TokenManager.gen_real_msToken()}")
    except Exception:
        pass
    try:
        parts.append(f"verifyFp={VerifyFpManager.gen_verify_fp()}")
        parts.append(f"s_v_web_id={VerifyFpManager.gen_s_v_web_id()}")
    except Exception:
        pass
    return "; ".join(parts)


def load_cookie_file() -> str:
    """回退：从 Netscape cookies.txt 抽抖音 cookie 拼成 Cookie 头。"""
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


async def _fetch(aweme_id: str, cookie: str) -> dict:
    from f2.apps.douyin.handler import DouyinHandler

    conf = {
        "cookie": cookie,
        "headers": {"User-Agent": _UA, "Referer": "https://www.douyin.com/"},
        "proxies": {"http://": None, "https://": None},
    }
    h = DouyinHandler(conf)
    h.enable_bark = False  # 关掉 f2 的 Bark 推送（会报 405、拖慢）
    v = await h.fetch_one_video(aweme_id=aweme_id)
    return v._to_dict()


def _try_fetch(vid: str, cookie: str) -> dict | None:
    if not cookie:
        return None
    try:
        d = asyncio.run(_fetch(vid, cookie))
    except Exception:
        return None
    return d if d and d.get("aweme_id") else None


async def _fetch_comments(aweme_id: str, cookie: str, limit: int = 20) -> list[dict]:
    from f2.apps.douyin.handler import DouyinHandler
    conf = {
        "cookie": cookie,
        "headers": {"User-Agent": _UA, "Referer": "https://www.douyin.com/"},
        "proxies": {"http://": None, "https://": None},
    }
    h = DouyinHandler(conf)
    h.enable_bark = False
    comments = []
    async for c in h.fetch_video_comments(aweme_id=aweme_id):
        d = c._to_dict()
        comments.append({
            "text":    d.get("text") or d.get("content") or "",
            "likes":   d.get("digg_count") or 0,
            "author":  d.get("nickname") or "",
            "replies": d.get("reply_comment_total") or 0,
        })
        if len(comments) >= limit:
            break
    return sorted(comments, key=lambda x: x["likes"], reverse=True)


def fetch_hot_comments(aweme_id: str, limit: int = 10) -> list[dict]:
    """抓取热门评论（最多 limit 条，按点赞降序）。失败时返回空列表。"""
    for cookie_fn in (gen_anon_cookie, load_cookie_file):
        cookie = cookie_fn()
        if not cookie:
            continue
        try:
            return asyncio.run(_fetch_comments(aweme_id, cookie, limit))
        except Exception:
            continue
    return []


def resolve(share_text: str) -> ResolveResult:
    canonical, vid = normalize_douyin_url(share_text)
    if not vid:
        return ResolveResult(ok=False, error=f"没能从链接解析出 aweme_id：{canonical}")

    # 一级：自动生成匿名 cookie（你只给链接，无需手动导出）
    d = _try_fetch(vid, gen_anon_cookie())
    # 二级回退：cookies.txt
    if not d:
        d = _try_fetch(vid, load_cookie_file())
    if not d:
        return ResolveResult(
            ok=False, aweme_id=vid,
            error="解析失败：自动 cookie 与 cookies.txt 均未拿到数据（可能被风控，稍后重试或导出新 cookie）",
        )

    dur = d.get("duration")
    fans = d.get("fans_count") or d.get("follower_count")
    return ResolveResult(
        ok=True,
        title=d.get("desc"),
        play_count=d.get("digg_count"),   # 抖音无播放量，存点赞数（选题按点赞筛）
        author={k: v for k, v in {
            "name": d.get("nickname"),
            "id": d.get("uid"),
            "sec_uid": d.get("sec_uid"),
            "fans_count": fans,
        }.items() if v is not None},
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
