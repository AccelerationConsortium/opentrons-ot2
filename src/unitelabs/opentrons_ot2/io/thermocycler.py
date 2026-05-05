"""Thermocycler module IO wrapper."""

import logging

from opentrons.drivers.thermocycler.driver import ThermocyclerDriverV2

from ._types import Temperature

log = logging.getLogger(__name__)


class ThermocyclerController:
    """Controller for Thermocycler module using Opentrons driver."""

    def __init__(self, driver: ThermocyclerDriverV2):
        self._driver = driver

    @classmethod
    async def build(cls, port: str) -> "ThermocyclerController":
        """
        Build a ThermocyclerController.

        Args:
            port: Serial port path.

        Returns:
            Configured ThermocyclerController.
        """
        driver = await ThermocyclerDriverV2.create(port=port, loop=None)
        await driver.connect()
        return cls(driver=driver)

    async def disconnect(self) -> None:
        """Disconnect from the module."""
        await self._driver.disconnect()

    async def is_connected(self) -> bool:
        """Check connection status."""
        return await self._driver.is_connected()

    async def open_lid(self) -> None:
        """Open the lid."""
        await self._driver.open_lid()

    async def close_lid(self) -> None:
        """Close the lid."""
        await self._driver.close_lid()

    async def get_lid_status(self) -> str:
        """Get lid status (open/closed/in_between/unknown)."""
        return (await self._driver.get_lid_status()).name.lower()

    async def set_lid_temperature(self, temperature: float) -> None:
        """Set lid temperature in Celsius."""
        await self._driver.set_lid_temperature(temp=temperature)

    async def set_plate_temperature(
        self,
        temperature: float,
        hold_time: float | None = None,
        volume: float | None = None,
    ) -> None:
        """
        Set plate (block) temperature.

        Args:
            temperature: Target temperature in Celsius.
            hold_time: Optional hold time in seconds.
            volume: Optional sample volume in uL.
        """
        await self._driver.set_plate_temperature(
            temp=temperature,
            hold_time=hold_time,
            volume=volume,
        )

    async def get_lid_temperature(self) -> Temperature:
        """Get lid temperature."""
        t = await self._driver.get_lid_temperature()
        return Temperature(current=t.current, target=t.target)

    async def get_plate_temperature(self) -> Temperature:
        """Get plate (block) temperature."""
        t = await self._driver.get_plate_temperature()
        return Temperature(current=t.current, target=t.target)

    async def deactivate_lid(self) -> None:
        """Turn off lid heater."""
        await self._driver.deactivate_lid()

    async def deactivate_block(self) -> None:
        """Turn off block heater/cooler."""
        await self._driver.deactivate_block()

    async def deactivate_all(self) -> None:
        """Turn off all heating/cooling."""
        await self._driver.deactivate_all()

    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        return await self._driver.get_device_info()
