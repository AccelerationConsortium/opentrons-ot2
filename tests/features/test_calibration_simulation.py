"""Simulation-mode tests for CalibrationFeature.

In simulation the driver updates its internal state without sending G-code,
so we can assert steps_per_mm changes directly via driver.steps_per_mm.
update_pipette_config returns {axis: data} without error in simulation.
"""

import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.features.calibration import CalibrationFeature, StepsPerMm
from unitelabs.opentrons_ot2.features.motion_control import Axis
from unitelabs.opentrons_ot2.io.motion import OT2MotionController


@pytest_asyncio.fixture
async def feature() -> CalibrationFeature:
    controller = await OT2MotionController.build(simulate=True)
    return CalibrationFeature(controller)


def _steps(feature: CalibrationFeature) -> dict:
    return feature._controller._driver.steps_per_mm


# ── UpdateStepsPerMm ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_steps_per_mm_single_axis(feature: CalibrationFeature):
    await feature.update_steps_per_mm([StepsPerMm(axis=Axis.X, steps_per_mm=80.0)])
    assert _steps(feature)["X"] == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_update_steps_per_mm_all_axes(feature: CalibrationFeature):
    updates = [StepsPerMm(axis=ax, steps_per_mm=100.0) for ax in Axis]
    await feature.update_steps_per_mm(updates)
    for ax in Axis:
        assert _steps(feature)[ax.value] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_update_steps_per_mm_partial_leaves_others(feature: CalibrationFeature):
    await feature.update_steps_per_mm([StepsPerMm(axis=Axis.X, steps_per_mm=90.0)])
    await feature.update_steps_per_mm([StepsPerMm(axis=Axis.Y, steps_per_mm=75.0)])
    assert _steps(feature)["X"] == pytest.approx(90.0)
    assert _steps(feature)["Y"] == pytest.approx(75.0)


@pytest.mark.asyncio
async def test_update_steps_per_mm_plunger_axis(feature: CalibrationFeature):
    await feature.update_steps_per_mm([StepsPerMm(axis=Axis.B, steps_per_mm=768.0)])
    assert _steps(feature)["B"] == pytest.approx(768.0)


# ── UpdatePipetteHome ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_pipette_home_does_not_raise(feature: CalibrationFeature):
    await feature.update_pipette_home(Axis.Z, home_position_mm=220.0)


@pytest.mark.asyncio
async def test_update_pipette_home_right_mount(feature: CalibrationFeature):
    await feature.update_pipette_home(Axis.A, home_position_mm=218.0)


# ── UpdateMaxTravel ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_max_travel_does_not_raise(feature: CalibrationFeature):
    await feature.update_max_travel(Axis.B, max_travel_mm=30.0)


# ── UpdateRetractDistance ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_retract_distance_does_not_raise(feature: CalibrationFeature):
    await feature.update_retract_distance(Axis.B, retract_mm=2.0)


# ── UpdateEndstopDebounce ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_endstop_debounce_does_not_raise(feature: CalibrationFeature):
    await feature.update_endstop_debounce(debounce_mm=0.5)
