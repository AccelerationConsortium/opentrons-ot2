"""Shared fixtures and options for integration tests.

Pass --robot HOST:PORT to run against a live SiLA2 server instead of the
built-in simulator.  The gRPC channel is redirected; the local simulator is
still started to obtain the protobuf codec object (pb).

Pass --robot-http HOST:PORT (or just --robot HOST:PORT, port is ignored) to run
HTTP API tests against the robot's built-in HTTP server on port 31950.  These
tests exercise the opentrons robot-server we start in-process with our injected
HardwareProxy.

Markers:
  simulator_only  — skipped when --robot is set
  robot_http_only — skipped unless --robot-http (or --robot) is set
"""

import contextlib

import grpc.aio
import httpx
import pytest
import pytest_asyncio

from unitelabs.cdk import SiLAServerConfig
from unitelabs.opentrons_ot2 import OpentronsOt2Config, create_app

_HTTP_API_PORT = 31950
_HTTP_API_VERSION_HEADER = "Opentrons-Version"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--robot",
        metavar="HOST:PORT",
        default=None,
        help="Run integration tests against a live SiLA2 server (e.g. 100.108.249.112:50051)",
    )
    parser.addoption(
        "--robot-http",
        metavar="HOST:PORT",
        default=None,
        help=(
            "Run HTTP API integration tests against a live robot "
            "(e.g. 100.108.249.112:31950). If omitted but --robot is set, the host "
            "is taken from --robot and port defaults to 31950."
        ),
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    has_robot = bool(config.getoption("--robot"))
    has_robot_http = bool(config.getoption("--robot-http")) or has_robot

    skip_sim = pytest.mark.skip(reason="simulator-only test, skipped when --robot is set")
    skip_http = pytest.mark.skip(reason="robot_http_only test, requires --robot-http or --robot")

    for item in items:
        if has_robot and item.get_closest_marker("simulator_only"):
            item.add_marker(skip_sim)
        if not has_robot_http and item.get_closest_marker("robot_http_only"):
            item.add_marker(skip_http)


@pytest.fixture(scope="session")
def robot_address(request: pytest.FixtureRequest) -> str | None:
    return request.config.getoption("--robot")


@pytest.fixture(scope="session")
def robot_http_url(request: pytest.FixtureRequest) -> str:
    """Base URL for the robot's opentrons HTTP API (port 31950).

    Derived from --robot-http HOST:PORT if given, otherwise from the host in
    --robot HOST:PORT with port fixed to 31950.
    """
    explicit = request.config.getoption("--robot-http")
    if explicit:
        host_port = explicit
        host = host_port.split(":")[0]
        port = host_port.split(":")[1] if ":" in host_port else str(_HTTP_API_PORT)
        return f"http://{host}:{port}"

    robot = request.config.getoption("--robot")
    if robot:
        host = robot.split(":")[0]
        return f"http://{host}:{_HTTP_API_PORT}"

    pytest.skip("--robot-http or --robot required for HTTP API tests")


@pytest.fixture(scope="session")
def http_client(robot_http_url: str) -> httpx.Client:
    """Synchronous httpx client pre-configured for the robot's HTTP API.

    Session-scoped: one connection is shared across all HTTP API tests.
    """
    with httpx.Client(
        base_url=robot_http_url,
        headers={_HTTP_API_VERSION_HEADER: "*"},
        timeout=10.0,
    ) as client:
        yield client


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
