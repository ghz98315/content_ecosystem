"""M0 worker 主循环。

验证「本地 worker ↔ Supabase ↔ 前端」实时联通：
  1. 轮询认领最靠前的 pending stage
  2. 假处理（sleep 模拟重活）
  3. rewrite/book 阶段进 needs_review（评审门），其余置 done
  4. 全部 stage 完成 → task 置 done

真正的各阶段处理逻辑在 M1+ 接入 stages/ 下的模块。
"""
import time
import config
import db
from stages import REAL_HANDLERS


def process_fake(stage: dict) -> None:
    """M0 假处理：sleep 一下模拟重活（还没接真实处理器的阶段用）。"""
    print(f"  [{stage['kind']}] processing (mock)")
    time.sleep(2)


def maybe_finish_task(task_id: str) -> None:
    """若该 task 的 8 个 stage 都 done，则 task 置 done。"""
    sb = db.get_client()
    res = sb.table("stages").select("status").eq("task_id", task_id).execute()
    statuses = [r["status"] for r in res.data]
    if statuses and all(s in ("done", "cancelled") for s in statuses):
        db.set_task_status(task_id, "done")
        print(f"  [OK] task {task_id[:8]} complete")
    elif any(s == "needs_review" for s in statuses):
        db.set_task_status(task_id, "needs_review")
    else:
        db.set_task_status(task_id, "processing")


def tick() -> bool:
    """处理一个 stage。返回是否处理了任务。"""
    stage = db.claim_next_stage()
    if not stage:
        return False

    kind = stage["kind"]
    task_id = stage["task_id"]
    print(f"认领 stage: task={task_id[:8]} kind={kind} seq={stage['seq']}")

    # 任务已被取消 → 跳过并标记
    task_res = db.get_client().table("tasks").select("status").eq("id", task_id).single().execute()
    if task_res.data and task_res.data.get("status") == "cancelled":
        db.set_stage(stage["id"], "cancelled")
        print(f"  [SKIP] {kind} skipped (task cancelled)")
        return True

    try:
        handler = REAL_HANDLERS.get(kind)
        if handler:
            # 真实处理器：自己决定 status/output_ref（可能 done 或 needs_review）
            status, output_ref = handler(stage)
            if status == "needs_review":
                # 处理器内部已 set 过 stage，这里只打印
                print(f"  [REVIEW] {kind} needs_review")
            elif status == "done":
                db.set_stage(stage["id"], "done", output_ref=output_ref)
                print(f"  [OK] {kind} done -> {output_ref}")
            else:
                # failed：处理器内部已 set_stage，这里只打印
                print(f"  [FAIL] {kind} failed (handler recorded error)")
        else:
            # 还没接真实处理器的阶段：M0 假处理 + 评审门
            process_fake(stage)
            if kind in config.REVIEW_GATES:
                db.set_stage(stage["id"], "needs_review",
                             output_ref=f"m0-fake://{kind}")
                print(f"  [REVIEW] {kind} needs_review (awaiting frontend approval)")
            else:
                db.set_stage(stage["id"], "done", output_ref=f"m0-fake://{kind}")
                print(f"  [OK] {kind} done")
    except Exception as e:  # noqa: BLE001
        db.set_stage(stage["id"], "failed", error=str(e))
        print(f"  [FAIL] {kind} failed: {e}")

    maybe_finish_task(task_id)
    return True


def main() -> None:
    config.require_config()
    print("worker 启动。轮询间隔", config.POLL_INTERVAL, "秒。Ctrl+C 退出。")
    while True:
        try:
            worked = tick()
        except KeyboardInterrupt:
            print("\n退出。")
            break
        except Exception as e:  # noqa: BLE001
            db.get_client.cache_clear()
            err_str = str(e)
            # WinError 10054 / ConnectionReset: 服务端关闭了空闲连接，属正常现象
            is_conn_reset = (
                "10054" in err_str or "ConnectionReset" in err_str
                or "RemoteDisconnected" in err_str or "ConnectionAborted" in err_str
            )
            if is_conn_reset:
                time.sleep(2)   # 短暂退避后重建连接
            else:
                print("循环异常:", e)
            worked = False
        if not worked:
            time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()
