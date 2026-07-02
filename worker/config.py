"""M0 worker 配置。所有密钥从环境变量读取，绝不进前端。"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ---- Supabase ----
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
# worker 用 service_role key，绕过 RLS
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ---- 大模型（清洗/改写/生图/书名反推）----
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")   # 第三方中转填此项，如 https://api.xcode.best/v1
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

CLEAN_MODEL   = os.environ.get("CLEAN_MODEL",   "gpt-4o-mini")
REWRITE_MODEL = os.environ.get("REWRITE_MODEL", "gpt-4o")
BOOK_MODEL    = os.environ.get("BOOK_MODEL",    "")

THIRDPARTY_DOUYIN_KEY = os.environ.get("THIRDPARTY_DOUYIN_KEY", "")


def openai_client(api_key: str = "", base_url: str = ""):
    """创建 OpenAI 客户端，自动读取 base_url（支持第三方中转）。"""
    from openai import OpenAI
    key  = api_key  or OPENAI_API_KEY
    url  = base_url or OPENAI_BASE_URL
    kwargs = {"api_key": key}
    if url:
        kwargs["base_url"] = url
    return OpenAI(**kwargs)

# ---- 轮询 ----
POLL_INTERVAL = float(os.environ.get("WORKER_POLL_INTERVAL", "3"))

# TTS
TTS_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")       # tiny/base/small/medium/large-v3
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")       # cpu / cuda
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")    # int8(cpu) / float16(cuda)

# 8 阶段顺序
STAGE_ORDER = ["ingest", "transcribe", "clean", "rewrite", "tts", "image", "book", "render"]

# M0：这两个阶段进 needs_review，验证评审门（等前端把它推回 pending）
REVIEW_GATES = {"rewrite", "book"}


def require_config() -> None:
    missing = [k for k, v in {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
    }.items() if not v]
    if missing:
        raise SystemExit(
            "缺少环境变量: " + ", ".join(missing) +
            "\n请复制 worker/.env.example 为 worker/.env 并填写。"
        )
