"""End-to-end gRPC integration tests for the OT-2 connector in simulate mode.

Spins up a real SiLA gRPC server on a dynamic port and makes real gRPC calls
over the wire using the server's own protobuf codec. Confirms the full chain:
  gRPC channel → SiLA server → MotionControlFeature → OT2MotionController → SmoothieDriver

The server's protobuf object is reused client-side to encode requests and decode
responses — no separate client SDK required.

``pb.decode()`` returns a single-entry dict whose value is the native Python
dataclass returned by the feature method.  The client wrapper extracts that
value so callers get the dataclass directly.
"""

import typing

import grpc
import grpc.aio
import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.features.motion_control import Axis, AxisPosition, HomedFlags, HomeResult, Mount

_PKG = "sila2.ca.accelerationconsortium.robots.motioncontrolfeature.v1"
_SERVICE = f"{_PKG}.MotionControlFeature"

# The simulator reports nominal homed coordinates (Y=353), but a real robot
# reports its firmware-queried homed position, which can differ slightly per
# machine (e.g. Y=350). Position assertions therefore compare against the
# `homed_position` fixture (captured live) rather than a hardcoded constant.

T = typing.TypeVar("T")


class _MotionClient:
    """Raw gRPC client for MotionControlFeature.

    Commands encode ``_Parameters`` via the server's protobuf object and decode
    ``_Responses`` the same way.  Properties (``Get_*``) have no registered
    ``_Parameters`` message, so they receive an empty-byte request.

    ``pb.decode`` returns ``{'response_0': <dataclass>}`` or
    ``{'TypeName': <dataclass>}``.  ``_single`` extracts the dataclass value.
    """

    def __init__(self, channel: grpc.aio.Channel, pb: object) -> None:
        self._ch = channel
        self._pb = pb

    @staticmethod
    def _single(decoded: dict, expected_type: type[T]) -> T:
        """Extract the single value from a decoded response dict."""
        value = next(iter(decoded.values()))
        assert isinstance(value, expected_type), (
            f"Expected {expected_type.__name__}, got {type(value).__name__}: {value}"
        )
        return value

    async def _call(self, method: str, params: dict | None = None) -> dict:
        req = await self._pb.encode(f"{_PKG}.{method}_Parameters", params or {})
        stub = self._ch.unary_unary(f"/{_SERVICE}/{method}")
        resp_bytes = await stub(req)
        return await self._pb.decode(f"{_PKG}.{method}_Responses", resp_bytes)

    async def _get_property(self, name: str) -> dict:
        stub = self._ch.unary_unary(f"/{_SERVICE}/{name}")
        resp_bytes = await stub(b"")
        return await self._pb.decode(f"{_PKG}.{name}_Responses", resp_bytes)

    async def home(self, axes: str = "XYZABC") -> HomeResult:
        """Home axes and return the HomeResult dataclass."""
        return self._single(await self._call("Home", {"axes": axes}), HomeResult)

    async def get_position(self) -> AxisPosition:
        """Return the current AxisPosition dataclass."""
        return self._single(await self._call("GetPosition"), AxisPosition)

    async def move_axis(self, axis: Axis, position: float) -> AxisPosition:
        """Move a single axis; returns AxisPosition dataclass."""
        return self._single(
            await self._call("MoveAxis", {"axis": axis, "position": position, "speed": 0.0}),
            AxisPosition,
        )

    async def move_relative_axis(self, axis: Axis, delta: float) -> AxisPosition:
        """Move a single axis relative; returns AxisPosition dataclass."""
        return self._single(
            await self._call("MoveRelativeAxis", {"axis": axis, "delta": delta, "speed": 0.0}),
            AxisPosition,
        )

    async def get_firmware_version(self) -> str:
        """Return the firmware version string."""
        return next(iter((await self._call("GetFirmwareVersion")).values()))

    async def reset_from_error(self) -> HomedFlags:
        """Clear alarm state; returns HomedFlags dataclass."""
        return self._single(await self._call("ResetFromError"), HomedFlags)

    async def aspirate(self, mount: Mount, volume_ul: float, ul_per_mm: float, flow_rate_ul_s: float) -> AxisPosition:
        """Aspirate volume_ul from mount; returns AxisPosition."""
        return self._single(
            await self._call(
                "Aspirate",
                {"mount": mount, "volume_ul": volume_ul, "ul_per_mm": ul_per_mm, "flow_rate_ul_s": flow_rate_ul_s},
            ),
            AxisPosition,
        )

    async def dispense(self, mount: Mount, volume_ul: float, ul_per_mm: float, flow_rate_ul_s: float) -> AxisPosition:
        """Dispense volume_ul from mount; returns AxisPosition."""
        return self._single(
            await self._call(
                "Dispense",
                {"mount": mount, "volume_ul": volume_ul, "ul_per_mm": ul_per_mm, "flow_rate_ul_s": flow_rate_ul_s},
            ),
            AxisPosition,
        )

    async def get_is_simulating(self) -> bool:
        """Return the is-simulating boolean."""
        return next(iter((await self._get_property("Get_IsSimulating")).values()))

    async def get_homed_flags(self) -> HomedFlags:
        """Return the HomedFlags dataclass."""
        return self._single(await self._get_property("Get_HomedFlags"), HomedFlags)


@pytest_asyncio.fixture
async def client(sila_channel) -> _MotionClient:
    """Yield a MotionControlFeature gRPC client (local sim or --robot target)."""
    channel, pb = sila_channel
    return _MotionClient(channel, pb)


@pytest_asyncio.fixture
async def homed_position(client: _MotionClient) -> AxisPosition:
    """Home the robot and return its actual homed position.

    Nominal coordinates in the simulator; the real firmware-reported position on
    hardware. Position tests compare against this so they hold on both backends.
    """
    return (await client.home()).position


# ── Simulation flag and firmware ──────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.simulator_only
async def test_firmware_version_is_virtual(client: _MotionClient) -> None:
    """GetFirmwareVersion returns the simulator sentinel string over the wire."""
    assert await client.get_firmware_version() == "Virtual Smoothie"


@pytest.mark.asyncio
@pytest.mark.simulator_only
async def test_is_simulating_is_true(client: _MotionClient) -> None:
    """Get_IsSimulating property returns True in simulate mode."""
    assert await client.get_is_simulating() is True


# ── Home ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_home_returns_homed_axes_string(client: _MotionClient) -> None:
    """Home XYZABC echoes the axes string in the response."""
    result = await client.home()
    assert result.homed_axes == "XYZABC"


@pytest.mark.asyncio
async def test_home_returns_homed_position(client: _MotionClient, homed_position: AxisPosition) -> None:
    """Home returns reproducible homed coordinates (matches a prior home)."""
    result = await client.home()
    assert result.position.x == pytest.approx(homed_position.x)
    assert result.position.y == pytest.approx(homed_position.y)
    assert result.position.z == pytest.approx(homed_position.z)
    assert result.position.a == pytest.approx(homed_position.a)


@pytest.mark.asyncio
async def test_home_sets_all_homed_flags(client: _MotionClient) -> None:
    """Home sets all six axis homed flags to True."""
    await client.home()
    flags = await client.get_homed_flags()
    assert all([flags.x, flags.y, flags.z, flags.a, flags.b, flags.c])


@pytest.mark.asyncio
@pytest.mark.simulator_only
async def test_home_subset_only_sets_requested_flags(client: _MotionClient) -> None:
    """Homing only BC leaves X, Y, Z, A flags False.

    Simulator-only: assumes a cold (un-homed) starting state. On real hardware
    homed flags reflect the firmware's actual state (GCODE.HOMING_STATUS) and
    stay set from any prior home — homing a subset does not un-home other axes.
    """
    await client.home(axes="BC")
    flags = await client.get_homed_flags()
    assert flags.b is True
    assert flags.c is True
    assert flags.x is False
    assert flags.y is False


# ── Position tracking ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_position_reflects_home(client: _MotionClient, homed_position: AxisPosition) -> None:
    """GetPosition returns the homed coordinates after a full home."""
    pos = await client.get_position()
    assert pos.x == pytest.approx(homed_position.x)
    assert pos.y == pytest.approx(homed_position.y)


@pytest.mark.asyncio
async def test_move_axis_changes_target_axis(client: _MotionClient) -> None:
    """MoveAxis X to 75 mm produces X≈75 in the returned position."""
    await client.home()
    result = await client.move_axis(axis=Axis.X, position=75.0)
    assert result.x == pytest.approx(75.0)


@pytest.mark.asyncio
async def test_move_axis_does_not_change_other_axes(client: _MotionClient, homed_position: AxisPosition) -> None:
    """MoveAxis X leaves Y at its homed value."""
    result = await client.move_axis(axis=Axis.X, position=75.0)
    assert result.y == pytest.approx(homed_position.y)


@pytest.mark.asyncio
async def test_move_relative_axis_accumulates(client: _MotionClient, homed_position: AxisPosition) -> None:
    """Two MoveRelativeAxis Y -20 mm moves produce Y = homed_Y - 40 mm."""
    await client.move_relative_axis(axis=Axis.Y, delta=-20.0)
    result = await client.move_relative_axis(axis=Axis.Y, delta=-20.0)
    assert result.y == pytest.approx(homed_position.y - 40.0)


# ── Error reset ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.simulator_only
async def test_reset_from_error_clears_homed_flags(client: _MotionClient) -> None:
    """ResetFromError clears the homed flags set by a prior Home call.

    Simulator-only: in simulation update_homed_flags() resets every flag to
    False. On real hardware M999 does not un-home the carriages, and
    update_homed_flags() re-queries the firmware (GCODE.HOMING_STATUS), which
    still reports the axes homed — so the flags correctly remain True.
    """
    await client.home()
    flags_before = await client.get_homed_flags()
    assert all([flags_before.x, flags_before.y, flags_before.z])

    await client.reset_from_error()

    flags_after = await client.get_homed_flags()
    assert not any([flags_after.x, flags_after.y, flags_after.z, flags_after.a, flags_after.b, flags_after.c])


# ── Aspirate / Dispense ───────────────────────────────────────────────────────

# ul_per_mm of 1.0 makes the math trivial: volume_ul == distance_mm.
_UL_PER_MM = 1.0
_FLOW_RATE = 10.0  # µL/s


@pytest.mark.asyncio
async def test_aspirate_decreases_plunger_position(client: _MotionClient) -> None:
    """Aspirate moves the left plunger (B) down by volume_ul / ul_per_mm."""
    await client.home()
    pos_before = await client.get_position()
    volume = 5.0
    pos_after = await client.aspirate(Mount.LEFT, volume, _UL_PER_MM, _FLOW_RATE)
    assert pos_after.b == pytest.approx(pos_before.b - volume / _UL_PER_MM)


@pytest.mark.asyncio
async def test_dispense_restores_plunger_position(client: _MotionClient) -> None:
    """Dispense after aspirate returns the left plunger (B) to its original position."""
    await client.home()
    pos_before = await client.get_position()
    volume = 5.0
    await client.aspirate(Mount.LEFT, volume, _UL_PER_MM, _FLOW_RATE)
    pos_after = await client.dispense(Mount.LEFT, volume, _UL_PER_MM, _FLOW_RATE)
    assert pos_after.b == pytest.approx(pos_before.b)


@pytest.mark.asyncio
async def test_aspirate_right_mount_moves_c_axis(client: _MotionClient) -> None:
    """Aspirate on the right mount moves axis C, not B."""
    await client.home()
    pos_before = await client.get_position()
    volume = 3.0
    pos_after = await client.aspirate(Mount.RIGHT, volume, _UL_PER_MM, _FLOW_RATE)
    assert pos_after.c == pytest.approx(pos_before.c - volume / _UL_PER_MM)
    assert pos_after.b == pytest.approx(pos_before.b)


@pytest.mark.asyncio
async def test_aspirate_does_not_move_gantry(client: _MotionClient) -> None:
    """Aspirate leaves X, Y, Z, A axes unchanged."""
    await client.home()
    pos_before = await client.get_position()
    pos_after = await client.aspirate(Mount.LEFT, 5.0, _UL_PER_MM, _FLOW_RATE)
    assert pos_after.x == pytest.approx(pos_before.x)
    assert pos_after.y == pytest.approx(pos_before.y)
    assert pos_after.z == pytest.approx(pos_before.z)
    assert pos_after.a == pytest.approx(pos_before.a)
