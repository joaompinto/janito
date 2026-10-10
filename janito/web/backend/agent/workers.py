"""Track sync work until an ACP turn can safely release its process cwd.

Web turns retain their existing ``asyncio.to_thread`` behaviour. ACP installs
one tracker per turn: shielded worker tasks survive cancellation of their
caller and are drained before its cwd and turn lock are released.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Any, TypeVar

T = TypeVar("T")


class WorkerTracker:
    """Own the thread-hop tasks started by one turn."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def register(self, task: asyncio.Task) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        # A cancelled caller no longer retrieves the worker's exception.
        # Consume it here as well as in drain to avoid unhandled-task errors.
        if not task.cancelled():
            task.exception()

    async def drain(self) -> None:
        """Wait for outstanding workers, including ones whose caller cancelled."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


_current: ContextVar[WorkerTracker | None] = ContextVar("janito_worker_tracker", default=None)


def set_tracker(tracker: WorkerTracker) -> Token:
    return _current.set(tracker)


def reset_tracker(token: Token) -> None:
    _current.reset(token)


async def run_in_worker(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run sync work, retaining ownership when its ACP caller is cancelled."""
    tracker = _current.get()
    if tracker is None:
        return await asyncio.to_thread(func, *args, **kwargs)
    task = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    tracker.register(task)
    return await asyncio.shield(task)


async def drain_shielded(tracker: WorkerTracker) -> bool:
    """Drain once despite repeated cancellation; report cancellation during cleanup."""
    drain_task = asyncio.create_task(tracker.drain())
    cancelled = False
    while True:
        try:
            await asyncio.shield(drain_task)
            return cancelled
        except asyncio.CancelledError:
            cancelled = True
