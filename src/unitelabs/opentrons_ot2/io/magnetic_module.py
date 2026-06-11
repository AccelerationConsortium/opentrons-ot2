"""Magnetic Module IO wrapper."""

import logging

from opentrons.drivers.mag_deck.driver import MagDeckDriver

from ._errors import EngageHeightOutOfRangeError
from ._module_base import ModuleControllerBase

log = logging.getLogger(__name__)


class MagneticModuleController(ModuleControllerBase):
    """
    Controller for Magnetic Module.

    Two backends are supported (see ``ModuleControllerBase``):

    - ``build(port=...)`` wraps a low-level ``MagDeckDriver`` that owns the serial
      port directly (standalone connector mode).
    - ``from_module(module)`` wraps the high-level ``MagDeck`` object already
      attached to a shared ``HardwareControlAPI`` (in-process robot-server mode).
    """

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

    async def engage(self, height: float) -> None:
        """
        Engage magnets at specified height.

        Args:
            height: Height from home in mm.

        Raises:
            EngageHeightOutOfRangeError: if height exceeds the module's allowed range.
        """
        try:
            if self._module is not None:
                await self._module.engage(height=height)
            else:
                await self._driver.engage(height=height)
        except ValueError as e:
            raise EngageHeightOutOfRangeError(str(e)) from e

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
