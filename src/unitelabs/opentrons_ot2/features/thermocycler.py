"""SiLA2 feature for Thermocycler module control."""

from dataclasses import dataclass

from unitelabs.cdk import sila

from ..io import DeviceInfo, ThermocyclerController, Temperature


@dataclass
class ThermocyclerStatus:
    """Current status of thermocycler module."""

    lid_temperature_current: float
    lid_temperature_target: float | None
    plate_temperature_current: float
    plate_temperature_target: float | None
    lid_status: str


class ThermocyclerFeature(sila.Feature):
    """
    SiLA2 feature for Thermocycler module.

    Provides commands for:
    - Lid control (open/close)
    - Lid temperature control
    - Plate (block) temperature control
    """

    def __init__(self, controller: ThermocyclerController):
        """
        Initialize the thermocycler feature.

        Args:
            controller: The ThermocyclerController instance.
        """
        super().__init__(originator="ca.accelerationconsortium", category="modules")
        self._controller = controller

    # ============ Lid Control ============

    @sila.UnobservableCommand()
    async def open_lid(self) -> str:
        """
        Open the thermocycler lid.

        Returns:
            Lid status after opening.
        """
        await self._controller.open_lid()
        return await self._controller.get_lid_status()

    @sila.UnobservableCommand()
    async def close_lid(self) -> str:
        """
        Close the thermocycler lid.

        Returns:
            Lid status after closing.
        """
        await self._controller.close_lid()
        return await self._controller.get_lid_status()

    @sila.UnobservableCommand()
    async def get_lid_status(self) -> str:
        """
        Get the current lid status.

        Returns:
            Lid status (open, closed, in_between, unknown).
        """
        return await self._controller.get_lid_status()

    # ============ Temperature Control ============

    @sila.UnobservableCommand()
    async def set_lid_temperature(self, temperature: float) -> Temperature:
        """
        Set the lid temperature.

        Args:
            temperature: Target temperature in Celsius.

        Returns:
            Current and target lid temperature.
        """
        await self._controller.set_lid_temperature(temperature)
        return await self._controller.get_lid_temperature()

    @sila.UnobservableCommand()
    async def get_lid_temperature(self) -> Temperature:
        """
        Get the current lid temperature.

        Returns:
            Current and target lid temperature.
        """
        return await self._controller.get_lid_temperature()

    @sila.UnobservableCommand()
    async def set_plate_temperature(
        self,
        temperature: float,
        hold_time: float | None = None,
        volume: float | None = None,
    ) -> Temperature:
        """
        Set the plate (block) temperature.

        Args:
            temperature: Target temperature in Celsius.
            hold_time: Optional hold time in seconds.
            volume: Optional sample volume in uL for better thermal control.

        Returns:
            Current and target plate temperature.
        """
        await self._controller.set_plate_temperature(
            temperature=temperature,
            hold_time=hold_time,
            volume=volume,
        )
        return await self._controller.get_plate_temperature()

    @sila.UnobservableCommand()
    async def get_plate_temperature(self) -> Temperature:
        """
        Get the current plate (block) temperature.

        Returns:
            Current and target plate temperature.
        """
        return await self._controller.get_plate_temperature()

    @sila.UnobservableCommand()
    async def deactivate_lid(self) -> Temperature:
        """
        Turn off the lid heater.

        Returns:
            Current lid temperature after deactivation.
        """
        await self._controller.deactivate_lid()
        return await self._controller.get_lid_temperature()

    @sila.UnobservableCommand()
    async def deactivate_block(self) -> Temperature:
        """
        Turn off the block heater/cooler.

        Returns:
            Current plate temperature after deactivation.
        """
        await self._controller.deactivate_block()
        return await self._controller.get_plate_temperature()

    @sila.UnobservableCommand()
    async def deactivate_all(self) -> ThermocyclerStatus:
        """
        Turn off all heating/cooling.

        Returns:
            Full status after deactivation.
        """
        await self._controller.deactivate_all()
        return await self.get_status()

    # ============ Status ============

    @sila.UnobservableCommand()
    async def get_status(self) -> ThermocyclerStatus:
        """
        Get complete module status.

        Returns:
            Lid temperature, plate temperature, and lid status.
        """
        lid_temp = await self._controller.get_lid_temperature()
        plate_temp = await self._controller.get_plate_temperature()
        lid_status = await self._controller.get_lid_status()

        return ThermocyclerStatus(
            lid_temperature_current=lid_temp.current,
            lid_temperature_target=lid_temp.target,
            plate_temperature_current=plate_temp.current,
            plate_temperature_target=plate_temp.target,
            lid_status=lid_status,
        )

    @sila.UnobservableCommand()
    async def get_device_info(self) -> DeviceInfo:
        """
        Get device information.

        Returns:
            Serial number, model, and firmware version.
        """
        return await self._controller.get_device_info()
