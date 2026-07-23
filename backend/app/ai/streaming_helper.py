"""Shared helpers for AI calls that publish progress events."""
from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, str, str], None]
ChunkCallback = Callable[[str], Awaitable[None] | None]


@dataclass(frozen=True)
class StreamOutcome:
    """The text received from a stream and its terminal business outcome."""

    content: str
    completed: bool
    reason: str | None = None


async def _maybe_call_chunk_callback(
    callback: ChunkCallback | None,
    chunk: str,
) -> None:
    if callback is None:
        return
    result = callback(chunk)
    if inspect.isawaitable(result):
        await result


async def _close_stream(iterator: AsyncIterator[Any]) -> None:
    close = getattr(iterator, "aclose", None)
    if close is not None:
        try:
            await close()
        except Exception as exc:
            logger.warning(
                "Stream iterator close failed type=%s",
                type(exc).__name__,
            )


async def _collect_stream(
    iterator: AsyncIterator[Any],
    *,
    task_name: str,
    emit_event: Callable[[str, str], None],
    chunk_callback: ChunkCallback | None,
    heartbeat_interval: float,
    connected_event: str,
) -> StreamOutcome:
    """Collect one router stream without adding another timeout or parsing JSON."""

    chunks: list[str] = []
    chunk_count = 0
    terminal: str | None = None
    reason: str | None = None
    last_heartbeat_time = asyncio.get_running_loop().time()

    async for item in iterator:
        if isinstance(item, str):
            if not item:
                continue
            chunks.append(item)
            chunk_count += 1
            await _maybe_call_chunk_callback(chunk_callback, item)

            now = asyncio.get_running_loop().time()
            if now - last_heartbeat_time >= heartbeat_interval:
                emit_event(
                    "ai_chunk_heartbeat",
                    f"{task_name} streaming ({chunk_count} chunks)",
                )
                last_heartbeat_time = now
            continue

        if not isinstance(item, dict):
            continue

        state = item.get("state")
        if state == "connected":
            emit_event(connected_event, f"{task_name} connected")
        elif state == "receiving":
            emit_event("ai_stream_receiving", f"{task_name} receiving")
        elif state == "completed":
            terminal = "completed"
            emit_event("ai_stream_complete", f"{task_name} complete")
            break
        elif state == "interrupted":
            terminal = "interrupted"
            reason = item.get("reason") or "outbound_timeout"
            emit_event("ai_stream_interrupted", f"{task_name} interrupted")
            break
        elif item.get("type") == "error":
            terminal = "error"
            reason = item.get("code") or "stream_error"
            emit_event("ai_stream_error", f"{task_name} stream error")
            break

    completed = terminal == "completed"
    return StreamOutcome(
        content="".join(chunks),
        completed=completed,
        reason=None if completed else reason,
    )


async def stream_call_with_heartbeat(
    router: Any,
    capability: str,
    messages: list[dict[str, str]],
    response_format: dict | None = None,
    task_name: str = "AI处理",
    heartbeat_interval: float = 1.5,
    event_callback: EventCallback | None = None,
    chunk_callback: ChunkCallback | None = None,
) -> StreamOutcome:
    """Collect ``astream_capability`` while forwarding progress callbacks."""

    def emit_event(event_type: str, message: str) -> None:
        if event_callback is None:
            return
        try:
            event_callback(event_type, message, "AI")
        except Exception as exc:
            logger.debug(
                "Stream event callback failed type=%s",
                type(exc).__name__,
            )

    try:
        iterator = router.astream_capability(
            capability=capability,
            messages=messages,
            response_format=response_format,
        )
        try:
            return await _collect_stream(
                iterator,
                task_name=task_name,
                emit_event=emit_event,
                chunk_callback=chunk_callback,
                heartbeat_interval=heartbeat_interval,
                connected_event="ai_stream_start",
            )
        finally:
            await _close_stream(iterator)
    except Exception as exc:
        logger.error(
            "Streaming call %s failed type=%s",
            task_name,
            type(exc).__name__,
        )
        emit_event("ai_stream_error", f"{task_name} stream failed")
        raise


async def stream_invoke_with_heartbeat(
    router: Any,
    capability: str,
    payload: dict,
    task_name: str = "AI处理",
    heartbeat_interval: float = 2.0,
    event_callback: EventCallback | None = None,
    chunk_callback: ChunkCallback | None = None,
) -> StreamOutcome:
    """Collect ``astream`` while forwarding progress callbacks."""

    def emit_event(event_type: str, message: str) -> None:
        if event_callback is None:
            return
        try:
            event_callback(event_type, message, "AI")
        except Exception:
            pass

    emit_event("ai_stream_start", f"{task_name} stream started")
    try:
        iterator = router.astream(capability, payload)
        try:
            return await _collect_stream(
                iterator,
                task_name=task_name,
                emit_event=emit_event,
                chunk_callback=chunk_callback,
                heartbeat_interval=heartbeat_interval,
                connected_event="ai_stream_connected",
            )
        finally:
            await _close_stream(iterator)
    except Exception as exc:
        logger.error(
            "Streaming invoke %s failed type=%s",
            task_name,
            type(exc).__name__,
        )
        emit_event("ai_stream_error", f"{task_name} stream failed")
        raise


async def invoke_with_heartbeat(
    router: Any,
    capability: str,
    payload: dict,
    task_name: str = "AI处理",
    heartbeat_interval: float = 2.0,
    event_callback: Callable[[str, str, str], None] | None = None,
) -> dict:
    """非流式调用的心跳封装 - 使用 ainvoke (不推荐，容易超时)

    对于不支持流式的场景，通过定时心跳来保持连接活跃。
    """
    def emit_event(event_type: str, message: str):
        if event_callback:
            try:
                event_callback(event_type, message, "AI")
            except Exception:
                pass

    emit_event("ai_request_start", f"🚀 {task_name} 开始请求")

    heartbeat_task = None
    heartbeat_count = 0

    async def send_heartbeats():
        nonlocal heartbeat_count
        while True:
            await asyncio.sleep(heartbeat_interval)
            heartbeat_count += 1
            emit_event("ai_heartbeat", f"💓 {task_name} 等待中 ({heartbeat_count * heartbeat_interval:.0f}s)")

    try:
        heartbeat_task = asyncio.create_task(send_heartbeats())
        response = await router.ainvoke(capability, payload)

        emit_event("ai_request_complete", f"✅ {task_name} 完成")
        return response
    except asyncio.CancelledError:
        emit_event("ai_request_cancelled", f"🚫 {task_name} 已取消")
        raise
    except Exception as exc:
        emit_event("ai_request_error", f"❌ {task_name} 失败")
        logger.error(
            "[AI请求] %s 失败 type=%s",
            task_name,
            type(exc).__name__,
        )
        raise
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass


async def acall_with_heartbeat(
    router: Any,
    capability: str,
    messages: list[dict[str, str]],
    response_format: dict | None = None,
    task_name: str = "AI处理",
    heartbeat_interval: float = 2.0,
    event_callback: Callable[[str, str, str], None] | None = None,
) -> str:
    """非流式 acall_capability 的心跳封装"""
    def emit_event(event_type: str, message: str):
        if event_callback:
            try:
                event_callback(event_type, message, "AI")
            except Exception:
                pass

    emit_event("ai_request_start", f"🚀 {task_name} 开始请求")

    heartbeat_task = None
    heartbeat_count = 0

    async def send_heartbeats():
        nonlocal heartbeat_count
        while True:
            await asyncio.sleep(heartbeat_interval)
            heartbeat_count += 1
            emit_event("ai_heartbeat", f"💓 {task_name} 等待中 ({heartbeat_count * heartbeat_interval:.0f}s)")

    try:
        heartbeat_task = asyncio.create_task(send_heartbeats())
        response = await router.acall_capability(
            capability, messages, response_format
        )

        emit_event("ai_request_complete", f"✅ {task_name} 完成")
        return response
    except asyncio.CancelledError:
        emit_event("ai_request_cancelled", f"🚫 {task_name} 已取消")
        raise
    except Exception as exc:
        emit_event("ai_request_error", f"❌ {task_name} 失败")
        logger.error(
            "[AI请求] %s 失败 type=%s",
            task_name,
            type(exc).__name__,
        )
        raise
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
