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

    async def prepare_for_aspirate(self, mount: Mount, bottom_position_mm: float) -> AxisPosition:
        """Move the plunger to its bottom position; returns AxisPosition."""
        return self._single(
            await self._call(
                "PrepareForAspirate",
                {"mount": mount, "bottom_position_mm": bottom_position_mm},
            ),
            AxisPosition,
        )

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

    async def move_to(self, position: dict[str, float], speed: float = 0.0) -> AxisPosition:
        """Move all axes to an absolute position; returns the queried AxisPosition."""
        return self._single(await self._call("MoveTo", {"position": position, "speed": speed}), AxisPosition)

    async def move_to_unverified(self, position: dict[str, float], speed: float = 0.0) -> AxisPosition:
        """Move without the trailing firmware position query; returns the commanded AxisPosition."""
        return self._single(
            await self._call("MoveToUnverified", {"position": position, "speed": speed}),
            AxisPosition,
        )

    async def move_through(self, waypoints: list[dict[str, float]]) -> AxisPosition:
        """Execute a batched waypoint sequence; returns the final AxisPosition."""
        return self._single(await self._call("MoveThrough", {"waypoints": waypoints}), AxisPosition)

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


# ── MoveToUnverified / MoveThrough ────────────────────────────────────────────


def _axes_dict(position: AxisPosition, **overrides: float) -> dict[str, float]:
    axes = {ax: float(getattr(position, ax)) for ax in "xyzabc"}
    axes.update(overrides)
    return axes


@pytest.mark.asyncio
async def test_move_to_unverified_returns_commanded_target(client: _MotionClient, homed_position: AxisPosition) -> None:
    """MoveToUnverified echoes the commanded target; GetPosition then confirms it."""
    target = _axes_dict(homed_position, x=75.0, z=100.0)
    result = await client.move_to_unverified(target)
    assert result.x == pytest.approx(75.0)
    assert result.z == pytest.approx(100.0)
    verified = await client.get_position()
    assert verified.x == pytest.approx(75.0)
    assert verified.z == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_move_through_lands_on_final_waypoint(client: _MotionClient, homed_position: AxisPosition) -> None:
    """A wiggle + rise batch over the wire ends at the last waypoint's position."""
    waypoints = [
        _axes_dict(homed_position, x=75.0, y=300.0, z=100.0, speed=0.0),
        _axes_dict(homed_position, x=75.5, y=300.0, z=100.0, speed=25.0),
        _axes_dict(homed_position, x=74.5, y=300.0, z=100.0, speed=25.0),
        _axes_dict(homed_position, x=75.0, y=300.0, z=120.0, speed=0.0),
    ]
    result = await client.move_through(waypoints)
    assert result.x == pytest.approx(75.0)
    assert result.y == pytest.approx(300.0)
    assert result.z == pytest.approx(120.0)


@pytest.mark.asyncio
async def test_move_through_matches_individual_move_to_calls(
    client: _MotionClient, homed_position: AxisPosition
) -> None:
    """The batch's final position equals the same waypoints issued as discrete MoveTo calls."""
    targets = [
        _axes_dict(homed_position, x=80.0, y=300.0),
        _axes_dict(homed_position, x=80.3, y=300.0),
        _axes_dict(homed_position, x=79.7, y=300.0, z=110.0),
    ]
    for target in targets:
        discrete = await client.move_to(target)

    await client.home()
    batched = await client.move_through([dict(t, speed=0.0) for t in targets])
    assert batched.x == pytest.approx(discrete.x)
    assert batched.y == pytest.approx(discrete.y)
    assert batched.z == pytest.approx(discrete.z)


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
# A realistic plunger `bottom` (P1000 GEN2 = -18.5 mm); comes from the client's
# pipette config in production, same ownership as ul_per_mm.
_PLUNGER_BOTTOM = -18.5


@pytest.mark.asyncio
async def test_prepare_for_aspirate_moves_plunger_to_bottom(client: _MotionClient) -> None:
    """PrepareForAspirate places the left plunger (B) at the given bottom position."""
    await client.home()
    pos = await client.prepare_for_aspirate(Mount.LEFT, _PLUNGER_BOTTOM)
    assert pos.b == pytest.approx(_PLUNGER_BOTTOM)


@pytest.mark.asyncio
async def test_aspirate_raises_plunger_from_bottom(client: _MotionClient) -> None:
    """Aspirate retracts the left plunger (B) UP from bottom by volume_ul / ul_per_mm
    (Opentrons semantics: plunger up = liquid drawn in)."""
    await client.home()
    await client.prepare_for_aspirate(Mount.LEFT, _PLUNGER_BOTTOM)
    volume = 5.0
    pos_after = await client.aspirate(Mount.LEFT, volume, _UL_PER_MM, _FLOW_RATE)
    assert pos_after.b == pytest.approx(_PLUNGER_BOTTOM + volume / _UL_PER_MM)


@pytest.mark.asyncio
async def test_dispense_restores_plunger_position(client: _MotionClient) -> None:
    """Dispense after aspirate presses the left plunger (B) back down to bottom."""
    await client.home()
    await client.prepare_for_aspirate(Mount.LEFT, _PLUNGER_BOTTOM)
    volume = 5.0
    await client.aspirate(Mount.LEFT, volume, _UL_PER_MM, _FLOW_RATE)
    pos_after = await client.dispense(Mount.LEFT, volume, _UL_PER_MM, _FLOW_RATE)
    assert pos_after.b == pytest.approx(_PLUNGER_BOTTOM)


@pytest.mark.asyncio
async def test_aspirate_right_mount_moves_c_axis(client: _MotionClient) -> None:
    """Aspirate on the right mount moves axis C, not B."""
    await client.home()
    pos_homed = await client.get_position()
    await client.prepare_for_aspirate(Mount.RIGHT, _PLUNGER_BOTTOM)
    volume = 3.0
    pos_after = await client.aspirate(Mount.RIGHT, volume, _UL_PER_MM, _FLOW_RATE)
    assert pos_after.c == pytest.approx(_PLUNGER_BOTTOM + volume / _UL_PER_MM)
    assert pos_after.b == pytest.approx(pos_homed.b)


@pytest.mark.asyncio
async def test_aspirate_does_not_move_gantry(client: _MotionClient) -> None:
    """Aspirate leaves X, Y, Z, A axes unchanged."""
    await client.home()
    pos_before = await client.get_position()
    await client.prepare_for_aspirate(Mount.LEFT, _PLUNGER_BOTTOM)
    pos_after = await client.aspirate(Mount.LEFT, 5.0, _UL_PER_MM, _FLOW_RATE)
    assert pos_after.x == pytest.approx(pos_before.x)
    assert pos_after.y == pytest.approx(pos_before.y)
    assert pos_after.z == pytest.approx(pos_before.z)
    assert pos_after.a == pytest.approx(pos_before.a)
