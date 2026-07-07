"""Tests for the general calibration read commands on CalibrationFeature.

These reads need a real (simulated) HardwareControlAPI, which build(simulate=True)
does not attach. We build a hardware simulator and inject it as the controller's
_hw_api (the reads only touch _hw_api) — the same wiring the with_robot_server
path uses via from_api().
"""

import pytest
import pytest_asyncio

from opentrons.hardware_control import API
from opentrons.types import Mount as OTMount

from unitelabs.opentrons_ot2.features.calibration import (
    CalibrationFeature,
    CalibrationUnavailableError,
    NoPipetteOnMountError,
)
from unitelabs.opentrons_ot2.features.motion_control import Mount
from unitelabs.opentrons_ot2.io.motion import OT2MotionController


@pytest_asyncio.fixture
async def hw_api():
    hw = await API.build_hardware_simulator(
        attached_instruments={
            OTMount.RIGHT: {"model": "p300_multi_v2.1", "id": "sim-r"},
            OTMount.LEFT: {"model": "p1000_single_v2.1", "id": "sim-l"},
        }
    )
    yield hw
    await hw.clean_up()


@pytest_asyncio.fixture
async def feature(hw_api) -> CalibrationFeature:
    controller = await OT2MotionController.build(simulate=True)
    controller._hw_api = hw_api
    return CalibrationFeature(controller)


@pytest_asyncio.fixture
async def feature_no_hw() -> CalibrationFeature:
    controller = await OT2MotionController.build(simulate=True)
    return CalibrationFeature(controller)


# ── GetDeckCalibration ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_deck_calibration_default_is_identity(feature: CalibrationFeature):
    dc = await feature.get_deck_calibration()
    assert len(dc.attitude) == 3
    assert (dc.attitude[0].col_x, dc.attitude[0].col_y, dc.attitude[0].col_z) == (1.0, 0.0, 0.0)
    assert (dc.attitude[1].col_x, dc.attitude[1].col_y, dc.attitude[1].col_z) == (0.0, 1.0, 0.0)
    assert (dc.attitude[2].col_x, dc.attitude[2].col_y, dc.attitude[2].col_z) == (0.0, 0.0, 1.0)
    assert dc.source == "default"
    assert dc.marked_bad is False


@pytest.mark.asyncio
async def test_get_deck_calibration_without_hw_api_raises(feature_no_hw: CalibrationFeature):
    with pytest.raises(CalibrationUnavailableError):
        await feature_no_hw.get_deck_calibration()


# ── GetPipetteOffset ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pipette_offset_reports_mount_model_and_id(feature: CalibrationFeature):
    po = await feature.get_pipette_offset(Mount.RIGHT)
    assert po.mount == Mount.RIGHT
    assert (po.x_mm, po.y_mm, po.z_mm) == (0.0, 0.0, 0.0)
    assert po.pipette_model == "p300_multi_v2.1"
    assert po.pipette_id == "sim-r"
    assert po.source == "default"


@pytest.mark.asyncio
async def test_get_pipette_offset_left_mount(feature: CalibrationFeature):
    po = await feature.get_pipette_offset(Mount.LEFT)
    assert po.mount == Mount.LEFT
    assert po.pipette_model == "p1000_single_v2.1"
    assert po.pipette_id == "sim-l"


@pytest.mark.asyncio
async def test_get_pipette_offset_without_hw_api_raises(feature_no_hw: CalibrationFeature):
    with pytest.raises(CalibrationUnavailableError):
        await feature_no_hw.get_pipette_offset(Mount.RIGHT)


@pytest.mark.asyncio
async def test_get_pipette_offset_no_pipette_on_mount_raises():
    hw = await API.build_hardware_simulator(
        attached_instruments={OTMount.RIGHT: {"model": "p300_multi_v2.1", "id": "sim-r"}}
    )
    try:
        controller = await OT2MotionController.build(simulate=True)
        controller._hw_api = hw
        feature = CalibrationFeature(controller)
        with pytest.raises(NoPipetteOnMountError):
            await feature.get_pipette_offset(Mount.LEFT)
    finally:
        await hw.clean_up()
