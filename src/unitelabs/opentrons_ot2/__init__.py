import collections.abc
import dataclasses
import logging
from importlib.metadata import version

from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig

from .features import MotionControlFeature
from .io import OT2MotionController

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
    """
    Create the connector application.

    Uses the Opentrons driver layer for motion and GPIO control.
    """
    log.info(
        "Starting Opentrons OT-2 connector v%s (simulate=%s, port=%s)",
        __version__,
        config.use_simulator,
        config.serial_port,
    )
    controller = await OT2MotionController.build(
        port=config.serial_port,
        simulate=config.use_simulator,
    )

    app = Connector(config)
    app.register(MotionControlFeature(controller))
    log.info(
        "SiLA server listening on %s:%d",
        config.sila_server.hostname,
        config.sila_server.port,
    )

    yield app

    await controller.disconnect()
