"""Simulation-mode tests for PipetteFeature.

In simulation:
  - read_pipette_model returns None (no EEPROM) -> feature returns ""
  - read_pipette_id returns "1234567890" (driver fixture value)
"""

import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.features.motion_control import Mount
from unitelabs.opentrons_ot2.features.pipette import PipetteFeature, PipetteInfo
from unitelabs.opentrons_ot2.io.motion import OT2MotionController


@pytest_asyncio.fixture
async def feature() -> PipetteFeature:
    controller = await OT2MotionController.build(simulate=True)
    return PipetteFeature(controller)


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
