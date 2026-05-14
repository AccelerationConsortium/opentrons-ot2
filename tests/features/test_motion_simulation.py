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

from unitelabs.opentrons_ot2.features.motion_control import MotionControlFeature, AxisPosition
from unitelabs.opentrons_ot2.io.motion import OT2MotionController

# Real homed positions reported by the Smoothie firmware defaults.
HOMED_POSITION = {"X": 418.0, "Y": 353.0, "Z": 218.0, "A": 218.0, "B": 19.0, "C": 19.0}


@pytest_asyncio.fixture
async def feature() -> MotionControlFeature:
    controller = await OT2MotionController.build(simulate=True)
    return MotionControlFeature(controller)


@pytest_asyncio.fixture
async def homed_feature(feature: MotionControlFeature) -> MotionControlFeature:
    """Feature with all axes already homed."""
    await feature.home()
    return feature


# ── Basic state ──────────────────────────────────────────────────────────────


def test_is_simulating(feature: MotionControlFeature):
    assert feature.is_simulating() is True


def test_homed_flags_all_false_before_homing(feature: MotionControlFeature):
    flags = feature.homed_flags()
    assert not any([flags.x, flags.y, flags.z, flags.a, flags.b, flags.c])


# ── Home ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_home_all_axes_returns_homed_position(feature: MotionControlFeature):
    result = await feature.home()
    assert result.homed_axes == "XYZABC"
    assert result.position.x == HOMED_POSITION["X"]
    assert result.position.y == HOMED_POSITION["Y"]
    assert result.position.z == HOMED_POSITION["Z"]
    assert result.position.a == HOMED_POSITION["A"]


@pytest.mark.asyncio
async def test_home_sets_all_homed_flags(feature: MotionControlFeature):
    await feature.home()
    flags = feature.homed_flags()
    assert all([flags.x, flags.y, flags.z, flags.a, flags.b, flags.c])


@pytest.mark.asyncio
async def test_home_subset_of_axes(feature: MotionControlFeature):
    # Home only the plunger axes (B/C) — independent of gantry homing sequence.
    result = await feature.home(axes="BC")
    assert result.homed_axes == "BC"
    flags = feature.homed_flags()
    assert flags.b and flags.c
    assert not flags.x and not flags.y


@pytest.mark.asyncio
async def test_home_invalid_axis_raises(feature: MotionControlFeature):
    with pytest.raises(ValueError, match="Invalid axes"):
        await feature.home(axes="Q")


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
    result = await homed_feature.move_axis(axis="X", position=75.0)
    assert result.x == pytest.approx(75.0)
    assert result.y == HOMED_POSITION["Y"]


@pytest.mark.asyncio
async def test_move_axis_case_insensitive(homed_feature: MotionControlFeature):
    result = await homed_feature.move_axis(axis="x", position=20.0)
    assert result.x == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_move_axis_invalid_raises(homed_feature: MotionControlFeature):
    with pytest.raises(ValueError, match="Invalid axis"):
        await homed_feature.move_axis(axis="Q", position=10.0)


@pytest.mark.asyncio
async def test_move_relative_axis_updates_position(homed_feature: MotionControlFeature):
    before = await homed_feature.get_position()
    result = await homed_feature.move_relative_axis(axis="X", delta=-10.0)
    assert result.x == pytest.approx(before.x - 10.0)
    assert result.y == pytest.approx(before.y)


@pytest.mark.asyncio
async def test_move_relative_axis_accumulates(homed_feature: MotionControlFeature):
    await homed_feature.move_relative_axis(axis="Y", delta=-20.0)
    result = await homed_feature.move_relative_axis(axis="Y", delta=-20.0)
    assert result.y == pytest.approx(HOMED_POSITION["Y"] - 40.0)


# ── Probe ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_probe_returns_current_position(homed_feature: MotionControlFeature):
    # In simulation, probe returns the cached position (no physical contact).
    pos = await homed_feature.probe(axis="Z", distance=10.0)
    assert isinstance(pos, AxisPosition)
    assert pos.z == pytest.approx(HOMED_POSITION["Z"])


@pytest.mark.asyncio
async def test_probe_invalid_axis_raises(homed_feature: MotionControlFeature):
    with pytest.raises(ValueError, match="Invalid axis"):
        await homed_feature.probe(axis="Q", distance=10.0)


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
