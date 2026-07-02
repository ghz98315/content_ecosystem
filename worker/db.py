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

    只认领"前置 stage 全部 done"的任务，确保 needs_review 阶段阻塞后续流程。
    """
    sb = get_client()
    # 取所有 pending stage，按 seq 排列
    res = (
        sb.table("stages")
        .select("*")
        .eq("status", "pending")
        .order("seq")
        .execute()
    )
    if not res.data:
        return None

    for stage in res.data:
        task_id = stage["task_id"]
        seq     = stage["seq"]
        # 检查同一任务中 seq 更小的 stage 是否都 done
        if seq > 1:
            prior = (
                sb.table("stages")
                .select("status")
                .eq("task_id", task_id)
                .lt("seq", seq)
                .execute()
            )
            if not all(r["status"] == "done" for r in prior.data):
                continue  # 有前置未完成，跳过

        # 乐观锁认领
        upd = (
            sb.table("stages")
            .update({"status": "processing"})
            .eq("id", stage["id"])
            .eq("status", "pending")
            .execute()
        )
        if upd.data:
            return upd.data[0]

    return None


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
