import asyncio
import collections.abc
import dataclasses
import logging
from importlib.metadata import version

from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig

from .features import (
    CalibrationFeature,
    HeaterShakerFeature,
    MagneticModuleFeature,
    MotionControlFeature,
    PipetteFeature,
    TemperatureModuleFeature,
    ThermocyclerFeature,
)
from .io import (
    HardwareProxy,
    HeaterShakerController,
    MagneticModuleController,
    OT2MotionController,
    TemperatureModuleController,
    ThermocyclerController,
    scan_module_ports,
)

log = logging.getLogger(__name__)

__version__ = version("unitelabs-opentrons-ot2")


@dataclasses.dataclass
class OpentronsOt2Config(ConnectorBaseConfig):
    """Configuration for the Opentrons OT-2 connector."""

    use_simulator: bool = True
    """Whether to use the simulator backend instead of real hardware."""

    serial_port: str = "/dev/ttyAMA0"
    """Serial port for the Smoothie controller."""

    with_robot_server: bool = False
    """Run the opentrons HTTP robot-server in the same process, sharing one HardwareControlAPI.

    When True, the connector builds a HardwareControlAPI (real or simulated depending on
    ``use_simulator``), wraps it in HardwareProxy, and starts the robot-server FastAPI app
    alongside the SiLA2 gRPC server. Both share a single asyncio.Lock so serial commands
    cannot interleave.

    Requires the opentrons robot_server package to be installed.
    """

    robot_server_uds: str = "/run/aiohttp.sock"
    """Unix domain socket path for the opentrons HTTP API when with_robot_server=True.

    Used on the OT-2 where nginx proxies external port 31950 to this socket.
    Ignored when robot_server_tcp_port is set.
    """

    robot_server_tcp_port: int | None = None
    """TCP port for the opentrons HTTP API when with_robot_server=True.

    When set, uvicorn binds to 127.0.0.1 on this port instead of robot_server_uds.
    Useful for simulator/testing environments where a Unix socket is not needed.
    """

    sila_server: SiLAServerConfig = dataclasses.field(
        default_factory=lambda: SiLAServerConfig(
            name="Opentrons OT-2",
            type="LiquidHandler",
            description="SiLA2 connector for Opentrons OT-2 motion and GPIO control",
            version=str(__version__),
            vendor_url="https://opentrons.com/",
        )
    )


async def create_app(config: OpentronsOt2Config) -> collections.abc.AsyncGenerator[Connector, None]:
    """
    Create the connector application.

    When ``config.with_robot_server`` is False (the default / simulator mode) this starts
    only the SiLA2 gRPC server.

    When ``config.with_robot_server`` is True this starts *both* the SiLA2 gRPC server
    and the opentrons HTTP robot-server in the same process, sharing one
    ``HardwareControlAPI`` via ``HardwareProxy``.  The HTTP API is served on
    ``config.robot_server_uds`` (default ``/run/aiohttp.sock``), which nginx on the OT-2
    proxies to TCP port 31950.  This replaces the stock ``opentrons-robot-server`` systemd
    service, which must be disabled before deployment.

    See ``_create_app_with_robot_server`` for the in-process HTTP server startup details.
    """
    log.info(
        "Starting Opentrons OT-2 connector v%s (simulate=%s, port=%s)",
        __version__,
        config.use_simulator,
        config.serial_port,
    )

    if config.with_robot_server:
        async for connector in _create_app_with_robot_server(config):
            yield connector
        return

    motion_controller = await OT2MotionController.build(
        port=config.serial_port,
        simulate=config.use_simulator,
    )

    app = Connector(config)
    app.register(MotionControlFeature(motion_controller))
    app.register(PipetteFeature(motion_controller))
    app.register(CalibrationFeature(motion_controller))

    if not config.use_simulator:
        module_ports = scan_module_ports()
        module_controllers = []

        if "heater_shaker" in module_ports:
            hs = await HeaterShakerController.build(port=module_ports["heater_shaker"])
            app.register(HeaterShakerFeature(hs))
            module_controllers.append(hs)

        if "thermocycler" in module_ports:
            tc = await ThermocyclerController.build(port=module_ports["thermocycler"])
            app.register(ThermocyclerFeature(tc))
            module_controllers.append(tc)

        if "temperature" in module_ports:
            temp = await TemperatureModuleController.build(port=module_ports["temperature"])
            app.register(TemperatureModuleFeature(temp))
            module_controllers.append(temp)

        if "magnetic" in module_ports:
            mag = await MagneticModuleController.build(port=module_ports["magnetic"])
            app.register(MagneticModuleFeature(mag))
            module_controllers.append(mag)
    else:
        module_controllers = []

    log.info(
        "SiLA server listening on %s:%d",
        config.sila_server.hostname,
        config.sila_server.port,
    )

    yield app

    for mc in module_controllers:
        await mc.disconnect()
    await motion_controller.disconnect()


async def _create_app_with_robot_server(
    config: OpentronsOt2Config,
) -> collections.abc.AsyncGenerator[Connector, None]:
    """
    Start both the SiLA2 gRPC server and the opentrons HTTP robot-server in one process.

    Startup sequence
    ----------------
    1. ``API.build_hardware_controller`` opens ``/dev/ttyAMA0`` once.
    2. ``HardwareProxy`` wraps it with an ``asyncio.Lock`` — every serial command from
       either server acquires this lock, preventing interleaved writes.
    3. **App-state pre-population**: before uvicorn starts its lifespan, we set
       ``_init_task_accessor`` to a completed noop task and ``_hw_api_accessor`` to our
       proxy on ``robot_server_app.state``.  This causes ``start_initializing_hardware()``
       (called in the lifespan) to skip its own hardware init (it only acts when the task
       is ``None``), so the serial port is never opened a second time.
    4. uvicorn serves ``robot_server_app`` on ``config.robot_server_uds`` (a Unix domain
       socket).  nginx on the OT-2 proxies TCP 31950 → that socket.
    5. The SiLA2 ``Connector`` is built and yielded; modules are registered as found.

    Deferred imports
    ----------------
    ``robot_server`` is a system package on the OT-2 (not on PyPI).  All imports from it
    are deferred to this function so that the rest of the package can be imported in a
    dev environment without the robot-server installed.
    """
    import os

    import uvicorn
    from opentrons.hardware_control import API

    # Set environment variables the robot-server expects before importing it.
    # RUNNING_ON_PI enables real GPIO/hardware paths; OT_SMOOTHIE_ID identifies the port.
    # Only set these for real hardware — setting RUNNING_ON_PI=true in simulator mode
    # causes the opentrons library to attempt Pi-specific hardware init that hangs in CI.
    if not config.use_simulator:
        os.environ.setdefault("RUNNING_ON_PI", "true")
        os.environ.setdefault("OT_SMOOTHIE_ID", "AMA")

    from robot_server.hardware import _hw_api_accessor, _init_task_accessor  # type: ignore[import]
    from robot_server.app import app as robot_server_app  # type: ignore[import]

    if config.use_simulator:
        log.info("Building shared HardwareControlAPI (simulator)")
        real_api = await API.build_simulator()
    else:
        log.info("Building shared HardwareControlAPI on %s", config.serial_port)
        real_api = await API.build_hardware_controller(port=config.serial_port)

    shared_lock = asyncio.Lock()
    proxy = HardwareProxy(real_api, lock=shared_lock)
    motion_controller = OT2MotionController.from_api(real_api, lock=shared_lock)

    # Pre-populate robot_server app state before uvicorn starts its lifespan.
    # start_initializing_hardware() skips hardware init when initialize_task is not None,
    # so setting it here prevents robot_server from opening /dev/ttyAMA0 a second time.
    async def _noop() -> None:
        pass

    init_task: asyncio.Task[None] = asyncio.create_task(_noop())
    await init_task  # ensure .done() is True before lifespan reads it
    _init_task_accessor.set_on(robot_server_app.state, init_task)
    _hw_api_accessor.set_on(robot_server_app.state, proxy)

    # Start robot_server on either a TCP port (simulator/test) or a Unix domain socket
    # (production OT-2, where nginx proxies external port 31950 to the socket).
    if config.robot_server_tcp_port is not None:
        uv_config = uvicorn.Config(
            robot_server_app,
            host="127.0.0.1",
            port=config.robot_server_tcp_port,
            ws="wsproto",
            loop="none",
            log_level="info",
        )
        log.info("robot-server starting on 127.0.0.1:%d", config.robot_server_tcp_port)
    else:
        uv_config = uvicorn.Config(
            robot_server_app,
            uds=config.robot_server_uds,
            ws="wsproto",
            loop="none",
            log_level="info",
        )
    uv_server = uvicorn.Server(uv_config)
    robot_server_task = asyncio.create_task(uv_server.serve())
    if config.robot_server_tcp_port is None:
        log.info("robot-server starting on %s", config.robot_server_uds)

    # Build SiLA connector (modules same as standalone path)
    connector = Connector(config)
    connector.register(MotionControlFeature(motion_controller))
    connector.register(PipetteFeature(motion_controller))
    connector.register(CalibrationFeature(motion_controller))

    module_controllers = []
    module_ports = scan_module_ports()

    if "heater_shaker" in module_ports:
        hs = await HeaterShakerController.build(port=module_ports["heater_shaker"])
        connector.register(HeaterShakerFeature(hs))
        module_controllers.append(hs)

    if "thermocycler" in module_ports:
        tc = await ThermocyclerController.build(port=module_ports["thermocycler"])
        connector.register(ThermocyclerFeature(tc))
        module_controllers.append(tc)

    if "temperature" in module_ports:
        temp = await TemperatureModuleController.build(port=module_ports["temperature"])
        connector.register(TemperatureModuleFeature(temp))
        module_controllers.append(temp)

    if "magnetic" in module_ports:
        mag = await MagneticModuleController.build(port=module_ports["magnetic"])
        connector.register(MagneticModuleFeature(mag))
        module_controllers.append(mag)

    log.info(
        "SiLA server listening on %s:%d",
        config.sila_server.hostname,
        config.sila_server.port,
    )

    yield connector

    # Shutdown robot_server gracefully
    uv_server.should_exit = True
    await asyncio.gather(robot_server_task, return_exceptions=True)

    for mc in module_controllers:
        await mc.disconnect()
    await real_api.disconnect()
