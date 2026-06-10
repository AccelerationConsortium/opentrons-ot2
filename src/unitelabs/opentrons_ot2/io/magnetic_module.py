"""Magnetic Module IO wrapper."""

import logging

from opentrons.drivers.mag_deck.driver import MagDeckDriver
from opentrons.hardware_control.modules import MagDeck

log = logging.getLogger(__name__)


class MagneticModuleController:
    """
    Controller for Magnetic Module.

    Two backends are supported:

    - ``build(port=...)`` wraps a low-level ``MagDeckDriver`` that owns the serial
      port directly (standalone connector mode).
    - ``from_module(module)`` wraps the high-level ``MagDeck`` object already
      attached to a shared ``HardwareControlAPI`` (in-process robot-server mode),
      avoiding a second open of the module's serial port.
    """

    def __init__(self, driver: MagDeckDriver | None = None, module: MagDeck | None = None):
        self._driver = driver
        self._module = module

    @classmethod
    async def build(cls, port: str) -> "MagneticModuleController":
        """
        Build a controller that owns the serial port via a low-level driver.

        Args:
            port: Serial port path.

        Returns:
            Configured MagneticModuleController.
        """
        driver = await MagDeckDriver.create(port=port, loop=None)
        await driver.connect()
        return cls(driver=driver)

    @classmethod
    def from_module(cls, module: MagDeck) -> "MagneticModuleController":
        """Build a controller backed by a module already attached to a shared HardwareControlAPI."""
        return cls(module=module)

    async def disconnect(self) -> None:
        """Disconnect from the module. No-op when backed by a shared module (the API owns it)."""
        if self._module is None:
            await self._driver.disconnect()

    async def is_connected(self) -> bool:
        """Check connection status."""
        if self._module is not None:
            return True
        return await self._driver.is_connected()

    async def engage(self, height: float) -> None:
        """
        Engage magnets at specified height.

        Args:
            height: Height from home in mm.
        """
        if self._module is not None:
            await self._module.engage(height=height)
        else:
            await self._driver.engage(height=height)

    async def disengage(self) -> None:
        """Disengage magnets (lower to home)."""
        if self._module is not None:
            await self._module.deactivate()
        else:
            await self._driver.disengage()

    async def get_mag_position(self) -> float:
        """Get current magnet position in mm."""
        if self._module is not None:
            return self._module.current_height
        return await self._driver.get_mag_position()

    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        if self._module is not None:
            return dict(self._module.device_info)
        return await self._driver.get_device_info()
