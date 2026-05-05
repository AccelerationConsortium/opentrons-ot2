"""Magnetic Module IO wrapper."""

import logging

from opentrons.drivers.mag_deck.driver import MagDeckDriver

log = logging.getLogger(__name__)


class MagneticModuleController:
    """Controller for Magnetic Module using Opentrons driver."""

    def __init__(self, driver: MagDeckDriver):
        self._driver = driver

    @classmethod
    async def build(cls, port: str) -> "MagneticModuleController":
        """
        Build a MagneticModuleController.

        Args:
            port: Serial port path.

        Returns:
            Configured MagneticModuleController.
        """
        driver = await MagDeckDriver.create(port=port, loop=None)
        await driver.connect()
        return cls(driver=driver)

    async def disconnect(self) -> None:
        """Disconnect from the module."""
        await self._driver.disconnect()

    async def is_connected(self) -> bool:
        """Check connection status."""
        return await self._driver.is_connected()

    async def engage(self, height: float) -> None:
        """
        Engage magnets at specified height.

        Args:
            height: Height from home in mm.
        """
        await self._driver.engage(height=height)

    async def disengage(self) -> None:
        """Disengage magnets (lower to home)."""
        await self._driver.disengage()

    async def get_mag_position(self) -> float:
        """Get current magnet position in mm."""
        return await self._driver.get_mag_position()

    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        return await self._driver.get_device_info()
