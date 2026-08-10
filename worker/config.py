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

CLEAN_MODEL   = os.environ.get("CLEAN_MODEL",   "gpt-5.5")
REWRITE_MODEL = os.environ.get("REWRITE_MODEL", "gpt-5.5")
BOOK_MODEL    = os.environ.get("BOOK_MODEL",    "gpt-5.5")

# ---- 生图（可独立于文字模型，支持 openai / doubao 两个后端）----
IMAGE_PROVIDER = os.environ.get("IMAGE_PROVIDER", "openai")   # openai | doubao

# gpt 生图
IMAGE_API_KEY  = os.environ.get("IMAGE_API_KEY",  "")   # 留空则复用 OPENAI_API_KEY
IMAGE_BASE_URL = os.environ.get("IMAGE_BASE_URL", "")   # 留空则复用 OPENAI_BASE_URL
IMAGE_MODEL    = os.environ.get("IMAGE_MODEL",    "dall-e-3")
# Grid source size. gpt-image-2 supports a 3:2 landscape canvas; each 3x3
# cell is then cropped deterministically to the required 4:3 video still.
IMAGE_GRID_SIZE = os.environ.get("IMAGE_GRID_SIZE", "1536x1024")

# doubao（豆包）生图
DOUBAO_API_KEY     = os.environ.get("DOUBAO_API_KEY", "")
DOUBAO_BASE_URL    = os.environ.get("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
DOUBAO_IMAGE_MODEL = os.environ.get("DOUBAO_IMAGE_MODEL", "doubao-seedream-3-0-t2i-250415")


def image_client():
    """生图专用客户端。按 IMAGE_PROVIDER 选后端，返回 (client, model)。"""
    if IMAGE_PROVIDER == "doubao":
        return openai_client(api_key=DOUBAO_API_KEY, base_url=DOUBAO_BASE_URL), DOUBAO_IMAGE_MODEL
    key = IMAGE_API_KEY or OPENAI_API_KEY
    url = IMAGE_BASE_URL or OPENAI_BASE_URL
    return openai_client(api_key=key, base_url=url), IMAGE_MODEL

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
# Optional safety filter for isolated end-to-end testing.
WORKER_TASK_ID = os.environ.get("WORKER_TASK_ID", "").strip()
# A running stage refreshes updated_at on this cadence. A restarted worker
# requeues processing stages whose heartbeat has expired.
WORKER_HEARTBEAT_INTERVAL = float(os.environ.get("WORKER_HEARTBEAT_INTERVAL", "20"))
WORKER_STALE_STAGE_SECONDS = float(os.environ.get("WORKER_STALE_STAGE_SECONDS", "300"))
IMAGE_REQUEST_TIMEOUT = float(os.environ.get("IMAGE_REQUEST_TIMEOUT", "180"))
IMAGE_TASK_TIMEOUT = float(os.environ.get("IMAGE_TASK_TIMEOUT", "300"))
# Long-form narration can produce 8-12 minute timelines. Keep a bounded
# deadline while allowing one ffmpeg encode step to finish on CPU machines.
RENDER_TIMEOUT = float(os.environ.get("RENDER_TIMEOUT", "1800"))
RENDER_SUBPROCESS_TIMEOUT = float(os.environ.get("RENDER_SUBPROCESS_TIMEOUT", "600"))
# Balanced dissolve launches one ffmpeg process per merge. Long timelines use
# deterministic hard cuts to avoid spending the whole render budget on merges.
RENDER_DISSOLVE_MAX_CLIPS = int(os.environ.get("RENDER_DISSOLVE_MAX_CLIPS", "24"))

# TTS
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "edge")
TTS_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
COSYVOICE2_VOICE = (
    os.environ.get("COSYVOICE2_VOICE", "").strip()
    or os.environ.get("COSYVOICE_VOICE", "").strip()
)
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")       # tiny/base/small/medium/large-v3
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")       # cpu / cuda
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")    # int8(cpu) / float16(cuda)

# 8 阶段顺序（tts 在 book 之后，CTA 需要书籍信息）
STAGE_ORDER = ["ingest", "transcribe", "clean", "rewrite", "image", "book", "tts", "render"]

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
