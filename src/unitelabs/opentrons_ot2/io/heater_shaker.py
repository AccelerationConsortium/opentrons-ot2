"""Heater-Shaker module IO wrapper."""

import logging

from opentrons.drivers.heater_shaker.driver import HeaterShakerDriver
from opentrons.drivers.heater_shaker.abstract import HeaterShakerLabwareLatchStatus

from ._types import RPM, Temperature

log = logging.getLogger(__name__)


class HeaterShakerController:
    """Controller for Heater-Shaker module using Opentrons driver."""

    def __init__(self, driver: HeaterShakerDriver):
        self._driver = driver

    @classmethod
    async def build(cls, port: str) -> "HeaterShakerController":
        """
        Build a HeaterShakerController.

        Args:
            port: Serial port path.

        Returns:
            Configured HeaterShakerController.
        """
        driver = await HeaterShakerDriver.create(port=port, loop=None)
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
        await self._driver.set_temperature(temperature=temperature)

    async def get_temperature(self) -> Temperature:
        """Get current and target temperature."""
        t = await self._driver.get_temperature()
        return Temperature(current=t.current, target=t.target)

    async def deactivate_heater(self) -> None:
        """Turn off the heater."""
        await self._driver.deactivate_heater()

    async def set_rpm(self, rpm: int) -> None:
        """Set shaking speed in RPM."""
        await self._driver.set_rpm(rpm=rpm)

    async def get_rpm(self) -> RPM:
        """Get current and target RPM."""
        r = await self._driver.get_rpm()
        return RPM(current=r.current, target=r.target)

    async def stop_shaking(self) -> None:
        """Stop shaking (home)."""
        await self._driver.home()

    async def open_latch(self) -> None:
        """Open the labware latch."""
        await self._driver.open_labware_latch()

    async def close_latch(self) -> None:
        """Close the labware latch."""
        await self._driver.close_labware_latch()

    async def get_latch_status(self) -> HeaterShakerLabwareLatchStatus:
        """Get latch status."""
        return await self._driver.get_labware_latch_status()

    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        return await self._driver.get_device_info()
