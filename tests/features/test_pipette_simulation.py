"""Simulation-mode tests for PipetteFeature.

In simulation:
  - read_pipette_model returns None (no EEPROM) → feature returns ""
  - read_pipette_id returns "1234567890" (driver fixture value)
  - update_pipette_config returns {axis: data} without touching hardware
  - update_steps_per_mm writes to driver.steps_per_mm in-process
"""

import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.features.motion_control import Mount
from unitelabs.opentrons_ot2.features.pipette import PipetteConfig, PipetteFeature, PipetteInfo
from unitelabs.opentrons_ot2.io.motion import OT2MotionController

_CONFIG = PipetteConfig(
    steps_per_mm=768.0,
    home_position_mm=19.0,
    max_travel_mm=30.0,
    retract_mm=2.0,
)


@pytest_asyncio.fixture
async def feature() -> PipetteFeature:
    controller = await OT2MotionController.build(simulate=True)
    return PipetteFeature(controller)


# ── GetAttachedPipettes ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_attached_pipettes_returns_both_mounts(feature: PipetteFeature):
    result = await feature.get_attached_pipettes()
    assert len(result) == 2
    assert {p.mount for p in result} == {Mount.LEFT, Mount.RIGHT}


@pytest.mark.asyncio
async def test_get_attached_pipettes_returns_pipette_info(feature: PipetteFeature):
    result = await feature.get_attached_pipettes()
    assert all(isinstance(p, PipetteInfo) for p in result)


@pytest.mark.asyncio
async def test_get_attached_pipettes_sim_model_is_empty(feature: PipetteFeature):
    result = await feature.get_attached_pipettes()
    assert all(p.model == "" for p in result)


@pytest.mark.asyncio
async def test_get_attached_pipettes_sim_id_is_fixture(feature: PipetteFeature):
    result = await feature.get_attached_pipettes()
    assert all(p.pipette_id == "1234567890" for p in result)


# ── ConfigureMount ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_configure_left_mount_does_not_raise(feature: PipetteFeature):
    await feature.configure_mount(Mount.LEFT, _CONFIG)


@pytest.mark.asyncio
async def test_configure_right_mount_does_not_raise(feature: PipetteFeature):
    await feature.configure_mount(Mount.RIGHT, _CONFIG)


@pytest.mark.asyncio
async def test_configure_left_mount_updates_b_axis_steps(feature: PipetteFeature):
    await feature.configure_mount(Mount.LEFT, _CONFIG)
    assert feature._controller._driver.steps_per_mm["B"] == pytest.approx(_CONFIG.steps_per_mm)


@pytest.mark.asyncio
async def test_configure_right_mount_updates_c_axis_steps(feature: PipetteFeature):
    await feature.configure_mount(Mount.RIGHT, _CONFIG)
    assert feature._controller._driver.steps_per_mm["C"] == pytest.approx(_CONFIG.steps_per_mm)


@pytest.mark.asyncio
async def test_configure_left_does_not_affect_right_mount_steps(feature: PipetteFeature):
    right_config = PipetteConfig(steps_per_mm=500.0, home_position_mm=19.0, max_travel_mm=30.0, retract_mm=2.0)
    await feature.configure_mount(Mount.RIGHT, right_config)
    await feature.configure_mount(Mount.LEFT, _CONFIG)
    assert feature._controller._driver.steps_per_mm["C"] == pytest.approx(500.0)
