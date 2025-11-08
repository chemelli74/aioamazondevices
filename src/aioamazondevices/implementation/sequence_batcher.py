"""Sequence batching coordinator for Amazon Echo API."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from aioamazondevices.utils import _LOGGER

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class SequenceBatcher:
    """Coordinates batching of sequence operations to reduce API calls."""

    def __init__(
        self,
        batch_delay: float,
        send_callback: Callable[[list[dict[str, Any]]], Awaitable[None]],
    ) -> None:
        """Initialize the sequence batcher.

        Args:
            batch_delay: Time in seconds to wait before sending batched operations
            send_callback: Async function to call with batched operation nodes

        """
        self._batch_delay = batch_delay
        self._send_callback = send_callback

        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._batch_pending = False
        self._tasks: set[asyncio.Task] = set()

    async def enqueue(self, operation_node: dict[str, Any]) -> None:
        """Add an operation node to the batch queue.

        Args:
            operation_node: The operation node to enqueue

        """
        async with self._lock:
            self._buffer.append(operation_node)

            if not self._batch_pending:
                self._batch_pending = True
                task = asyncio.create_task(self._process_batch())
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    async def _process_batch(self) -> None:
        """Wait for batch delay, then send all accumulated operations."""
        await asyncio.sleep(self._batch_delay)

        async with self._lock:
            nodes = self._buffer
            self._buffer = []
            self._batch_pending = False

        if nodes:
            _LOGGER.debug("Processing batch of %d sequence operations", len(nodes))
            try:
                await self._send_callback(nodes)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Failed to send batch of %d operations", len(nodes))

    async def flush(self) -> None:
        """Force immediate send of all pending operations."""
        async with self._lock:
            if not self._buffer:
                return

            nodes = self._buffer
            self._buffer = []
            self._batch_pending = False

        _LOGGER.debug("Flushing %d sequence operations", len(nodes))
        try:
            await self._send_callback(nodes)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to flush %d operations", len(nodes))

    async def shutdown(self) -> None:
        """Cancel pending tasks and flush remaining operations."""
        # Cancel pending batch processing
        pending = tuple(self._tasks)
        for task in pending:
            if not task.done():
                task.cancel()

        # Wait for cancellations
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            self._tasks.clear()

        # Flush any remaining operations
        if self._buffer:
            await self.flush()
