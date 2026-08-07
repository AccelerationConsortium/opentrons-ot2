"""Simulation-mode tests for MotionControlFeature.

Uses a real SmoothieDriver(connection=None) — no mocks. Exercises the actual
driver state machine through the feature layer to confirm the full
feature → controller → driver chain is wired correctly.

What is testable in simulation (driver maintains internal state):
  - home() updates homed_flags and returns homed position
  - get_position() reflects move/home calls
  - move_to() / move_axis() / move_relative_axis() update position
  - probe_axis() returns current position (no physical probe in sim)
  - get_firmware_version() returns "Virtual Smoothie"
  - reset_from_error() clears homed flags
  - is_simulating is True

What is NOT testable in simulation (driver no-ops):
  - pause() / resume() — do nothing, run_flag not affected
  - smoothie_reset() — GPIO no-op
  - emergency_stop() — sets internal flag only, no actual halt
"""

import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.features.motion_control import (
    Axis,
    AxisPosition,
    MotionControlFeature,
    Mount,
    OutOfBoundsError,
    PlungerAxisNotSupportedError,
    Waypoint,
)
from unitelabs.opentrons_ot2.io.motion import OT2MotionController

# Real homed positions reported by the Smoothie firmware defaults.
HOMED_POSITION = {"X": 418.0, "Y": 353.0, "Z": 218.0, "A": 218.0, "B": 19.0, "C": 19.0}

ALL_AXES = "XYZABC"


@pytest_asyncio.fixture
async def feature() -> MotionControlFeature:
    controller = await OT2MotionController.build(simulate=True)
    return MotionControlFeature(controller)


@pytest_asyncio.fixture
async def homed_feature(feature: MotionControlFeature) -> MotionControlFeature:
    """Feature with all axes already homed."""
    await feature.home(ALL_AXES)
    return feature


def _with(position: AxisPosition, **overrides: float) -> AxisPosition:
    axes = {ax: getattr(position, ax) for ax in "xyzabc"}
    axes.update(overrides)
    return AxisPosition(**axes)


def _waypoint(position: AxisPosition, speed: float = 0.0, **overrides: float) -> Waypoint:
    axes = {ax: getattr(position, ax) for ax in "xyzabc"}
    axes.update(overrides)
    return Waypoint(speed=speed, **axes)


def _assert_positions_equal(actual: AxisPosition, expected: AxisPosition) -> None:
    for ax in "xyzabc":
        assert getattr(actual, ax) == pytest.approx(getattr(expected, ax)), f"axis {ax}"


# ── Plunger bounds: the plunger axes travel negative (down to drop-tip) ────────


async def test_move_to_allows_negative_plunger(homed_feature: MotionControlFeature):
    """The plunger axes (B, C) accept negative targets (e.g. bottom / blow-out)."""
    pos = await homed_feature.get_position()
    result = await homed_feature.move_to(_with(pos, c=-30.0))
    assert result.c == pytest.approx(-30.0)


async def test_move_to_rejects_plunger_below_floor(homed_feature: MotionControlFeature):
    """A plunger target below the software floor (-37 mm) is rejected."""
    pos = await homed_feature.get_position()
    with pytest.raises(OutOfBoundsError):
        await homed_feature.move_to(_with(pos, c=-50.0))


async def test_move_to_rejects_negative_gantry(homed_feature: MotionControlFeature):
    """X/Y (deck-plane) still reject negative targets."""
    pos = await homed_feature.get_position()
    with pytest.raises(OutOfBoundsError):
        await homed_feature.move_to(_with(pos, x=-1.0))


async def test_move_to_allows_negative_mount_vertical_axes(homed_feature: MotionControlFeature):
    """Z/A (mount-vertical) accept negative targets -- no synthetic software floor.

    Opentrons provides no fixed minimum for these two axes (only a homed/top
    position), and Protocol Engine itself does not reject negative machine
    positions for them: verified by replaying an identical moveToWell request
    through the real robot-server HTTP API, which executed a machine position
    of -21.44 mm without error. The physical limit switches are the real
    safety boundary, same as Protocol Engine relies on.
    """
    pos = await homed_feature.get_position()
    result = await homed_feature.move_to(_with(pos, z=-10.0, a=-10.0))
    assert result.z == pytest.approx(-10.0)
    assert result.a == pytest.approx(-10.0)


# ── Plunger direction: aspirate retracts UP from bottom, dispense presses DOWN ─

_PLUNGER_BOTTOM = -18.5  # P1000 GEN2 bottom; supplied by the client in production


async def test_prepare_aspirate_dispense_round_trip(homed_feature: MotionControlFeature):
    """Opentrons plunger semantics end-to-end: prepare places the plunger at
    bottom, aspirate retracts it UP by volume/ul_per_mm, dispense presses it
    back DOWN to bottom."""
    pos = await homed_feature.prepare_for_aspirate(Mount.LEFT, _PLUNGER_BOTTOM)
    assert pos.b == pytest.approx(_PLUNGER_BOTTOM)

    pos = await homed_feature.aspirate(Mount.LEFT, 5.0, 1.0, 10.0)
    assert pos.b == pytest.approx(_PLUNGER_BOTTOM + 5.0)

    pos = await homed_feature.dispense(Mount.LEFT, 5.0, 1.0, 10.0)
    assert pos.b == pytest.approx(_PLUNGER_BOTTOM)


async def test_aspirate_without_prepare_is_rejected(homed_feature: MotionControlFeature):
    """After home the plunger sits retracted at top (B=19): aspirating (an UP
    move) from there must be rejected as out of bounds, not silently run the
    transfer backwards. This is the guard for callers that skip
    PrepareForAspirate."""
    with pytest.raises(OutOfBoundsError):
        await homed_feature.aspirate(Mount.LEFT, 5.0, 1.0, 10.0)


async def test_plunger_floor_is_dynamic_from_attached_pipette():
    """The plunger floor comes from the attached pipette's drop-tip, not a constant."""
    from opentrons.hardware_control import API
    from opentrons.types import Mount as OTMount

    hw = await API.build_hardware_simulator(
        attached_instruments={OTMount.RIGHT: {"model": "p300_multi_v2.1", "id": "r"}},
    )
    try:
        controller = await OT2MotionController.build(simulate=True)
        controller._hw_api = hw
        feature = MotionControlFeature(controller)
        bounds = {b.axis.value: b.min_mm for b in feature.axis_bounds()}
        assert bounds["C"] == pytest.approx(-33.4)  # p300_multi drop-tip (not the -37 fallback)
    finally:
        await hw.clean_up()


# ── Basic state ──────────────────────────────────────────────────────────────


def test_is_simulating(feature: MotionControlFeature):
    assert feature.is_simulating() is True


def test_homed_flags_all_false_before_homing(feature: MotionControlFeature):
    flags = feature.homed_flags()
    assert not any([flags.x, flags.y, flags.z, flags.a, flags.b, flags.c])


# ── Home ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_home_all_axes_returns_homed_position(feature: MotionControlFeature):
    result = await feature.home(ALL_AXES)
    assert result.homed_axes == "XYZABC"
    assert result.position.x == HOMED_POSITION["X"]
    assert result.position.y == HOMED_POSITION["Y"]
    assert result.position.z == HOMED_POSITION["Z"]
    assert result.position.a == HOMED_POSITION["A"]


@pytest.mark.asyncio
async def test_home_sets_all_homed_flags(feature: MotionControlFeature):
    await feature.home(ALL_AXES)
    flags = feature.homed_flags()
    assert all([flags.x, flags.y, flags.z, flags.a, flags.b, flags.c])


@pytest.mark.asyncio
async def test_home_subset_of_axes(feature: MotionControlFeature):
    result = await feature.home("BC")
    assert result.homed_axes == "BC"
    flags = feature.homed_flags()
    assert flags.b and flags.c
    assert not flags.x and not flags.y


# ── Position ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_position_after_home(homed_feature: MotionControlFeature):
    pos = await homed_feature.get_position()
    assert pos.x == HOMED_POSITION["X"]
    assert pos.y == HOMED_POSITION["Y"]


@pytest.mark.asyncio
async def test_move_to_updates_position(homed_feature: MotionControlFeature):
    target = AxisPosition(x=50.0, y=30.0, z=100.0, a=100.0, b=10.0, c=10.0)
    result = await homed_feature.move_to(position=target)
    assert result.x == pytest.approx(50.0)
    assert result.y == pytest.approx(30.0)
    assert result.z == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_move_axis_updates_single_axis(homed_feature: MotionControlFeature):
    result = await homed_feature.move_axis(axis=Axis.X, position=75.0)
    assert result.x == pytest.approx(75.0)
    assert result.y == HOMED_POSITION["Y"]


@pytest.mark.asyncio
async def test_move_relative_axis_updates_position(homed_feature: MotionControlFeature):
    before = await homed_feature.get_position()
    result = await homed_feature.move_relative_axis(axis=Axis.X, delta=-10.0)
    assert result.x == pytest.approx(before.x - 10.0)
    assert result.y == pytest.approx(before.y)


@pytest.mark.asyncio
async def test_move_relative_axis_accumulates(homed_feature: MotionControlFeature):
    await homed_feature.move_relative_axis(axis=Axis.Y, delta=-20.0)
    result = await homed_feature.move_relative_axis(axis=Axis.Y, delta=-20.0)
    assert result.y == pytest.approx(HOMED_POSITION["Y"] - 40.0)


# ── MoveToUnverified ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_move_to_unverified_returns_target_without_position_query(
    homed_feature: MotionControlFeature, monkeypatch: pytest.MonkeyPatch
):
    """MoveToUnverified must not issue the trailing get_position firmware query."""

    async def _fail() -> dict[str, float]:
        pytest.fail("MoveToUnverified must not query the position")

    monkeypatch.setattr(homed_feature._controller, "get_position", _fail)
    target = AxisPosition(x=50.0, y=30.0, z=100.0, a=100.0, b=19.0, c=19.0)
    result = await homed_feature.move_to_unverified(position=target)
    _assert_positions_equal(result, target)


@pytest.mark.asyncio
async def test_move_to_unverified_matches_move_to(homed_feature: MotionControlFeature):
    """The unverified return value equals what a subsequent GetPosition reports."""
    target = AxisPosition(x=50.0, y=30.0, z=100.0, a=100.0, b=19.0, c=19.0)
    result = await homed_feature.move_to_unverified(position=target)
    verified = await homed_feature.get_position()
    _assert_positions_equal(result, verified)


@pytest.mark.asyncio
async def test_move_to_unverified_out_of_bounds_rejected_without_moving(homed_feature: MotionControlFeature):
    before = await homed_feature.get_position()
    with pytest.raises(OutOfBoundsError):
        await homed_feature.move_to_unverified(_with(before, x=-1.0))
    _assert_positions_equal(await homed_feature.get_position(), before)


# ── MoveThrough ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_move_through_single_waypoint_reaches_target(homed_feature: MotionControlFeature):
    pos = await homed_feature.get_position()
    result = await homed_feature.move_through([_waypoint(pos, x=50.0, y=30.0, z=100.0)])
    assert result.x == pytest.approx(50.0)
    assert result.y == pytest.approx(30.0)
    assert result.z == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_move_through_matches_sequence_of_move_to_calls(homed_feature: MotionControlFeature):
    """A batch must land exactly where the same waypoints issued as MoveTo calls land."""
    reference = MotionControlFeature(await OT2MotionController.build(simulate=True))
    await reference.home(ALL_AXES)

    pos = await homed_feature.get_position()
    targets = [
        _with(pos, x=50.0, y=30.0),
        _with(pos, x=50.3, y=30.0),
        _with(pos, x=49.7, y=30.0, z=100.0),
    ]

    for target in targets:
        expected = await reference.move_to(position=target, speed=25.0)
    result = await homed_feature.move_through(
        [_waypoint(pos, speed=25.0, x=t.x, y=t.y, z=t.z, a=t.a, b=t.b, c=t.c) for t in targets]
    )
    _assert_positions_equal(result, expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_index", [0, 1, 2])
async def test_move_through_bad_waypoint_rejects_whole_batch(homed_feature: MotionControlFeature, bad_index: int):
    """One out-of-bounds waypoint anywhere in the list must reject the batch before any motion."""
    pos = await homed_feature.get_position()
    waypoints = [
        _waypoint(pos, x=50.0),
        _waypoint(pos, x=51.0),
        _waypoint(pos, x=52.0),
    ]
    waypoints[bad_index] = _waypoint(pos, x=-5.0)
    with pytest.raises(OutOfBoundsError):
        await homed_feature.move_through(waypoints)
    _assert_positions_equal(await homed_feature.get_position(), pos)


@pytest.mark.asyncio
async def test_move_through_rejects_plunger_motion_without_moving(homed_feature: MotionControlFeature):
    """Waypoints that move B/C are rejected: batching skips the plunger backlash preload."""
    pos = await homed_feature.get_position()
    waypoints = [_waypoint(pos, x=50.0), _waypoint(pos, x=50.0, b=pos.b - 5.0)]
    with pytest.raises(PlungerAxisNotSupportedError):
        await homed_feature.move_through(waypoints)
    _assert_positions_equal(await homed_feature.get_position(), pos)


@pytest.mark.asyncio
async def test_move_through_queries_position_only_once(
    homed_feature: MotionControlFeature, monkeypatch: pytest.MonkeyPatch
):
    """The whole point of the batch: no per-waypoint read-back, one query at the end."""
    controller = homed_feature._controller
    calls = 0
    original = controller.get_position

    async def _counting_get_position() -> dict[str, float]:
        nonlocal calls
        calls += 1
        return await original()

    monkeypatch.setattr(controller, "get_position", _counting_get_position)
    pos = await homed_feature.get_position()
    calls = 0
    await homed_feature.move_through([_waypoint(pos, x=50.0 + i) for i in range(5)])
    assert calls == 1


# ── Probe ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_probe_returns_current_position(homed_feature: MotionControlFeature):
    # In simulation, probe returns the cached position (no physical contact).
    pos = await homed_feature.probe(axis=Axis.Z, distance=10.0)
    assert isinstance(pos, AxisPosition)
    assert pos.z == pytest.approx(HOMED_POSITION["Z"])


# ── Firmware ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_firmware_version_is_virtual(feature: MotionControlFeature):
    version = await feature.get_firmware_version()
    assert version == "Virtual Smoothie"


# ── Error reset ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_from_error_clears_homed_flags(homed_feature: MotionControlFeature):
    flags_before = homed_feature.homed_flags()
    assert all([flags_before.x, flags_before.y, flags_before.z])

    await homed_feature.reset_from_error()

    flags_after = homed_feature.homed_flags()
    assert not any([flags_after.x, flags_after.y, flags_after.z])


# ── AxisBounds ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_axis_bounds_returns_all_axes(feature):
    bounds = feature.axis_bounds()
    axes = {b.axis.value for b in bounds}
    assert axes == {"X", "Y", "Z", "A", "B", "C"}


@pytest.mark.asyncio
async def test_axis_bounds_min_per_axis(feature):
    """X/Y (deck-plane) floor at 0. Z/A (mount-vertical) have no software floor --
    Opentrons provides no fixed minimum for these and Protocol Engine itself
    doesn't enforce one; the physical limit switches are the real boundary.
    Plunger axes (B, C) floor negative (drop-tip travel)."""
    bounds = {b.axis.value: b.min_mm for b in feature.axis_bounds()}
    for ax in ("X", "Y"):
        assert bounds[ax] == 0.0
    for ax in ("Z", "A"):
        assert bounds[ax] == float("-inf")
    assert bounds["B"] < 0.0
    assert bounds["C"] < 0.0


@pytest.mark.asyncio
async def test_axis_bounds_max_positive(feature):
    for b in feature.axis_bounds():
        assert b.max_mm > 0.0


@pytest.mark.asyncio
async def test_move_axis_out_of_bounds_raises(feature):
    from unitelabs.opentrons_ot2.features.motion_control import OutOfBoundsError

    await feature.home("X")
    with pytest.raises(OutOfBoundsError):
        await feature.move_axis(Axis.X, position=9999.0)


@pytest.mark.asyncio
async def test_move_axis_within_bounds_does_not_raise(feature):
    await feature.home("X")
    await feature.move_axis(Axis.X, position=10.0)


# ── Bounds: relative / aspirate / dispense ────────────────────────────────────
# Simulator bounds: X<=418, Y<=370, Z/A<=218, B/C<=19; plungers home at 19 (=max).


@pytest.mark.asyncio
async def test_move_relative_axis_out_of_bounds_raises(homed_feature):
    from unitelabs.opentrons_ot2.features.motion_control import OutOfBoundsError

    # Homed X=418 is the max; a positive relative move exceeds the limit.
    with pytest.raises(OutOfBoundsError):
        await homed_feature.move_relative_axis(axis=Axis.X, delta=100.0)


@pytest.mark.asyncio
async def test_move_relative_axis_below_zero_raises(homed_feature):
    from unitelabs.opentrons_ot2.features.motion_control import OutOfBoundsError

    with pytest.raises(OutOfBoundsError):
        await homed_feature.move_relative_axis(axis=Axis.X, delta=-9999.0)


@pytest.mark.asyncio
async def test_move_relative_axis_within_bounds_ok(homed_feature):
    result = await homed_feature.move_relative_axis(axis=Axis.X, delta=-10.0)
    assert result.x == pytest.approx(HOMED_POSITION["X"] - 10.0)


@pytest.mark.asyncio
async def test_aspirate_above_plunger_max_raises(homed_feature):
    # Plunger B homed at its max (19); aspirating (an UP move) from there
    # exceeds the limit — the guard against skipping PrepareForAspirate.
    with pytest.raises(OutOfBoundsError):
        await homed_feature.aspirate(mount=Mount.LEFT, volume_ul=300.0, ul_per_mm=5.0, flow_rate_ul_s=10.0)


@pytest.mark.asyncio
async def test_aspirate_within_bounds_ok(homed_feature):
    # Prepared at bottom (-18.5); 50 uL / 5 (uL/mm) = 10 mm UP → -8.5, within bounds.
    await homed_feature.prepare_for_aspirate(mount=Mount.LEFT, bottom_position_mm=_PLUNGER_BOTTOM)
    result = await homed_feature.aspirate(mount=Mount.LEFT, volume_ul=50.0, ul_per_mm=5.0, flow_rate_ul_s=10.0)
    assert result.b == pytest.approx(_PLUNGER_BOTTOM + 10.0)


@pytest.mark.asyncio
async def test_dispense_below_plunger_floor_raises(homed_feature):
    # Plunger B homed at 19; dispensing 60 mm worth of volume (a DOWN move)
    # drives it to -41, below the -37 mm plunger floor.
    with pytest.raises(OutOfBoundsError):
        await homed_feature.dispense(mount=Mount.LEFT, volume_ul=300.0, ul_per_mm=5.0, flow_rate_ul_s=10.0)


@pytest.mark.asyncio
async def test_dispense_within_bounds_ok(homed_feature):
    # Prepare + aspirate 10 mm up (-8.5), then dispense 4 mm back down → -12.5.
    await homed_feature.prepare_for_aspirate(mount=Mount.LEFT, bottom_position_mm=_PLUNGER_BOTTOM)
    await homed_feature.aspirate(mount=Mount.LEFT, volume_ul=50.0, ul_per_mm=5.0, flow_rate_ul_s=10.0)
    result = await homed_feature.dispense(mount=Mount.LEFT, volume_ul=20.0, ul_per_mm=5.0, flow_rate_ul_s=10.0)
    assert result.b == pytest.approx(_PLUNGER_BOTTOM + 6.0)


# ── Board revision / serial / disengage ───────────────────────────────────────


def test_board_revision_is_unknown_in_simulation(feature: MotionControlFeature):
    from unitelabs.opentrons_ot2.features.motion_control import BoardRevision

    assert feature.board_revision() == BoardRevision.UNKNOWN


@pytest.mark.asyncio
async def test_serial_number_returns_string_in_simulation(feature: MotionControlFeature):
    sn = await feature.serial_number()
    assert isinstance(sn, str)  # '' in simulation (no /var/serial)


@pytest.mark.asyncio
async def test_disengage_axes_does_not_raise(feature: MotionControlFeature):
    await feature.home(ALL_AXES)
    await feature.disengage_axes("XYZABC")
