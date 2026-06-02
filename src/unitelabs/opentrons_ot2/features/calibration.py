"""
SiLA2 feature for OT-2 Smoothie calibration writes.

Exposes the raw EEPROM write commands that the Opentrons hardware control
layer uses when configuring a pipette mount or recovering from an error:

  M92  — steps per mm (UpdateStepsPerMm)
  M365.0 — pipette home position (UpdatePipetteHome)
  M365.1 — max travel distance (UpdateMaxTravel)
  M365.2 — endstop debounce (UpdateEndstopDebounce, global — no axis)
  M365.3 — retract from endstop (UpdateRetractDistance)

Typical call sequence for a pipette mount (mirrors Opentrons controller.py):
  1. UpdateStepsPerMm — plunger axis (B or C)
  2. UpdatePipetteHome — mount axis (Z or A)
  3. UpdateMaxTravel — plunger axis (B or C)
  4. UpdateRetractDistance — plunger axis (B or C)
"""

import json
from dataclasses import dataclass
from pathlib import Path

import opentrons_shared_data
from unitelabs.cdk import sila

from ..io import OT2MotionController
from .motion_control import Axis

_TIPRACK_300UL_DIR = (
    Path(opentrons_shared_data.__file__).parent
    / "data"
    / "labware"
    / "definitions"
    / "2"
    / "opentrons_96_tiprack_300ul"
)


@dataclass
class RightMountCalibration:
    """Calibration values for the right pipette mount."""

    nozzle_deck_a: float
    """Machine A-axis value when the right nozzle (no tip) is exactly at deck Z=0.
    Derived from the robot's deck calibration matrix and pipette offset calibration.
    Use as CALIBRATED_DECK_A in OT2Labware / OT2Pipette."""

    tip_length_mm: float
    """Length of the standard 300 uL tip in mm (from opentrons_96_tiprack_300ul definition).
    Add this to working depths when a tip is attached."""


@dataclass
class StepsPerMm:
    """Steps-per-mm setting for one axis."""

    axis: Axis
    steps_per_mm: float


class CalibrationFeature(sila.Feature):
    """SiLA2 feature for raw Smoothie EEPROM calibration writes."""

    def __init__(self, controller: OT2MotionController):
        super().__init__(originator="ca.accelerationconsortium", category="robots")
        self._controller = controller

    @sila.UnobservableCommand()
    async def update_steps_per_mm(self, updates: list[StepsPerMm]) -> None:
        """
        Write steps/mm for one or more axes (M92).

        Gantry defaults (from robot config): X=80, Y=80, Z=400, A=400.
        Plunger defaults (from pipette type): B=768, C=768 for most gen2 pipettes.

        Args:
            updates: Per-axis steps/mm values. Only listed axes are updated.
        """
        await self._controller.update_steps_per_mm({u.axis.value: u.steps_per_mm for u in updates})

    @sila.UnobservableCommand()
    async def update_pipette_home(self, axis: Axis, home_position_mm: float) -> None:
        """
        Write the pipette home position for one axis (M365.0).

        Typically called with a mount axis (Z for left, A for right).
        Default: 220 mm.

        Args:
            axis: Axis to configure.
            home_position_mm: Home position in mm.
        """
        await self._controller.update_pipette_config(axis.value, {"home": home_position_mm})

    @sila.UnobservableCommand()
    async def update_max_travel(self, axis: Axis, max_travel_mm: float) -> None:
        """
        Write the max plunger travel distance for one axis (M365.1).

        Typically called with a plunger axis (B for left, C for right).
        Default: 30 mm.

        Args:
            axis: Axis to configure.
            max_travel_mm: Maximum travel in mm.
        """
        await self._controller.update_pipette_config(axis.value, {"max_travel": max_travel_mm})

    @sila.UnobservableCommand()
    async def update_retract_distance(self, axis: Axis, retract_mm: float) -> None:
        """
        Write the retract-from-endstop distance for one axis (M365.3).

        Typically called with a plunger axis (B for left, C for right).

        Args:
            axis: Axis to configure.
            retract_mm: Retract distance in mm.
        """
        await self._controller.update_pipette_config(axis.value, {"retract": retract_mm})

    @sila.UnobservableCommand()
    async def update_endstop_debounce(self, debounce_mm: float) -> None:
        """
        Write the endstop debounce distance (M365.2).

        This setting is global — the axis argument is ignored by the Smoothie firmware.
        Applies to all axes.

        Args:
            debounce_mm: Debounce distance in mm.
        """
        # Axis is required by the driver method signature but ignored for debounce.
        await self._controller.update_pipette_config("B", {"debounce": debounce_mm})

    @sila.UnobservableCommand()
    async def get_right_mount_calibration(self) -> RightMountCalibration:
        """
        Return calibration values for the right pipette mount.

        Reads the robot's stored deck calibration and pipette offset calibration to
        compute the A-axis value when the right nozzle is at deck Z=0. Also returns
        the standard 300 uL tip length. Together these let workflow code compute
        exact well positions without any hardcoded constants.

        The robot must be homed before calling this command so the current machine
        position is meaningful.

        Returns:
            RightMountCalibration with nozzle_deck_a and tip_length_mm.

        Raises:
            RuntimeError: If not running in with_robot_server mode (hw_api unavailable).
        """
        from opentrons.hardware_control.types import Axis as OTAxis, CriticalPoint
        from opentrons.types import Mount

        hw_api = self._controller._hw_api
        if hw_api is None:
            raise RuntimeError(
                "get_right_mount_calibration requires with_robot_server=True — "
                "the HardwareAPI is not available in standalone connector mode."
            )

        # Machine A position (right mount) from the Smoothie driver cache.
        machine_a = self._controller.position.get("A", 0.0)

        # Deck position of the right nozzle. current_position applies the full
        # calibration stack: deck attitude matrix + pipette offset + nozzle geometry.
        nozzle_deck_pos = await hw_api.current_position(Mount.RIGHT, critical_point=CriticalPoint.NOZZLE)
        nozzle_deck_z = nozzle_deck_pos.get(OTAxis.Z_R, 0.0)

        # When nozzle_deck_z = 0, machine_a = machine_a - nozzle_deck_z.
        calibrated_nozzle_deck_a = machine_a - nozzle_deck_z

        # Tip length from the opentrons_96_tiprack_300ul labware definition.
        versions = sorted(_TIPRACK_300UL_DIR.glob("*.json"), key=lambda p: int(p.stem))
        tiprack_def = json.loads(versions[-1].read_text())
        tip_length_mm = float(tiprack_def["parameters"]["tipLength"])

        return RightMountCalibration(
            nozzle_deck_a=calibrated_nozzle_deck_a,
            tip_length_mm=tip_length_mm,
        )
