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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

CLEAN_MODEL   = os.environ.get("CLEAN_MODEL",   "gpt-4o-mini")   # 清洗：便宜够用
REWRITE_MODEL = os.environ.get("REWRITE_MODEL", "gpt-4o")        # 改写：质量要求高
BOOK_MODEL    = os.environ.get("BOOK_MODEL",    "")               # 书名反推：空=用 deepseek-v4-flash，没 key 则 fallback gpt-4o-mini       # 书名反推，没配 fallback openai
THIRDPARTY_DOUYIN_KEY = os.environ.get("THIRDPARTY_DOUYIN_KEY", "")  # 可选备用解析

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
