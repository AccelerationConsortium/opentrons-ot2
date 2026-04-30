"""
Module wrappers using the Opentrons driver layer.

This module provides thin wrappers around the existing Opentrons module drivers
(Heater-Shaker, Thermocycler, Temperature Deck, Magnetic Deck).
"""

import logging
from dataclasses import dataclass

# Import Opentrons module drivers
from opentrons.drivers.heater_shaker.driver import HeaterShakerDriver
from opentrons.drivers.heater_shaker.abstract import (
    HeaterShakerLabwareLatchStatus,
)
from opentrons.drivers.thermocycler.driver import ThermocyclerDriverV2
from opentrons.drivers.temp_deck.driver import TempDeckDriver
from opentrons.drivers.mag_deck.driver import MagDeckDriver

log = logging.getLogger(__name__)


@dataclass
class Temperature:
    """Temperature reading."""

    current: float
    target: float | None = None


@dataclass
class RPM:
    """RPM reading."""

    current: int
    target: int | None = None


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

    # Temperature control
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

    # Shaking control
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

    # Labware latch
    async def open_latch(self) -> None:
        """Open the labware latch."""
        await self._driver.open_labware_latch()

    async def close_latch(self) -> None:
        """Close the labware latch."""
        await self._driver.close_labware_latch()

    async def get_latch_status(self) -> HeaterShakerLabwareLatchStatus:
        """Get latch status."""
        return await self._driver.get_labware_latch_status()

    # Device info
    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        return await self._driver.get_device_info()


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

    # Lid control
    async def open_lid(self) -> None:
        """Open the lid."""
        await self._driver.open_lid()

    async def close_lid(self) -> None:
        """Close the lid."""
        await self._driver.close_lid()

    async def get_lid_status(self) -> str:
        """Get lid status (open/closed/in_between/unknown)."""
        return (await self._driver.get_lid_status()).name.lower()

    # Temperature control
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

    # Device info
    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        return await self._driver.get_device_info()


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

    # Temperature control
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

    # Device info
    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        return await self._driver.get_device_info()


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

    # Magnet control
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

    # Device info
    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        return await self._driver.get_device_info()
