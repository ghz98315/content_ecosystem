"""Supabase client and transient-network retry helpers."""
from __future__ import annotations

from functools import lru_cache
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
    if _http_client is not None:
        try:
            _http_client.close()
        except Exception:  # noqa: BLE001
            pass
        _http_client = None


def is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (ssl.SSLError, httpx.TransportError, httpx.TimeoutException)):
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
            if not all(r["status"] in ("done", "cancelled") for r in prior.data):
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
