"""SiLA2 feature for Magnetic Module control."""

import typing
from dataclasses import dataclass

from unitelabs.cdk import sila
from unitelabs.cdk.sila import constraints

from ..io import (
    DeviceInfo,
    EngageHeightOutOfRangeError,
    MagneticModuleController,
    ModuleNotRespondingError,
    ModuleOperationError,
)

# Engage height has a model-dependent maximum (GEN1: 45 mm, GEN2: 25 mm — see
# opentrons MAX_ENGAGE_HEIGHT in hardware_control/modules/magdeck.py). Only the
# model-independent lower bound (>= 0) is constrained statically; the per-model
# maximum is enforced by the module, which raises if exceeded.
_HeightMm = typing.Annotated[float, constraints.MinimalInclusive(0.0)]


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

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError, EngageHeightOutOfRangeError])
    async def engage(self, height_mm: _HeightMm) -> MagnetStatus:
        """
        Engage the magnets at a specified height.

        Args:
            height_mm: Height from home position in mm. Must be >= 0; the maximum
                is model-dependent (45 mm GEN1, 25 mm GEN2) and enforced by the module.

        Returns:
            Magnet engagement status.
        """
        await self._controller.engage(height_mm)
        position = await self._controller.get_mag_position()
        return MagnetStatus(engaged=True, position=position)

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def disengage(self) -> MagnetStatus:
        """
        Disengage the magnets (lower to home position).

        Returns:
            Magnet disengagement status.
        """
        await self._controller.disengage()
        position = await self._controller.get_mag_position()
        return MagnetStatus(engaged=False, position=position)

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def get_position(self) -> float:
        """
        Get the current magnet position.

        Returns:
            Current position in mm from home.
        """
        return await self._controller.get_mag_position()

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def get_status(self) -> MagnetStatus:
        """
        Get the current magnet status.

        Returns:
            Engagement status and position.
        """
        position = await self._controller.get_mag_position()
        engaged = position > 0
        return MagnetStatus(engaged=engaged, position=position)

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def get_device_info(self) -> DeviceInfo:
        """
        Get device information.

        Returns:
            Serial number, model, and firmware version.
        """
        return await self._controller.get_device_info()
