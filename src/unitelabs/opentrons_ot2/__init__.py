import collections.abc
import dataclasses
import logging
from importlib.metadata import version

from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig

from .features import (
    HeaterShakerFeature,
    MagneticModuleFeature,
    MotionControlFeature,
    TemperatureModuleFeature,
    ThermocyclerFeature,
)
from .io import (
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

    motion_controller = await OT2MotionController.build(
        port=config.serial_port,
        simulate=config.use_simulator,
    )

    app = Connector(config)
    app.register(MotionControlFeature(motion_controller))

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
