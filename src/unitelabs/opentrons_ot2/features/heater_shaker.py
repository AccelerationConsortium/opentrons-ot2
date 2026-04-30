"""SiLA2 feature for Heater-Shaker module control."""

from dataclasses import dataclass

from unitelabs.cdk import sila

from ..io import HeaterShakerController, Temperature, RPM


@dataclass
class HeaterShakerStatus:
    """Current status of heater-shaker module."""

    temperature_current: float
    temperature_target: float | None
    rpm_current: int
    rpm_target: int | None
    latch_status: str


class HeaterShakerFeature(sila.Feature):
    """
    SiLA2 feature for Heater-Shaker module.

    Provides commands for:
    - Temperature control (heating)
    - Shaking control (orbital motion)
    - Labware latch control
    """

    def __init__(self, controller: HeaterShakerController):
        """
        Initialize the heater-shaker feature.

        Args:
            controller: The HeaterShakerController instance.
        """
        super().__init__(originator="ca.accelerationconsortium", category="modules")
        self._controller = controller

    @sila.UnobservableCommand()
    async def set_temperature(self, temperature: float) -> Temperature:
        """
        Set the target temperature.

        Args:
            temperature: Target temperature in Celsius.

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
    async def deactivate_heater(self) -> Temperature:
        """
        Turn off the heater.

        Returns:
            Current and target temperature after deactivation.
        """
        await self._controller.deactivate_heater()
        return await self._controller.get_temperature()

    @sila.UnobservableCommand()
    async def set_rpm(self, rpm: int) -> RPM:
        """
        Set the shaking speed.

        Args:
            rpm: Target speed in RPM (200-3000 typical range).

        Returns:
            Current and target RPM.
        """
        await self._controller.set_rpm(rpm)
        return await self._controller.get_rpm()

    @sila.UnobservableCommand()
    async def get_rpm(self) -> RPM:
        """
        Get the current shaking speed.

        Returns:
            Current and target RPM.
        """
        return await self._controller.get_rpm()

    @sila.UnobservableCommand()
    async def stop_shaking(self) -> RPM:
        """
        Stop shaking and return to home position.

        Returns:
            Current and target RPM after stopping.
        """
        await self._controller.stop_shaking()
        return await self._controller.get_rpm()

    @sila.UnobservableCommand()
    async def open_latch(self) -> str:
        """
        Open the labware latch.

        Returns:
            Latch status after opening.
        """
        await self._controller.open_latch()
        status = await self._controller.get_latch_status()
        return status.value

    @sila.UnobservableCommand()
    async def close_latch(self) -> str:
        """
        Close the labware latch.

        Returns:
            Latch status after closing.
        """
        await self._controller.close_latch()
        status = await self._controller.get_latch_status()
        return status.value

    @sila.UnobservableCommand()
    async def get_latch_status(self) -> str:
        """
        Get the current latch status.

        Returns:
            Latch status (idle_open, idle_closed, opening, closing, etc.).
        """
        status = await self._controller.get_latch_status()
        return status.value

    @sila.UnobservableCommand()
    async def get_status(self) -> HeaterShakerStatus:
        """
        Get complete module status.

        Returns:
            Temperature, RPM, and latch status.
        """
        temp = await self._controller.get_temperature()
        rpm = await self._controller.get_rpm()
        latch = await self._controller.get_latch_status()

        return HeaterShakerStatus(
            temperature_current=temp.current,
            temperature_target=temp.target,
            rpm_current=rpm.current,
            rpm_target=rpm.target,
            latch_status=latch.value,
        )

    @sila.UnobservableCommand()
    async def get_device_info(self) -> dict:
        """
        Get device information.

        Returns:
            Serial number, model, and firmware version.
        """
        return await self._controller.get_device_info()
