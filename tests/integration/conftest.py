"""Shared fixtures and options for integration tests.

Pass --robot HOST:PORT to run against a live SiLA2 server instead of the
built-in simulator.  The gRPC channel is redirected; the local simulator is
still started to obtain the protobuf codec object (pb).

Tests marked @pytest.mark.simulator_only are skipped when --robot is used.
"""

import contextlib

import grpc.aio
import pytest
import pytest_asyncio

from unitelabs.cdk import SiLAServerConfig
from unitelabs.opentrons_ot2 import OpentronsOt2Config, create_app


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--robot",
        metavar="HOST:PORT",
        default=None,
        help="Run integration tests against a live SiLA2 server (e.g. 100.108.249.112:50051)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--robot"):
        return
    skip = pytest.mark.skip(reason="simulator-only test, skipped when --robot is set")
    for item in items:
        if item.get_closest_marker("simulator_only"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def robot_address(request: pytest.FixtureRequest) -> str | None:
    return request.config.getoption("--robot")


@pytest_asyncio.fixture
async def sila_channel(robot_address: str | None):
    """Yield (channel, pb).

    channel connects to the live robot when --robot is given, or to a local
    simulator otherwise.  pb (the protobuf codec) always comes from a local
    simulator because it is derived from the feature definitions, not the wire.
    """
    config = OpentronsOt2Config(
        use_simulator=True,
        sila_server=SiLAServerConfig(hostname="127.0.0.1", port=0, tls=False),
        cloud_server_endpoint=None,
        discovery=None,
    )
    gen = create_app(config)
    connector = await gen.__anext__()
    await connector.start()
    pb = connector.sila_server.protobuf
    address = robot_address or connector.sila_server._address

    channel = grpc.aio.insecure_channel(address)
    try:
        yield channel, pb
    finally:
        await channel.close()
        await connector.stop()
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()
