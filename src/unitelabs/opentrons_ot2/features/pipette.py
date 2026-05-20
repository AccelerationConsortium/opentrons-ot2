"""SiLA2 feature for OT-2 pipette detection."""

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


class PipetteFeature(sila.Feature):
    """SiLA2 feature for pipette detection."""

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
