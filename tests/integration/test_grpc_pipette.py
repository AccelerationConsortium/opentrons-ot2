"""End-to-end gRPC integration tests for PipetteFeature in simulate mode."""

import grpc
import grpc.aio
import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.features.motion_control import Mount
from unitelabs.opentrons_ot2.features.pipette import PipetteInfo

_PKG = "sila2.ca.accelerationconsortium.robots.pipettefeature.v1"
_SERVICE = f"{_PKG}.PipetteFeature"


class _PipetteClient:
    def __init__(self, channel: grpc.aio.Channel, pb: object) -> None:
        self._ch = channel
        self._pb = pb

    async def _call(self, method: str, params: dict | None = None) -> dict:
        req = await self._pb.encode(f"{_PKG}.{method}_Parameters", params or {})
        stub = self._ch.unary_unary(f"/{_SERVICE}/{method}")
        resp_bytes = await stub(req)
        return await self._pb.decode(f"{_PKG}.{method}_Responses", resp_bytes)

    async def get_attached_pipettes(self) -> list[PipetteInfo]:
        decoded = await self._call("GetAttachedPipettes")
        value = next(iter(decoded.values()))
        assert isinstance(value, list)
        return value


@pytest_asyncio.fixture
async def client(sila_channel) -> _PipetteClient:
    """Yield a PipetteFeature gRPC client (local sim or --robot target)."""
    channel, pb = sila_channel
    return _PipetteClient(channel, pb)


@pytest.mark.asyncio
async def test_get_attached_pipettes_returns_two_entries(client: _PipetteClient) -> None:
    result = await client.get_attached_pipettes()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_attached_pipettes_entries_are_pipette_info(client: _PipetteClient) -> None:
    result = await client.get_attached_pipettes()
    assert all(isinstance(p, PipetteInfo) for p in result)


@pytest.mark.asyncio
@pytest.mark.simulator_only
async def test_get_attached_pipettes_sim_model_is_empty(client: _PipetteClient) -> None:
    result = await client.get_attached_pipettes()
    assert all(p.model == "" for p in result)


@pytest.mark.asyncio
async def test_get_attached_pipettes_covers_both_mounts(client: _PipetteClient) -> None:
    result = await client.get_attached_pipettes()
    mounts = {p.mount for p in result}
    assert mounts == {Mount.LEFT, Mount.RIGHT}
