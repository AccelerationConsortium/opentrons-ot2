"""Heater-Shaker module IO wrapper."""

import logging

from opentrons.drivers.heater_shaker.driver import HeaterShakerDriver
from opentrons.drivers.heater_shaker.abstract import HeaterShakerLabwareLatchStatus
from opentrons.hardware_control.modules import HeaterShaker

from ._types import RPM, Temperature

log = logging.getLogger(__name__)


class HeaterShakerController:
    """
    Controller for Heater-Shaker module.

    Two backends are supported:

    - ``build(port=...)`` wraps a low-level ``HeaterShakerDriver`` that owns the
      serial port directly (standalone connector mode).
    - ``from_module(module)`` wraps the high-level ``HeaterShaker`` object already
      attached to a shared ``HardwareControlAPI`` (in-process robot-server mode),
      avoiding a second open of the module's serial port.
    """

    def __init__(self, driver: HeaterShakerDriver | None = None, module: HeaterShaker | None = None):
        self._driver = driver
        self._module = module

    @classmethod
    async def build(cls, port: str) -> "HeaterShakerController":
        """
        Build a controller that owns the serial port via a low-level driver.

        Args:
            port: Serial port path.

        Returns:
            Configured HeaterShakerController.
        """
        driver = await HeaterShakerDriver.create(port=port, loop=None)
        await driver.connect()
        return cls(driver=driver)

    @classmethod
    def from_module(cls, module: HeaterShaker) -> "HeaterShakerController":
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
            await self._driver.set_temperature(temperature=temperature)

    async def get_temperature(self) -> Temperature:
        """Get current and target temperature."""
        if self._module is not None:
            return Temperature(current=self._module.temperature, target=self._module.target_temperature)
        t = await self._driver.get_temperature()
        return Temperature(current=t.current, target=t.target)

    async def deactivate_heater(self) -> None:
        """Turn off the heater."""
        if self._module is not None:
            await self._module.deactivate_heater()
        else:
            await self._driver.deactivate_heater()

    async def set_rpm(self, rpm: int) -> None:
        """Set shaking speed in RPM."""
        if self._module is not None:
            await self._module.set_speed(rpm)
        else:
            await self._driver.set_rpm(rpm=rpm)

    async def get_rpm(self) -> RPM:
        """Get current and target RPM."""
        if self._module is not None:
            return RPM(current=self._module.speed, target=self._module.target_speed)
        r = await self._driver.get_rpm()
        return RPM(current=r.current, target=r.target)

    async def stop_shaking(self) -> None:
        """Stop shaking (home)."""
        if self._module is not None:
            await self._module.deactivate_shaker()
        else:
            await self._driver.home()

    async def open_latch(self) -> None:
        """Open the labware latch."""
        if self._module is not None:
            await self._module.open_labware_latch()
        else:
            await self._driver.open_labware_latch()

    async def close_latch(self) -> None:
        """Close the labware latch."""
        if self._module is not None:
            await self._module.close_labware_latch()
        else:
            await self._driver.close_labware_latch()

    async def get_latch_status(self) -> HeaterShakerLabwareLatchStatus:
        """Get latch status."""
        if self._module is not None:
            return self._module.labware_latch_status
        return await self._driver.get_labware_latch_status()

    async def get_device_info(self) -> dict:
        """Get device serial, model, version."""
        if self._module is not None:
            return dict(self._module.device_info)
        return await self._driver.get_device_info()
