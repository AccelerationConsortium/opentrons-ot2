"""
Locking proxy for opentrons HardwareControlAPI.

Wraps a HardwareControlAPI instance with an asyncio.Lock so that concurrent
callers (SiLA2 gRPC server and opentrons HTTP server) cannot interleave serial
commands to the Smoothie.

See plan/serial_port_sharing.md for why this approach was chosen over a TCP
proxy or separate-process architecture.
"""

import asyncio
import functools
import inspect

from opentrons.hardware_control import HardwareControlAPI


class HardwareProxy:
    """
    Serialises concurrent async callers against a shared HardwareControlAPI.

    Uses __getattr__ to delegate every attribute access to the wrapped API.
    Async methods are transparently wrapped with an asyncio.Lock so that only
    one call is in-flight on the serial port at a time. Sync attributes and
    properties are passed through without locking — none of them send serial
    bytes directly.

    pause() and resume() are sync methods that schedule internal coroutines via
    run_coroutine_threadsafe; they bypass the lock but do not touch the serial
    port directly, so the gap is safe (see plan/inprocess_server_plan.md).
    """

    _api: HardwareControlAPI
    _lock: asyncio.Lock

    def __init__(self, api: HardwareControlAPI) -> None:
        object.__setattr__(self, "_api", api)
        object.__setattr__(self, "_lock", asyncio.Lock())

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._api, name, value)

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._api, name)

        if inspect.isasyncgenfunction(attr):

            @functools.wraps(attr)
            async def locked_gen(*args: object, **kwargs: object) -> object:
                async with self._lock:
                    async for item in attr(*args, **kwargs):
                        yield item

            return locked_gen

        if inspect.iscoroutinefunction(attr):

            @functools.wraps(attr)
            async def locked(*args: object, **kwargs: object) -> object:
                async with self._lock:
                    return await attr(*args, **kwargs)

            return locked

        return attr

    def wrapped(self) -> "HardwareProxy":
        """Return self — satisfies robot-server's ThreadManager.wrapped() call."""
        return self
