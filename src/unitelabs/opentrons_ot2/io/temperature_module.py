"""Temperature Module IO wrapper."""

import logging

from opentrons.drivers.temp_deck.driver import TempDeckDriver

from ._module_base import ModuleControllerBase
from ._types import Temperature

log = logging.getLogger(__name__)


class TemperatureModuleController(ModuleControllerBase):
    """
    Controller for Temperature Module.

    Two backends are supported (see ``ModuleControllerBase``):

    - ``build(port=...)`` wraps a low-level ``TempDeckDriver`` that owns the serial
      port directly (standalone connector mode).
    - ``from_module(module)`` wraps the high-level ``TempDeck`` object already
      attached to a shared ``HardwareControlAPI`` (in-process robot-server mode).
    """

    @classmethod
    async def build(cls, port: str) -> "TemperatureModuleController":
        """
        Build a controller that owns the serial port via a low-level driver.

        Args:
            port: Serial port path.

        Returns:
            Configured TemperatureModuleController.
        """
        driver = await TempDeckDriver.create(port=port, loop=None)
        await driver.connect()
        return cls(driver=driver)

    async def set_temperature(self, temperature: float) -> None:
        """Set target temperature in Celsius (does not wait for the target to be reached)."""
        if self._module is not None:
            await self._module.start_set_temperature(temperature)
        else:
            await self._driver.set_temperature(celsius=temperature)

    async def get_temperature(self) -> Temperature:
        """Get current and target temperature."""
        if self._module is not None:
            return Temperature(current=self._module.temperature, target=self._module.target)
        t = await self._driver.get_temperature()
        return Temperature(current=t.current, target=t.target)

    async def deactivate(self) -> None:
        """Turn off temperature control."""
        if self._module is not None:
            await self._module.deactivate()
        else:
            await self._driver.deactivate()
