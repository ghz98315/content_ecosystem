"""Supabase 客户端封装（worker 侧，service_role）。"""
from functools import lru_cache
from supabase import create_client, Client
import config


@lru_cache(maxsize=1)
def get_client() -> Client:
    config.require_config()
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)


def claim_next_stage() -> dict | None:
    """认领最靠前的一个 pending stage，原子置为 processing。

    M0 简化版：先查再改。单 worker 够用；多 worker 时需换成
    Postgres 函数 + FOR UPDATE SKIP LOCKED 做真正的原子认领。
    """
    sb = get_client()
    res = (
        sb.table("stages")
        .select("*")
        .eq("status", "pending")
        .order("seq")
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    stage = res.data[0]
    upd = (
        sb.table("stages")
        .update({"status": "processing"})
        .eq("id", stage["id"])
        .eq("status", "pending")   # 乐观锁：仍是 pending 才认领成功
        .execute()
    )
    if not upd.data:
        return None  # 被别的 worker 抢了
    return upd.data[0]


def set_stage(stage_id: str, status: str, output_ref: str | None = None,
              error: str | None = None) -> None:
    patch: dict = {"status": status}
    if output_ref is not None:
        patch["output_ref"] = output_ref
    if error is not None:
        patch["error"] = error
    get_client().table("stages").update(patch).eq("id", stage_id).execute()


def set_task_status(task_id: str, status: str) -> None:
    get_client().table("tasks").update({"status": status}).eq("id", task_id).execute()
