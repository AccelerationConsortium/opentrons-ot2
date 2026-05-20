"""End-to-end gRPC integration tests for CalibrationFeature in simulate mode."""

import contextlib

import grpc
import grpc.aio
import pytest
import pytest_asyncio

from unitelabs.cdk import SiLAServerConfig
from unitelabs.opentrons_ot2 import OpentronsOt2Config, create_app
from unitelabs.opentrons_ot2.features.calibration import StepsPerMm
from unitelabs.opentrons_ot2.features.motion_control import Axis

_PKG = "sila2.ca.accelerationconsortium.robots.calibrationfeature.v1"
_SERVICE = f"{_PKG}.CalibrationFeature"


class _CalibrationClient:
    def __init__(self, channel: grpc.aio.Channel, pb: object) -> None:
        self._ch = channel
        self._pb = pb

    async def _call(self, method: str, params: dict | None = None) -> dict:
        req = await self._pb.encode(f"{_PKG}.{method}_Parameters", params or {})
        stub = self._ch.unary_unary(f"/{_SERVICE}/{method}")
        resp_bytes = await stub(req)
        return await self._pb.decode(f"{_PKG}.{method}_Responses", resp_bytes)

    async def update_steps_per_mm(self, updates: list[StepsPerMm]) -> None:
        await self._call("UpdateStepsPerMm", {"updates": updates})

    async def update_pipette_home(self, axis: Axis, home_position_mm: float) -> None:
        await self._call("UpdatePipetteHome", {"axis": axis, "home_position_mm": home_position_mm})

    async def update_max_travel(self, axis: Axis, max_travel_mm: float) -> None:
        await self._call("UpdateMaxTravel", {"axis": axis, "max_travel_mm": max_travel_mm})

    async def update_retract_distance(self, axis: Axis, retract_mm: float) -> None:
        await self._call("UpdateRetractDistance", {"axis": axis, "retract_mm": retract_mm})

    async def update_endstop_debounce(self, debounce_mm: float) -> None:
        await self._call("UpdateEndstopDebounce", {"debounce_mm": debounce_mm})


@pytest_asyncio.fixture
async def client() -> _CalibrationClient:
    config = OpentronsOt2Config(
        use_simulator=True,
        sila_server=SiLAServerConfig(hostname="127.0.0.1", port=0, tls=False),
        cloud_server_endpoint=None,
        discovery=None,
    )
    gen = create_app(config)
    connector = await gen.__anext__()
    await connector.start()

    address = connector.sila_server._address
    pb = connector.sila_server.protobuf
    channel = grpc.aio.insecure_channel(address)

    try:
        yield _CalibrationClient(channel, pb)
    finally:
        await channel.close()
        await connector.stop()
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()


@pytest.mark.asyncio
async def test_update_steps_per_mm_single_axis(client: _CalibrationClient) -> None:
    await client.update_steps_per_mm([StepsPerMm(axis=Axis.X, steps_per_mm=80.0)])


@pytest.mark.asyncio
async def test_update_steps_per_mm_all_axes(client: _CalibrationClient) -> None:
    updates = [StepsPerMm(axis=ax, steps_per_mm=100.0) for ax in Axis]
    await client.update_steps_per_mm(updates)


@pytest.mark.asyncio
async def test_update_pipette_home_does_not_raise(client: _CalibrationClient) -> None:
    await client.update_pipette_home(Axis.Z, home_position_mm=220.0)


@pytest.mark.asyncio
async def test_update_max_travel_does_not_raise(client: _CalibrationClient) -> None:
    await client.update_max_travel(Axis.B, max_travel_mm=30.0)


@pytest.mark.asyncio
async def test_update_retract_distance_does_not_raise(client: _CalibrationClient) -> None:
    await client.update_retract_distance(Axis.B, retract_mm=2.0)


@pytest.mark.asyncio
async def test_update_endstop_debounce_does_not_raise(client: _CalibrationClient) -> None:
    await client.update_endstop_debounce(debounce_mm=0.5)
