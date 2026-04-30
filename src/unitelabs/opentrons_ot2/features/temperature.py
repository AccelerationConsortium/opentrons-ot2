"""SiLA2 feature for Temperature Module control."""

from unitelabs.cdk import sila

from ..io import TemperatureModuleController, Temperature


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

    @sila.UnobservableCommand()
    async def set_temperature(self, temperature: float) -> Temperature:
        """
        Set the target temperature.

        Args:
            temperature: Target temperature in Celsius (typically 4-95°C).

        Returns:
            Current and target temperature.
        """
        await self._controller.set_temperature(temperature)
        return await self._controller.get_temperature()

    @sila.UnobservableCommand()
    async def get_temperature(self) -> Temperature:
        """
        Get the current temperature.

        Returns:
            Current and target temperature.
        """
        return await self._controller.get_temperature()

    @sila.UnobservableCommand()
    async def deactivate(self) -> Temperature:
        """
        Turn off temperature control.

        Returns:
            Current temperature after deactivation.
        """
        await self._controller.deactivate()
        return await self._controller.get_temperature()

    @sila.UnobservableCommand()
    async def get_device_info(self) -> dict:
        """
        Get device information.

        Returns:
            Serial number, model, and firmware version.
        """
        return await self._controller.get_device_info()
