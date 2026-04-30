"""SiLA2 feature for Magnetic Module control."""

from dataclasses import dataclass

from unitelabs.cdk import sila

from ..io import MagneticModuleController


@dataclass
class MagnetStatus:
    """Current status of magnetic module."""

    engaged: bool
    position: float


class MagneticModuleFeature(sila.Feature):
    """
    SiLA2 feature for Magnetic Module.

    Provides commands for engaging/disengaging magnets for
    bead-based separation workflows.
    """

    def __init__(self, controller: MagneticModuleController):
        """
        Initialize the magnetic module feature.

        Args:
            controller: The MagneticModuleController instance.
        """
        super().__init__(originator="ca.accelerationconsortium", category="modules")
        self._controller = controller

    @sila.UnobservableCommand()
    async def engage(self, height: float) -> MagnetStatus:
        """
        Engage the magnets at a specified height.

        Args:
            height: Height from home position in mm.

        Returns:
            Magnet engagement status.
        """
        await self._controller.engage(height)
        position = await self._controller.get_mag_position()
        return MagnetStatus(engaged=True, position=position)

    @sila.UnobservableCommand()
    async def disengage(self) -> MagnetStatus:
        """
        Disengage the magnets (lower to home position).

        Returns:
            Magnet disengagement status.
        """
        await self._controller.disengage()
        position = await self._controller.get_mag_position()
        return MagnetStatus(engaged=False, position=position)

    @sila.UnobservableCommand()
    async def get_position(self) -> float:
        """
        Get the current magnet position.

        Returns:
            Current position in mm from home.
        """
        return await self._controller.get_mag_position()

    @sila.UnobservableCommand()
    async def get_status(self) -> MagnetStatus:
        """
        Get the current magnet status.

        Returns:
            Engagement status and position.
        """
        position = await self._controller.get_mag_position()
        engaged = position > 0
        return MagnetStatus(engaged=engaged, position=position)

    @sila.UnobservableCommand()
    async def get_device_info(self) -> dict:
        """
        Get device information.

        Returns:
            Serial number, model, and firmware version.
        """
        return await self._controller.get_device_info()
