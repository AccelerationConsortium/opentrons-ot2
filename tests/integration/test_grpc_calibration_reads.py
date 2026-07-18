"""End-to-end gRPC integration tests for CalibrationFeature's calibration-*read* commands.

GetDeckCalibration/GetPipetteOffset (added for client-side coordinate resolution) need a
real HardwareControlAPI: without with_robot_server=True the connector has no HardwareAPI
wired up at all, and both commands raise CalibrationUnavailableError immediately (see
_require_hw_api in features/calibration.py). test_calibration_reads.py covers the feature
logic by injecting _hw_api directly into the controller -- useful, but it never starts a
real connector or crosses the wire, so it can't catch a startup-wiring regression (e.g. the
hardware never getting attached to the feature the way the running app actually does it).

These tests boot the connector the way it actually needs to run for these commands to be
reachable at all (hardware_sila_channel fixture, requires --with-http-server or --robot)
and call them over a real gRPC channel.
"""

import grpc.aio
import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.features.motion_control import Mount

_PKG = "sila2.ca.accelerationconsortium.robots.calibrationfeature.v1"
_SERVICE = f"{_PKG}.CalibrationFeature"


class _CalibrationReadClient:
    def __init__(self, channel: grpc.aio.Channel, pb: object) -> None:
        self._ch = channel
        self._pb = pb

    async def _call(self, method: str, params: dict | None = None) -> dict:
        req = await self._pb.encode(f"{_PKG}.{method}_Parameters", params or {})
        stub = self._ch.unary_unary(f"/{_SERVICE}/{method}")
        resp_bytes = await stub(req)
        return await self._pb.decode(f"{_PKG}.{method}_Responses", resp_bytes)

    async def get_deck_calibration(self) -> dict:
        return await self._call("GetDeckCalibration")

    async def get_pipette_offset(self, mount: Mount) -> dict:
        return await self._call("GetPipetteOffset", {"mount": mount})


@pytest_asyncio.fixture
async def client(hardware_sila_channel) -> _CalibrationReadClient:
    channel, pb = hardware_sila_channel
    return _CalibrationReadClient(channel, pb)


@pytest.mark.asyncio
@pytest.mark.robot_http_only
async def test_get_deck_calibration_over_the_wire(client: _CalibrationReadClient) -> None:
    """A connector actually started with_robot_server=True serves real calibration data.

    Response is keyed "response_0" -- this connector's established convention (every
    command result is unnamed; see sila_transport.py's documented wire mapping) -- and
    holds the actual DeckCalibration dataclass instance, not a re-encoded dict.
    """
    resp = await client.get_deck_calibration()
    deck_calibration = resp["response_0"]
    assert len(deck_calibration.attitude) == 3
    assert deck_calibration.source in ("default", "user")


@pytest.mark.asyncio
@pytest.mark.robot_http_only
async def test_get_pipette_offset_no_pipette_raises_defined_error(client: _CalibrationReadClient) -> None:
    """A bare simulator has no pipette attached; the wire surfaces the defined SiLA error."""
    with pytest.raises(grpc.aio.AioRpcError):
        await client.get_pipette_offset(Mount.RIGHT)
