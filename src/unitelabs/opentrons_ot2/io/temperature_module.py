"""Temperature Module IO wrapper."""

import logging

from opentrons.drivers.temp_deck.driver import TempDeckDriver

from ._types import Temperature

log = logging.getLogger(__name__)


class TemperatureModuleController:
    """Controller for Temperature Module using Opentrons driver."""

    def __init__(self, driver: TempDeckDriver):
        self._driver = driver

    @classmethod
    async def build(cls, port: str) -> "TemperatureModuleController":
        """
        Build a TemperatureModuleController.

        Args:
            port: Serial port path.

        Returns:
            Configured TemperatureModuleController.
        """
        driver = await TempDeckDriver.create(port=port, loop=None)
        await driver.connect()
        return cls(driver=driver)

    async def disconnect(self) -> None:
        """Disconnect from the module."""
        await self._driver.disconnect()

    async def is_connected(self) -> bool:
        """Check connection status."""
        return await self._driver.is_connected()

    async def set_temperature(self, temperature: float) -> None:
        """Set target temperature in Celsius."""
        await self._driver.set_temperature(celsius=temperature)

    async def get_temperature(self) -> Temperature:
        """Get current and target temperature."""
        t = await self._driver.get_temperature()
        return Temperature(current=t.current, target=t.target)

    async def deactivate(self) -> None:
        """Turn off temperature control."""
        await self._driver.deactivate()

    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        return await self._driver.get_device_info()
