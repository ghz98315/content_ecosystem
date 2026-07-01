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


def process_fake(stage: dict) -> None:
    """M0 假处理：sleep 一下模拟重活。"""
    print(f"  [{stage['kind']}] 处理中…（模拟）")
    time.sleep(2)


def maybe_finish_task(task_id: str) -> None:
    """若该 task 的 8 个 stage 都 done，则 task 置 done。"""
    sb = db.get_client()
    res = sb.table("stages").select("status").eq("task_id", task_id).execute()
    statuses = [r["status"] for r in res.data]
    if statuses and all(s == "done" for s in statuses):
        db.set_task_status(task_id, "done")
        print(f"  ✅ task {task_id[:8]} 全部完成")
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

    try:
        process_fake(stage)
        if kind in config.REVIEW_GATES:
            db.set_stage(stage["id"], "needs_review",
                         output_ref=f"m0-fake://{kind}")
            print(f"  ⏸  {kind} 进入评审门 needs_review（等前端确认）")
        else:
            db.set_stage(stage["id"], "done", output_ref=f"m0-fake://{kind}")
            print(f"  ✔  {kind} done")
    except Exception as e:  # noqa: BLE001
        db.set_stage(stage["id"], "failed", error=str(e))
        print(f"  ✖  {kind} failed: {e}")

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
            print("循环异常:", e)
            worked = False
        if not worked:
            time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()
