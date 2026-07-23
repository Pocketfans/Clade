from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Callable
from typing import TypeVar, cast

T = TypeVar("T")


class BoundedDaemonRunner:
    """Run blocking operations under a bounded daemon-thread total deadline."""

    def __init__(self, max_workers: int = 4) -> None:
        if max_workers <= 0 or max_workers > 4:
            raise ValueError("max_workers must be between 1 and 4")
        self._slots = threading.BoundedSemaphore(max_workers)
        self._state_lock = threading.Lock()
        self._active = 0
        self._max_active = 0

    @property
    def max_active(self) -> int:
        with self._state_lock:
            return self._max_active

    def _mark_started(self) -> None:
        with self._state_lock:
            self._active += 1
            self._max_active = max(self._max_active, self._active)

    def _mark_finished(self) -> None:
        with self._state_lock:
            self._active -= 1

    def _start_worker(self, worker: Callable[[], None]) -> None:
        thread = threading.Thread(
            target=worker,
            name="clade-safe-http",
            daemon=True,
        )
        try:
            thread.start()
        except BaseException:
            self._slots.release()
            raise

    def run(self, operation: Callable[[], T], *, timeout: float) -> T:
        deadline = time.monotonic() + max(timeout, 0.0)
        if not self._slots.acquire(timeout=max(deadline - time.monotonic(), 0.0)):
            raise TimeoutError

        result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

        def worker() -> None:
            self._mark_started()
            try:
                try:
                    result.put((True, operation()))
                except BaseException as exc:
                    result.put((False, exc))
            finally:
                self._mark_finished()
                self._slots.release()

        self._start_worker(worker)

        try:
            succeeded, value = result.get(
                timeout=max(deadline - time.monotonic(), 0.0)
            )
        except queue.Empty:
            raise TimeoutError from None
        if succeeded:
            return cast(T, value)
        raise cast(BaseException, value)

    async def arun(self, operation: Callable[[], T], *, timeout: float) -> T:
        loop = asyncio.get_running_loop()
        deadline = time.monotonic() + max(timeout, 0.0)
        while not self._slots.acquire(blocking=False):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            await asyncio.sleep(min(0.01, remaining))

        future: asyncio.Future[T] = loop.create_future()

        def publish(succeeded: bool, value: object) -> None:
            if future.done():
                return
            if succeeded:
                future.set_result(cast(T, value))
            else:
                future.set_exception(cast(BaseException, value))

        def worker() -> None:
            self._mark_started()
            try:
                try:
                    value: object = operation()
                    succeeded = True
                except BaseException as exc:
                    value = exc
                    succeeded = False
                try:
                    loop.call_soon_threadsafe(publish, succeeded, value)
                except RuntimeError:
                    # The owning event loop may already be closed after cancellation.
                    pass
            finally:
                self._mark_finished()
                self._slots.release()

        self._start_worker(worker)
        try:
            done, _ = await asyncio.wait(
                {future},
                timeout=max(deadline - time.monotonic(), 0.0),
            )
        except asyncio.CancelledError:
            future.cancel()
            raise
        if not done:
            future.cancel()
            raise TimeoutError from None
        return future.result()


DEFAULT_BOUNDED_RUNNER = BoundedDaemonRunner(max_workers=4)
