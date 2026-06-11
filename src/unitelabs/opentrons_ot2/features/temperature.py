"""SiLA2 feature for Temperature Module control."""

import typing

from unitelabs.cdk import sila
from unitelabs.cdk.sila import constraints

from ..io import (
    COMMON_MODULE_ERRORS,
    DeviceInfo,
    TemperatureModuleController,
    Temperature,
)

# Sourced from opentrons: tempdeck QA-tested range 4-95 C
# (opentrons/hardware_control/modules/tempdeck.py, protocol_api/module_contexts.py).
_TempCelsius = typing.Annotated[float, constraints.MinimalInclusive(4.0), constraints.MaximalInclusive(95.0)]


class TemperatureModuleFeature(sila.Feature):
    """
    SiLA2 feature for Temperature Module.

    Provides commands for temperature control of samples on the deck.
    Temperature range is typically 4-95°C.
    """

    def __init__(self, controller: TemperatureModuleController):
        """
        Initialize the temperature module feature.

        Args:
            controller: The TemperatureModuleController instance.
        """
        super().__init__(originator="ca.accelerationconsortium", category="modules")
        self._controller = controller

    @sila.UnobservableCommand(errors=COMMON_MODULE_ERRORS)
    async def set_temperature(self, temperature_celsius: _TempCelsius) -> Temperature:
        """
        Set the target temperature.

        Args:
            temperature_celsius: Target temperature in Celsius (valid range 4-95 C).

        Returns:
            Current and target temperature.
        """
        await self._controller.set_temperature(temperature_celsius)
        return await self._controller.get_temperature()

    @sila.UnobservableCommand(errors=COMMON_MODULE_ERRORS)
    async def get_temperature(self) -> Temperature:
        """
        Get the current temperature.

        Returns:
            Current and target temperature.
        """
        return await self._controller.get_temperature()

    @sila.UnobservableCommand(errors=COMMON_MODULE_ERRORS)
    async def deactivate(self) -> Temperature:
        """
        Turn off temperature control.

        Returns:
            Current temperature after deactivation.
        """
        await self._controller.deactivate()
        return await self._controller.get_temperature()

    @sila.UnobservableCommand(errors=COMMON_MODULE_ERRORS)
    async def get_device_info(self) -> DeviceInfo:
        """
        Get device information.

        Returns:
            Serial number, model, and firmware version.
        """
        return await self._controller.get_device_info()
