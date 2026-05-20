"""SiLA2 feature for OT-2 pipette detection and configuration."""

from dataclasses import dataclass

from unitelabs.cdk import sila

from ..io import OT2MotionController
from .motion_control import Mount


@dataclass
class PipetteInfo:
    """
    Detected pipette on one mount.

    In simulation: model is "" (driver returns None), pipette_id is "1234567890".
    On hardware: model is e.g. "p300_single_v2.0", pipette_id is the unique serial.
    """

    mount: Mount
    model: str
    pipette_id: str


@dataclass
class PipetteConfig:
    """
    Motion parameters for a pipette mount.

    All distances in mm. Written to Smoothie EEPROM via M92 (steps/mm)
    and M365 (home, max_travel, retract).
    """

    steps_per_mm: float
    home_position_mm: float
    max_travel_mm: float
    retract_mm: float


class PipetteFeature(sila.Feature):
    """SiLA2 feature for pipette detection and mount configuration."""

    def __init__(self, controller: OT2MotionController):
        super().__init__(originator="ca.accelerationconsortium", category="robots")
        self._controller = controller

    @sila.UnobservableCommand()
    async def get_attached_pipettes(self) -> list[PipetteInfo]:
        """
        Read the model and ID from both pipette mounts.

        Returns:
            Two PipetteInfo entries (LEFT then RIGHT). model is "" if no pipette detected.
        """
        results = []
        for mount in Mount:
            mount_str = mount.name.lower()  # SmoothieDriver takes "left" / "right"
            model = await self._controller.read_pipette_model(mount_str)
            pipette_id = await self._controller.read_pipette_id(mount_str)
            results.append(PipetteInfo(mount=mount, model=model, pipette_id=pipette_id))
        return results

    @sila.UnobservableCommand()
    async def configure_mount(self, mount: Mount, config: PipetteConfig) -> None:
        """
        Write motor parameters for a pipette mount to the Smoothie.

        Sets steps/mm (M92) and motion limits (M365: home, max_travel, retract).

        Args:
            mount: Which mount to configure.
            config: Motor parameters for the attached pipette.
        """
        axis = mount.value.value  # Mount.LEFT -> Axis.B -> "B"
        await self._controller.configure_mount(
            axis,
            steps_per_mm=config.steps_per_mm,
            home_position_mm=config.home_position_mm,
            max_travel_mm=config.max_travel_mm,
            retract_mm=config.retract_mm,
        )
