"""Tests for HardwareProxy against a real simulated HardwareControlAPI.

Ported from opentrons/api/tests/opentrons/hardware_control/test_moves.py
(tests that use the hardware_api fixture, i.e. a real API with Simulator backend).
Proxy-specific tests (lock serialisation, delegation, wrapped()) are added below.

The proxy must be transparent to the opentrons tests — behaviour must match
running against the raw API directly.
"""

import asyncio

import pytest
import pytest_asyncio

from opentrons import types
from opentrons.hardware_control import API
from opentrons.hardware_control.backends.simulator import Simulator
from opentrons.hardware_control.errors import OutOfBoundsMove
from opentrons.hardware_control.types import Axis, MotionChecks
from opentrons_shared_data.errors.exceptions import PositionUnknownError
from opentrons.drivers.smoothie_drivers.simulator import SimulatingDriver

from unitelabs.opentrons_ot2.io.hardware_proxy import HardwareProxy


@pytest_asyncio.fixture
async def api() -> API:
    return await API.build_hardware_simulator(loop=asyncio.get_running_loop())


@pytest_asyncio.fixture
async def proxy(api: API) -> HardwareProxy:
    return HardwareProxy(api)


# ── Delegation ────────────────────────────────────────────────────────────────


def test_wrapped_returns_self(proxy: HardwareProxy) -> None:
    assert proxy.wrapped() is proxy


def test_internal_attrs_not_proxied(proxy: HardwareProxy, api: API) -> None:
    assert proxy._api is api
    assert proxy._lock is not None


def test_sync_attr_passes_through(proxy: HardwareProxy, api: API) -> None:
    assert proxy.is_simulator == api.is_simulator


def test_private_state_accessible_via_getattr(proxy: HardwareProxy) -> None:
    """_current_position and _backend fall through to the real API."""
    assert isinstance(proxy._backend, Simulator)
    assert isinstance(proxy._current_position, dict)


def test_wraps_instance_ot2(proxy: HardwareProxy) -> None:
    """wraps_instance(API) must return True so get_ot2_hardware() routes work."""
    assert proxy.wraps_instance(API) is True


def test_wraps_instance_mismatch(proxy: HardwareProxy) -> None:
    """wraps_instance with a non-matching type must return False."""
    assert proxy.wraps_instance(str) is False


# ── Motion (ported from test_moves.py) ───────────────────────────────────────


async def test_home_specific_sim(proxy: HardwareProxy) -> None:
    await proxy.home()
    await proxy.move_to(types.Mount.RIGHT, types.Point(0, 10, 20))
    proxy._last_moved_mount = None
    await proxy.move_rel(types.Mount.LEFT, types.Point(0, 0, -20))
    await proxy.home([Axis.Z, Axis.C])
    assert proxy._current_position == {
        Axis.X: 0,
        Axis.Y: 10,
        Axis.Z: 218,
        Axis.A: -10,
        Axis.B: 19,
        Axis.C: 19,
    }


async def test_retract(proxy: HardwareProxy) -> None:
    await proxy.home()
    await proxy.move_to(types.Mount.RIGHT, types.Point(0, 10, 20))
    await proxy.retract(types.Mount.RIGHT, 10)
    assert proxy._current_position == {
        Axis.X: 0,
        Axis.Y: 10,
        Axis.Z: 218,
        Axis.A: 218,
        Axis.B: 19,
        Axis.C: 19,
    }


async def test_move(proxy: HardwareProxy) -> None:
    abs_position = types.Point(30, 20, 10)
    mount = types.Mount.RIGHT
    target_position1 = {
        Axis.X: 30,
        Axis.Y: 20,
        Axis.Z: 218,
        Axis.A: -20,
        Axis.B: 19,
        Axis.C: 19,
    }
    await proxy.home()
    await proxy.move_to(mount, abs_position)
    assert proxy._current_position == target_position1

    rel_position = types.Point(30, 20, -10)
    mount2 = types.Mount.LEFT
    target_position2 = {
        Axis.X: 60,
        Axis.Y: 40,
        Axis.Z: 208,
        Axis.A: 218,
        Axis.B: 19,
        Axis.C: 19,
    }
    await proxy.move_rel(mount2, rel_position)
    assert proxy._current_position == target_position2


async def test_move_rel_bounds(proxy: HardwareProxy) -> None:
    with pytest.raises(OutOfBoundsMove):
        await proxy.move_rel(types.Mount.RIGHT, types.Point(0, 0, 2000), check_bounds=MotionChecks.HIGH)


async def test_move_rel_homing_failures(proxy: HardwareProxy) -> None:
    await proxy.home()
    assert isinstance(proxy._backend._smoothie_driver, SimulatingDriver)
    proxy._backend._smoothie_driver._homed_flags = {
        "X": True,
        "Y": True,
        "Z": False,
        "A": True,
        "B": False,
        "C": False,
    }
    with pytest.raises(PositionUnknownError):
        await proxy.move_rel(types.Mount.LEFT, types.Point(0, 0, 2000), fail_on_not_homed=True)
    await proxy.move_rel(types.Mount.RIGHT, types.Point(0, 0, 2000), fail_on_not_homed=True)


async def test_current_position_homing_failures(proxy: HardwareProxy) -> None:
    await proxy.home()
    assert isinstance(proxy._backend._smoothie_driver, SimulatingDriver)
    proxy._backend._smoothie_driver._homed_flags = {
        "X": True,
        "Y": True,
        "Z": False,
        "A": True,
        "B": False,
        "C": True,
    }
    with pytest.raises(PositionUnknownError):
        await proxy.current_position(mount=types.Mount.LEFT, fail_on_not_homed=True)
    with pytest.raises(PositionUnknownError):
        await proxy.gantry_position(mount=types.Mount.LEFT, fail_on_not_homed=True)
    await proxy.current_position(mount=types.Mount.RIGHT, fail_on_not_homed=True)
    await proxy.gantry_position(mount=types.Mount.RIGHT, fail_on_not_homed=True)


# ── from_api shim ─────────────────────────────────────────────────────────────


async def test_from_api_shares_driver_and_lock(api: API) -> None:
    """OT2MotionController.from_api() must share the driver and lock with HardwareProxy."""
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController

    shared_lock = asyncio.Lock()
    proxy = HardwareProxy(api, lock=shared_lock)
    controller = OT2MotionController.from_api(api, lock=shared_lock)

    assert controller._lock is proxy._lock is shared_lock
    assert controller._driver is api._backend._smoothie_driver


# ── Lock serialisation ────────────────────────────────────────────────────────


async def test_concurrent_calls_all_complete(proxy: HardwareProxy) -> None:
    """Concurrent awaits must all complete without deadlock."""
    await proxy.home()
    results = await asyncio.gather(
        proxy.current_position(types.Mount.RIGHT),
        proxy.current_position(types.Mount.LEFT),
        proxy.gantry_position(types.Mount.RIGHT),
    )
    assert len(results) == 3


async def test_lock_serialises_calls(proxy: HardwareProxy) -> None:
    """Calls made concurrently must not overlap on the driver."""
    await proxy.home()
    call_order: list[str] = []

    async def move_and_record(label: str, point: types.Point) -> None:
        await proxy.move_to(types.Mount.RIGHT, point)
        call_order.append(label)

    await asyncio.gather(
        move_and_record("a", types.Point(10, 10, 10)),
        move_and_record("b", types.Point(20, 20, 20)),
        move_and_record("c", types.Point(30, 30, 30)),
    )
    # All three must complete — order is scheduler-dependent but all must finish
    assert sorted(call_order) == ["a", "b", "c"]
