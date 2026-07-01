"""stages 包：把各阶段真实处理器注册进来。

M1 起：ingest 用真实处理器；其余阶段暂用 M0 假处理（sleep），逐个里程碑替换。
"""
from . import ingest

# kind → 处理函数，返回 (status, output_ref)
REAL_HANDLERS = {
    "ingest": ingest.run,
}
