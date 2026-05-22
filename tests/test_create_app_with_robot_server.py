"""Integration tests for create_app() with with_robot_server=True.

Exercises _create_app_with_robot_server() end-to-end with all hardware and
external server boundaries mocked. Catches import errors, wiring mistakes, and
shutdown regressions for the in-process robot-server mode.

Boundaries:
  robot_server  — stubbed in conftest.py (Opentrons-internal, not on PyPI)
  uvicorn       — real package (test dep); Server.serve mocked to avoid binding ports
  hardware      — mocked at API.build_hardware_controller
"""

import asyncio
import contextlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from unitelabs.opentrons_ot2 import OpentronsOt2Config, create_app
from unitelabs.opentrons_ot2.features import CalibrationFeature, MotionControlFeature, PipetteFeature
from unitelabs.opentrons_ot2.io import HardwareProxy


_CONFIG = OpentronsOt2Config(use_simulator=False, with_robot_server=True, robot_server_uds="/run/aiohttp.sock")


@pytest.fixture(autouse=True)
def _reset_robot_server_stubs():
    """Reset robot_server stub call counts between tests."""
    sys.modules["robot_server.hardware"]._hw_api_accessor.reset_mock()
    sys.modules["robot_server.hardware"]._init_task_accessor.reset_mock()
    sys.modules["robot_server.app"].app.reset_mock()


@contextlib.asynccontextmanager
async def _run(config=_CONFIG, module_ports=None):
    """Run create_app(with_robot_server=True) with all external deps mocked.

    Yields a namespace with:
      api          — mock returned by API.build_hardware_controller
      registered   — list of features registered on the connector
      uv_server    — mock uvicorn.Server instance
    """
    mock_api = AsyncMock()
    mock_uv_server = MagicMock()
    mock_uv_server.serve = AsyncMock()
    mock_connector = MagicMock()
    registered = []
    mock_connector.register.side_effect = registered.append

    with (
        patch(
            "opentrons.hardware_control.API.build_hardware_controller",
            new_callable=AsyncMock,
            return_value=mock_api,
        ),
        patch("unitelabs.opentrons_ot2.OT2MotionController.from_api", return_value=MagicMock()),
        patch("unitelabs.opentrons_ot2.scan_module_ports", return_value=module_ports or {}),
        patch("unitelabs.opentrons_ot2.Connector", return_value=mock_connector),
        patch("uvicorn.Server", return_value=mock_uv_server),
        patch("uvicorn.Config"),
    ):
        gen = create_app(config)
        await gen.__anext__()
        await asyncio.sleep(0)  # let the uvicorn task be scheduled

        class _Result:
            pass

        result = _Result()
        result.api = mock_api
        result.registered = registered
        result.uv_server = mock_uv_server

        yield result

        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()


# ── import coverage ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_import_errors():
    """All deferred imports in _create_app_with_robot_server resolve without error.

    This test will fail with ModuleNotFoundError if any import inside the
    function is missing from the test environment or not stubbed in conftest.
    """
    async with _run():
        pass


# ── hardware init ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hardware_built_on_configured_port():
    """API.build_hardware_controller is awaited once with the configured serial port."""
    with (
        patch(
            "opentrons.hardware_control.API.build_hardware_controller",
            new_callable=AsyncMock,
            return_value=AsyncMock(),
        ) as mock_build,
        patch("unitelabs.opentrons_ot2.OT2MotionController.from_api", return_value=MagicMock()),
        patch("unitelabs.opentrons_ot2.scan_module_ports", return_value={}),
        patch("unitelabs.opentrons_ot2.Connector", return_value=MagicMock()),
        patch("uvicorn.Server", return_value=MagicMock(serve=AsyncMock())),
        patch("uvicorn.Config"),
    ):
        gen = create_app(_CONFIG)
        await gen.__anext__()
        mock_build.assert_awaited_once_with(port=_CONFIG.serial_port)
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()


# ── app.state pre-population ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_app_state_receives_init_task():
    """_init_task_accessor.set_on is called once with a completed asyncio.Task."""
    rs_hw = sys.modules["robot_server.hardware"]
    async with _run():
        rs_hw._init_task_accessor.set_on.assert_called_once()
        _, task_arg = rs_hw._init_task_accessor.set_on.call_args[0]
        assert isinstance(task_arg, asyncio.Task)
        assert task_arg.done()


@pytest.mark.asyncio
async def test_app_state_receives_hardware_proxy():
    """_hw_api_accessor.set_on is called once with a HardwareProxy instance."""
    rs_hw = sys.modules["robot_server.hardware"]
    async with _run():
        rs_hw._hw_api_accessor.set_on.assert_called_once()
        _, proxy_arg = rs_hw._hw_api_accessor.set_on.call_args[0]
        assert isinstance(proxy_arg, HardwareProxy)


# ── uvicorn startup ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_uvicorn_configured_on_unix_socket():
    """uvicorn.Config is constructed with the configured robot_server_uds socket path."""
    with (
        patch("uvicorn.Config") as mock_cfg,
        patch(
            "opentrons.hardware_control.API.build_hardware_controller",
            new_callable=AsyncMock,
            return_value=AsyncMock(),
        ),
        patch("unitelabs.opentrons_ot2.OT2MotionController.from_api", return_value=MagicMock()),
        patch("unitelabs.opentrons_ot2.scan_module_ports", return_value={}),
        patch("unitelabs.opentrons_ot2.Connector", return_value=MagicMock()),
        patch("uvicorn.Server", return_value=MagicMock(serve=AsyncMock())),
    ):
        gen = create_app(_CONFIG)
        await gen.__anext__()
        _, kwargs = mock_cfg.call_args
        assert kwargs["uds"] == _CONFIG.robot_server_uds
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()


@pytest.mark.asyncio
async def test_uvicorn_serve_task_started():
    """uvicorn.Server.serve is called to create the background task."""
    async with _run() as r:
        r.uv_server.serve.assert_called_once()


# ── feature registration ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_core_features_registered():
    """MotionControlFeature, PipetteFeature, CalibrationFeature are always registered."""
    async with _run() as r:
        types_ = [type(f) for f in r.registered]
        assert MotionControlFeature in types_
        assert PipetteFeature in types_
        assert CalibrationFeature in types_


# ── shutdown ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shutdown_stops_uvicorn():
    """uv_server.should_exit is set to True on shutdown."""
    async with _run() as r:
        pass  # context exit triggers shutdown
    assert r.uv_server.should_exit is True


@pytest.mark.asyncio
async def test_shutdown_disconnects_hardware():
    """real_api.disconnect is awaited on shutdown."""
    async with _run() as r:
        pass
    r.api.disconnect.assert_awaited_once()
