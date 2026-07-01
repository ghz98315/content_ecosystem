"""stages 包：把各阶段真实处理器注册进来。

M1 起：ingest 用真实处理器；其余阶段暂用 M0 假处理（sleep），逐个里程碑替换。
"""
from . import ingest, transcribe, clean, rewrite, tts, image

REAL_HANDLERS = {
    "ingest":     ingest.run,
    "transcribe": transcribe.run,
    "clean":      clean.run,
    "rewrite":    rewrite.run,
    "tts":        tts.run,
    "image":      image.run,
}
