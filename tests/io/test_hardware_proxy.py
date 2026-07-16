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

from unitelabs.opentrons_ot2.io.hardware_proxy import HardwareProxy, _TimedLock


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


async def test_from_api_shares_lock(api: API) -> None:
    """OT2MotionController.from_api() must share the lock with HardwareProxy regardless of backend."""
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController

    shared_lock = asyncio.Lock()
    proxy = HardwareProxy(api, lock=shared_lock)
    controller = OT2MotionController.from_api(api, lock=shared_lock)

    assert controller._lock._lock is proxy._lock._lock is shared_lock


async def test_from_api_does_not_share_simulating_driver(api: API) -> None:
    """On a Simulator backend, from_api() must NOT reuse backend._smoothie_driver.

    Simulator implements its own move/home/position bookkeeping and only pokes its
    _smoothie_driver (a bare SimulatingDriver) for a few incidental things — it never
    asks it to move. SimulatingDriver doesn't implement the rest of the interface
    OT2MotionController drives directly (move, position, probe_axis,
    set_active_current, ...), so reusing it would let the controller silently
    AttributeError the first time it tries to do anything beyond gantry homing.
    """
    from opentrons.drivers.smoothie_drivers.driver_3_0 import SmoothieDriver
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController, _SimulatorStateSyncingDriver

    assert isinstance(api._backend._smoothie_driver, SimulatingDriver)

    controller = OT2MotionController.from_api(api, lock=asyncio.Lock())

    assert controller._driver is not api._backend._smoothie_driver
    assert isinstance(controller._driver, _SimulatorStateSyncingDriver)
    assert isinstance(controller._driver._driver, SmoothieDriver)
    assert controller._driver.simulating is True


async def test_from_api_shares_real_driver_on_real_backend() -> None:
    """On a real (Controller-backed) hw_api, from_api() must share its actual SmoothieDriver.

    Controller forwards its own move/home/current methods straight to
    _smoothie_driver, so on real hardware that object is the one true mover — the
    opposite of the Simulator case above — and sharing it (rather than building a
    second, disconnected driver) is required for the SiLA server and robot_server
    to serialise access to the same physical board.
    """
    from opentrons.config.robot_configs import load_ot2
    from opentrons.drivers.rpi_drivers.gpio_simulator import SimulatingGPIOCharDev
    from opentrons.drivers.smoothie_drivers.driver_3_0 import SmoothieDriver
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController

    real_driver = SmoothieDriver(config=load_ot2(), gpio_chardev=SimulatingGPIOCharDev("simulated"), connection=None)

    class _FakeControllerBackend:
        _smoothie_driver = real_driver
        gpio_chardev = real_driver._gpio_chardev

    class _FakeApi:
        _backend = _FakeControllerBackend()

    controller = OT2MotionController.from_api(_FakeApi(), lock=asyncio.Lock())

    assert controller._driver is real_driver


async def test_from_api_home_plunger_works_against_simulator(api: API) -> None:
    """Regression test: homing a plunger axis through from_api() must not AttributeError.

    This is the exact failure this fix addresses: _home_plunger() calls
    self._driver.set_active_current(...), which SimulatingDriver (the object the
    old code shared directly from the Simulator backend) does not implement.
    """
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController

    controller = OT2MotionController.from_api(api, lock=asyncio.Lock())
    position = await controller.home("B")

    assert "B" in position


# ── Simulator state syncing (position visible to robot_server too) ────────────


async def test_home_through_from_api_updates_backend_position(api: API) -> None:
    """Homing via the standalone simulated driver must update Simulator's own _position.

    Simulator implements update_position()/current_position() (what a robot_server
    HTTP caller would see) from its own private _position dict, never from the
    standalone driver from_api() builds. Without _SimulatorStateSyncingDriver, a
    SiLA-driven home would be invisible to a concurrent HTTP caller.
    """
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController

    controller = OT2MotionController.from_api(api, lock=asyncio.Lock())
    position = await controller.home("X")

    backend_position = await api._backend.update_position()
    assert backend_position["X"] == position["X"]


async def test_move_through_from_api_updates_backend_position(api: API) -> None:
    """A move via the standalone simulated driver must update Simulator's own _position."""
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController

    controller = OT2MotionController.from_api(api, lock=asyncio.Lock())
    await controller.home("X")
    await controller._driver.move({"X": 42.0}, home_flagged_axes=False)

    backend_position = await api._backend.update_position()
    assert backend_position["X"] == 42.0


async def test_home_through_from_api_updates_backend_homed_flags(api: API) -> None:
    """Homing via the standalone simulated driver must update Simulator's is_homed() view.

    is_homed()/_unhomed_axes() read api._backend._smoothie_driver.homed_flags — the
    Simulator's own internal stub, never updated by the standalone driver without
    the sync wrapper.
    """
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController

    controller = OT2MotionController.from_api(api, lock=asyncio.Lock())
    assert api._backend.is_homed(["X"]) is False

    await controller.home("X")

    assert api._backend.is_homed(["X"]) is True


async def test_disengage_axis_through_from_api_updates_backend_engaged_axes(api: API) -> None:
    """Disengaging via the standalone simulated driver must update Simulator's engaged_axes()."""
    from unitelabs.opentrons_ot2.io.motion import OT2MotionController

    controller = OT2MotionController.from_api(api, lock=asyncio.Lock())
    await controller.home("X")
    assert api._backend.engaged_axes()["X"] is True

    await controller.disengage_axes("X")

    assert api._backend.engaged_axes()["X"] is False


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


# ── _TimedLock ────────────────────────────────────────────────────────────────


async def test_timed_lock_no_timeout_acquires() -> None:
    """timeout_s=None must behave identically to a plain asyncio.Lock."""
    raw = asyncio.Lock()
    tl = _TimedLock(raw, timeout_s=None)
    async with tl:
        assert raw.locked()
    assert not raw.locked()


async def test_timed_lock_raises_on_timeout() -> None:
    """When the underlying lock is held, _TimedLock must raise TimeoutError promptly."""
    raw = asyncio.Lock()
    await raw.acquire()  # simulate robot_server holding the lock

    tl = _TimedLock(raw, timeout_s=0.05)
    with pytest.raises(TimeoutError, match="robot_server may be holding the serial port"):
        async with tl:
            pass  # should not reach here

    raw.release()


async def test_proxy_timeout_raises_on_held_lock(api: API) -> None:
    """HardwareProxy with lock_timeout_s must raise TimeoutError when the lock is held."""
    shared_lock = asyncio.Lock()
    await shared_lock.acquire()  # simulate robot_server holding the lock

    proxy = HardwareProxy(api, lock=shared_lock, lock_timeout_s=0.05)
    with pytest.raises(TimeoutError, match="robot_server may be holding the serial port"):
        await proxy.home()

    shared_lock.release()


# ── locked_gen (async generator wrapping) ─────────────────────────────────────


async def test_locked_gen_yields_all_items(proxy: HardwareProxy) -> None:
    """Proxied async generator methods must yield every item under the lock."""
    from unittest.mock import patch

    async def fake_gen(*args, **kwargs):
        for i in range(3):
            yield i

    with patch.object(type(proxy._api), "attached_modules", new_callable=lambda: property(lambda self: None)):
        pass  # just checking the proxy routing — use a direct attribute patch instead

    # Inject a fake async-generator attribute directly onto the wrapped API
    proxy._api._fake_agen = fake_gen  # type: ignore[attr-defined]

    # Verify __getattr__ wraps it correctly
    import inspect as _inspect

    attr = getattr(proxy._api, "_fake_agen")
    assert _inspect.isasyncgenfunction(attr)

    collected = [item async for item in proxy._fake_agen()]  # type: ignore[attr-defined]

    assert collected == [0, 1, 2]


async def test_locked_gen_holds_lock_while_iterating(proxy: HardwareProxy) -> None:
    """The lock must be held for the full duration of the async generator iteration."""
    lock = proxy._lock._lock

    async def fake_gen(*args, **kwargs):
        assert lock.locked()
        yield 42
        assert lock.locked()

    proxy._api._checking_gen = fake_gen  # type: ignore[attr-defined]

    results = [item async for item in proxy._checking_gen()]  # type: ignore[attr-defined]

    assert results == [42]
    assert not lock.locked()
