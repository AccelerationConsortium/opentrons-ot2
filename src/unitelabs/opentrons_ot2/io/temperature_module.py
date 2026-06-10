"""Temperature Module IO wrapper."""

import logging

from opentrons.drivers.temp_deck.driver import TempDeckDriver
from opentrons.hardware_control.modules import TempDeck

from ._types import Temperature

log = logging.getLogger(__name__)


class TemperatureModuleController:
    """
    Controller for Temperature Module.

    Two backends are supported:

    - ``build(port=...)`` wraps a low-level ``TempDeckDriver`` that owns the serial
      port directly (standalone connector mode).
    - ``from_module(module)`` wraps the high-level ``TempDeck`` object already
      attached to a shared ``HardwareControlAPI`` (in-process robot-server mode).
      This avoids opening the module's serial port a second time; the module's
      own poller serialises concurrent callers.
    """

    def __init__(self, driver: TempDeckDriver | None = None, module: TempDeck | None = None):
        self._driver = driver
        self._module = module

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

    @classmethod
    def from_module(cls, module: TempDeck) -> "TemperatureModuleController":
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

    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        if self._module is not None:
            return dict(self._module.device_info)
        return await self._driver.get_device_info()
