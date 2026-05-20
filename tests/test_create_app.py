"""Integration tests for create_app() module detection wiring.

Validates that scan_module_ports() results drive feature registration correctly.
Hardware boundaries (controller builds, Connector gRPC server) are mocked.
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from unitelabs.opentrons_ot2 import OpentronsOt2Config, create_app
from unitelabs.opentrons_ot2.features import (
    HeaterShakerFeature,
    MagneticModuleFeature,
    MotionControlFeature,
    PipetteFeature,
    TemperatureModuleFeature,
    ThermocyclerFeature,
)

_ALL_MODULE_PORTS = {
    "heater_shaker": "/dev/ot_module_heatershaker0",
    "thermocycler": "/dev/ot_module_thermocycler0",
    "temperature": "/dev/ot_module_tempdeck0",
    "magnetic": "/dev/ot_module_magdeck0",
}


@contextlib.asynccontextmanager
async def _run_app(config: OpentronsOt2Config, module_ports: dict):
    """Run create_app() with all hardware mocked; yield (connector, registered_features)."""
    mock_motion_ctrl = AsyncMock()
    mock_hs_ctrl = AsyncMock()
    mock_tc_ctrl = AsyncMock()
    mock_temp_ctrl = AsyncMock()
    mock_mag_ctrl = AsyncMock()

    # Connector is patched to avoid starting a real gRPC server.
    mock_connector = MagicMock()
    registered: list = []
    mock_connector.register.side_effect = registered.append

    with (
        patch("unitelabs.opentrons_ot2.OT2MotionController.build", return_value=mock_motion_ctrl),
        patch("unitelabs.opentrons_ot2.HeaterShakerController.build", return_value=mock_hs_ctrl),
        patch("unitelabs.opentrons_ot2.ThermocyclerController.build", return_value=mock_tc_ctrl),
        patch("unitelabs.opentrons_ot2.TemperatureModuleController.build", return_value=mock_temp_ctrl),
        patch("unitelabs.opentrons_ot2.MagneticModuleController.build", return_value=mock_mag_ctrl),
        patch("unitelabs.opentrons_ot2.scan_module_ports", return_value=module_ports),
        patch("unitelabs.opentrons_ot2.Connector", return_value=mock_connector),
    ):
        gen = create_app(config)
        await gen.__anext__()
        yield mock_connector, registered
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()


# ── simulate mode ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simulate_registers_motion_and_pipette():
    config = OpentronsOt2Config(use_simulator=True)
    async with _run_app(config, module_ports=_ALL_MODULE_PORTS) as (_, registered):
        types = [type(f) for f in registered]
        assert types == [MotionControlFeature, PipetteFeature]


@pytest.mark.asyncio
async def test_simulate_skips_module_scan(monkeypatch):
    scan = MagicMock(return_value=_ALL_MODULE_PORTS)
    monkeypatch.setattr("unitelabs.opentrons_ot2.scan_module_ports", scan)
    config = OpentronsOt2Config(use_simulator=True)
    async with _run_app(config, module_ports=_ALL_MODULE_PORTS):
        scan.assert_not_called()


# ── real hardware, no modules ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_modules_registers_motion_and_pipette():
    config = OpentronsOt2Config(use_simulator=False)
    async with _run_app(config, module_ports={}) as (_, registered):
        types = [type(f) for f in registered]
        assert types == [MotionControlFeature, PipetteFeature]


# ── real hardware, individual modules ────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ports", "expected_feature"),
    [
        ({"heater_shaker": "/dev/ot_module_heatershaker0"}, HeaterShakerFeature),
        ({"thermocycler": "/dev/ot_module_thermocycler0"}, ThermocyclerFeature),
        ({"temperature": "/dev/ot_module_tempdeck0"}, TemperatureModuleFeature),
        ({"magnetic": "/dev/ot_module_magdeck0"}, MagneticModuleFeature),
    ],
)
async def test_single_module_registers_correct_feature(ports, expected_feature):
    config = OpentronsOt2Config(use_simulator=False)
    async with _run_app(config, module_ports=ports) as (_, registered):
        types = [type(f) for f in registered]
        assert MotionControlFeature in types
        assert PipetteFeature in types
        assert expected_feature in types
        assert len(types) == 3


@pytest.mark.asyncio
async def test_all_modules_registers_all_features():
    config = OpentronsOt2Config(use_simulator=False)
    async with _run_app(config, module_ports=_ALL_MODULE_PORTS) as (_, registered):
        types = {type(f) for f in registered}
        assert types == {
            MotionControlFeature,
            PipetteFeature,
            HeaterShakerFeature,
            ThermocyclerFeature,
            TemperatureModuleFeature,
            MagneticModuleFeature,
        }


# ── cleanup ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_controllers_disconnected_on_shutdown():
    config = OpentronsOt2Config(use_simulator=False)

    mock_motion_ctrl = AsyncMock()
    mock_hs_ctrl = AsyncMock()
    mock_tc_ctrl = AsyncMock()
    mock_temp_ctrl = AsyncMock()
    mock_mag_ctrl = AsyncMock()

    with (
        patch("unitelabs.opentrons_ot2.OT2MotionController.build", return_value=mock_motion_ctrl),
        patch("unitelabs.opentrons_ot2.HeaterShakerController.build", return_value=mock_hs_ctrl),
        patch("unitelabs.opentrons_ot2.ThermocyclerController.build", return_value=mock_tc_ctrl),
        patch("unitelabs.opentrons_ot2.TemperatureModuleController.build", return_value=mock_temp_ctrl),
        patch("unitelabs.opentrons_ot2.MagneticModuleController.build", return_value=mock_mag_ctrl),
        patch("unitelabs.opentrons_ot2.scan_module_ports", return_value=_ALL_MODULE_PORTS),
        patch("unitelabs.opentrons_ot2.Connector", return_value=MagicMock()),
    ):
        gen = create_app(config)
        await gen.__anext__()
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()

    mock_motion_ctrl.disconnect.assert_awaited_once()
    mock_hs_ctrl.disconnect.assert_awaited_once()
    mock_tc_ctrl.disconnect.assert_awaited_once()
    mock_temp_ctrl.disconnect.assert_awaited_once()
    mock_mag_ctrl.disconnect.assert_awaited_once()
