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
    """Run the opentrons HTTP robot-server in the same process, sharing one SmoothieDriver.

    When True, the connector builds a HardwareControlAPI, wraps it in HardwareProxy,
    and starts the robot-server FastAPI app on robot_server_port alongside the SiLA2
    gRPC server. Both share a single asyncio.Lock so serial commands cannot interleave.

    Only supported on the OT-2 with real hardware (use_simulator must be False).
    Requires the opentrons-robot-server package to be installed.
    """

    robot_server_port: int = 31950
    """TCP port for the opentrons HTTP API when with_robot_server=True."""

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
    """Create the connector application."""
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

    Both servers share a single HardwareControlAPI and asyncio.Lock via HardwareProxy,
    so serial commands to the Smoothie cannot interleave.

    Import note: robot_server.app_setup requires Python 3.8 (OT-2 system Python).
    The import is deferred to this function so dev-environment imports don't fail.
    """
    import uvicorn
    from opentrons.hardware_control import API

    # robot_server.hardware imports fine on all Python versions
    from robot_server.hardware import _hw_api_accessor, _init_task_accessor  # type: ignore[import]

    # robot_server.app_setup only importable on Python 3.8 (OT-2 system Python)
    from robot_server.app_setup import app as robot_server_app  # type: ignore[import]

    # Build one real HardwareControlAPI — this opens /dev/ttyAMA0
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

    # Start robot_server on its port in the background (same event loop, no thread)
    uv_config = uvicorn.Config(
        robot_server_app,
        host="0.0.0.0",
        port=config.robot_server_port,
        loop="none",
        log_level="info",
    )
    uv_server = uvicorn.Server(uv_config)
    robot_server_task = asyncio.create_task(uv_server.serve())
    log.info("robot-server starting on port %d", config.robot_server_port)

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
