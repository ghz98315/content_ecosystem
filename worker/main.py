"""M0 worker 主循环。

验证「本地 worker ↔ Supabase ↔ 前端」实时联通：
  1. 轮询认领最靠前的 pending stage
  2. 假处理（sleep 模拟重活）
  3. rewrite/book 阶段进 needs_review（评审门），其余置 done
  4. 全部 stage 完成 → task 置 done

真正的各阶段处理逻辑在 M1+ 接入 stages/ 下的模块。
"""
import threading
import time
import config
import db
from stages import REAL_HANDLERS
from stages.image import process_replacement_request


class StageHeartbeat:
    def __init__(self, stage_id: str, interval: float) -> None:
        self.stage_id = stage_id
        self.interval = max(1.0, interval)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                db.touch_stage(self.stage_id)
            except Exception as exc:  # noqa: BLE001
                print(f"  [heartbeat] refresh failed: {type(exc).__name__}: {str(exc)[:160]}", flush=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=min(2.0, self.interval))


def recover_orphaned_stages() -> list[dict]:
    recovered = db.recover_stale_stages(
        config.WORKER_TASK_ID,
        config.WORKER_STALE_STAGE_SECONDS,
    )
    for stage in recovered:
        print(
            f"  [RECOVER] task={stage['task_id'][:8]} kind={stage['kind']} requeued",
            flush=True,
        )
    return recovered


def process_fake(stage: dict) -> None:
    """M0 假处理：sleep 一下模拟重活（还没接真实处理器的阶段用）。"""
    print(f"  [{stage['kind']}] processing (mock)")
    time.sleep(2)


def maybe_finish_task(task_id: str) -> None:
    """若该 task 的 8 个 stage 都 done，则 task 置 done。"""
    task = db.retry(
        lambda: db.get_client().table("tasks").select("status").eq("id", task_id).single().execute()
    )
    if task.data and task.data.get("status") == "cancelled":
        return

    res = db.retry(
        lambda: db.get_client().table("stages").select("status").eq("task_id", task_id).execute()
    )
    statuses = [r["status"] for r in res.data]
    # A non-cancelled task with cancelled stages must never be reported as done.
    # Only an explicitly cancelled task may contain cancelled downstream stages.
    if any(s == "cancelled" for s in statuses):
        if task.data and task.data.get("status") == "cancelled":
            return
        db.set_task_status(task_id, "failed")
        print(f"  [FAIL] task {task_id[:8]} has cancelled stages")
    elif statuses and all(s == "done" for s in statuses):
        db.set_task_status(task_id, "done")
        print(f"  [OK] task {task_id[:8]} complete")
    elif any(s == "failed" for s in statuses):
        db.set_task_status(task_id, "failed")
    elif any(s == "needs_review" for s in statuses):
        db.set_task_status(task_id, "needs_review")
    else:
        db.set_task_status(task_id, "processing")


def tick() -> bool:
    """处理一个 stage。返回是否处理了任务。"""
    replacement = db.claim_next_image_replacement()
    if replacement:
        print(f"璁ら replacement: task={replacement['task_id'][:8]} image={replacement['image_index']}", flush=True)
        try:
            path = process_replacement_request(replacement)
            db.complete_image_replacement(replacement["id"], path)
            print(f"  [OK] replacement done -> {path}", flush=True)
        except Exception as exc:  # noqa: BLE001
            db.fail_image_replacement(replacement["id"], str(exc))
            print(f"  [FAIL] replacement failed: {exc}", flush=True)
        return True

    stage = db.claim_next_stage(config.WORKER_TASK_ID)
    if not stage:
        return False

    kind = stage["kind"]
    task_id = stage["task_id"]
    print(f"认领 stage: task={task_id[:8]} kind={kind} seq={stage['seq']}")

    heartbeat = StageHeartbeat(stage["id"], config.WORKER_HEARTBEAT_INTERVAL)
    heartbeat.start()

    try:
        # 任务已被取消 → 跳过并标记
        task_res = db.retry(
            lambda: db.get_client().table("tasks")
            .select("status").eq("id", task_id).single().execute()
        )
        if task_res.data and task_res.data.get("status") == "cancelled":
            db.set_stage(stage["id"], "cancelled")
            print(f"  [SKIP] {kind} skipped (task cancelled)")
            return True

        handler = REAL_HANDLERS.get(kind)
        if handler:
            # 真实处理器：自己决定 status/output_ref（可能 done 或 needs_review）
            # Handlers may create paid external side effects. Retrying the whole
            # handler can submit them again; each handler owns its safe retries.
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
    finally:
        heartbeat.stop()

    maybe_finish_task(task_id)
    return True


def main() -> None:
    config.require_config()
    print("worker 启动。轮询间隔", config.POLL_INTERVAL, "秒。Ctrl+C 退出。")
    if config.WORKER_TASK_ID:
        print("测试隔离模式：仅处理任务", config.WORKER_TASK_ID)
    recover_orphaned_stages()
    while True:
        try:
            worked = tick()
        except KeyboardInterrupt:
            print("\n退出。")
            break
        except Exception as e:  # noqa: BLE001
            if db.is_transient_error(e):
                db.reset_client()
                print(f"轮询网络重试: {type(e).__name__}: {str(e)[:180]}")
                time.sleep(2)   # 短暂退避后重建连接
            else:
                print("循环异常:", e)
            worked = False
        if not worked:
            time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()
