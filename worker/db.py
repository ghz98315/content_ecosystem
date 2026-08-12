"""Supabase client and transient-network retry helpers."""
from __future__ import annotations

from functools import lru_cache
from datetime import datetime, timedelta, timezone
import ssl
import time
from typing import Callable, TypeVar

import certifi
import httpx
from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions

import config


T = TypeVar("T")
_http_client: httpx.Client | None = None
_TRANSIENT_MARKERS = (
    "unexpected_eof_while_reading",
    "eof occurred in violation of protocol",
    "server disconnected",
    "remote end closed connection",
    "connectionreset",
    "connection reset",
    "connectionaborted",
    "remotedisconnected",
    "read operation timed out",
    "readtimeout",
    "connecttimeout",
    "winerror 10054",
)


@lru_cache(maxsize=1)
def get_client() -> Client:
    global _http_client
    config.require_config()
    _http_client = httpx.Client(
        verify=certifi.where(),
        http2=False,
        timeout=httpx.Timeout(120.0, connect=20.0),
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10, keepalive_expiry=10.0),
    )
    options = SyncClientOptions(
        httpx_client=_http_client,
        postgrest_client_timeout=120,
        storage_client_timeout=120,
    )
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, options=options)


def reset_client() -> None:
    global _http_client
    get_client.cache_clear()
    # Heartbeats run in a separate thread.  A retry in the main loop may happen
    # while that thread is still issuing a request with this client, so closing
    # it here races active requests and produces "client has been closed".
    # Drop our reference instead; the retired client is reclaimed on process
    # exit after any in-flight request has completed.
    _http_client = None


def is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (ssl.SSLError, httpx.TransportError, httpx.TimeoutException)):
        return True
    exception_name = type(exc).__name__.lower()
    if "timeout" in exception_name or "connectionerror" in exception_name:
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def retry(operation: Callable[[], T], attempts: int = 4) -> T:
    """Retry only transient transport failures, rebuilding the shared client."""
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            if not is_transient_error(exc) or attempt == attempts - 1:
                raise
            reset_client()
            time.sleep(min(8.0, 1.5 * (2 ** attempt)))
    raise RuntimeError("unreachable")


def get_task_prompt_context(task_id: str) -> dict:
    """Read prompt context while remaining compatible before migration 0003 runs."""
    # Keep first-publication tasks readable before optional migrations are applied.
    selects = (
        "title,author,content_category,rewrite_mode,source_task_id,version_no",
        "title,author,content_category",
        "title,author",
    )
    last_error: Exception | None = None
    for fields in selects:
        try:
            result = retry(
                lambda fields=fields: get_client().table("tasks")
                .select(fields)
                .eq("id", task_id)
                .single()
                .execute()
            )
            return result.data or {}
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if "42703" not in str(exc):
                raise
    raise last_error or RuntimeError("读取任务上下文失败")


def claim_next_stage(task_id: str = "") -> dict | None:
    """认领最靠前的一个 pending stage，原子置为 processing。

    只认领"前置 stage 全部 done"的任务，确保 needs_review 阶段阻塞后续流程。
    """
    sb = get_client()
    # 取所有 pending stage，按 seq 排列
    query = sb.table("stages").select("*").eq("status", "pending")
    if task_id:
        query = query.eq("task_id", task_id)
    res = query.order("seq").execute()
    if not res.data:
        return None

    for stage in res.data:
        stage_task_id = stage["task_id"]
        seq     = stage["seq"]
        task = (
            sb.table("tasks")
            .select("status")
            .eq("id", stage_task_id)
            .single()
            .execute()
        )
        if not task.data or task.data.get("status") not in ("pending", "processing"):
            continue
        # 检查同一任务中 seq 更小的 stage 是否都 done
        if seq > 1:
            prior = (
                sb.table("stages")
                .select("status")
                .eq("task_id", stage_task_id)
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
    retry(lambda: get_client().table("stages").update(patch).eq("id", stage_id).execute())


def set_task_status(task_id: str, status: str) -> None:
    retry(lambda: get_client().table("tasks").update({"status": status}).eq("id", task_id).execute())


def claim_next_image_replacement() -> dict | None:
    sb = get_client()
    res = retry(lambda: sb.table("image_replacement_requests").select("*").eq("status", "pending").order("requested_at").limit(20).execute())
    if not res.data:
        return None
    for request in res.data:
        task = retry(lambda request=request: sb.table("tasks").select("status").eq("id", request["task_id"]).single().execute())
        if not task.data or task.data.get("status") == "cancelled":
            continue
        upd = retry(lambda request=request: sb.table("image_replacement_requests").update({"status": "processing", "error": None}).eq("id", request["id"]).eq("status", "pending").execute())
        if upd.data:
            return upd.data[0]
    return None


def complete_image_replacement(request_id: str, replacement_path: str) -> None:
    retry(lambda: get_client().table("image_replacement_requests").update({"status": "done", "replacement_path": replacement_path, "completed_at": datetime.now(timezone.utc).isoformat(), "error": None}).eq("id", request_id).execute())


def fail_image_replacement(request_id: str, error: str) -> None:
    retry(lambda: get_client().table("image_replacement_requests").update({"status": "failed", "error": error[:500], "completed_at": datetime.now(timezone.utc).isoformat()}).eq("id", request_id).execute())


def touch_stage(stage_id: str) -> None:
    """Refresh the lease timestamp while a handler is still running."""
    retry(
        lambda: get_client().table("stages")
        .update({"status": "processing"})
        .eq("id", stage_id)
        .eq("status", "processing")
        .execute()
    )


def recover_stale_stages(task_id: str = "", stale_seconds: float = 300) -> list[dict]:
    """Requeue processing stages whose worker heartbeat has expired."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=max(1.0, stale_seconds))
    ).isoformat()
    def fetch_stale():
        # retry() may rebuild the shared client after a transport failure. Build
        # the request inside the operation so it never reuses a closed client.
        query = (
            get_client().table("stages")
            .select("id,task_id,kind,updated_at")
            .eq("status", "processing")
            .lt("updated_at", cutoff)
        )
        if task_id:
            query = query.eq("task_id", task_id)
        return query.execute()

    stale = retry(fetch_stale).data or []
    recovered: list[dict] = []
    for stage in stale:
        result = retry(
            lambda stage_id=stage["id"]: get_client().table("stages")
            .update({
                "status": "pending",
                "error": "Worker heartbeat expired; stage automatically requeued",
            })
            .eq("id", stage_id)
            .eq("status", "processing")
            .lt("updated_at", cutoff)
            .execute()
        )
        if result.data:
            recovered.append(stage)
            set_task_status(stage["task_id"], "processing")
    return recovered
