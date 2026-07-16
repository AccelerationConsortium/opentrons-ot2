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
import typing
from dataclasses import dataclass
from pathlib import Path

import opentrons_shared_data
from unitelabs.cdk import sila

from ..io import OT2MotionController
from .motion_control import Axis, Mount

if typing.TYPE_CHECKING:
    from opentrons.hardware_control import HardwareControlAPI

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


@dataclass
class AttitudeRow:
    """One row of the 3x3 deck-calibration attitude matrix (dimensionless)."""

    col_x: float
    col_y: float
    col_z: float


@dataclass
class DeckCalibration:
    """
    The robot's stored deck-calibration attitude and its provenance.

    The attitude is the 3x3 matrix relating deck coordinates to machine
    coordinates. OT-2 deck calibration carries no translation (the deck offset is
    zero); clients should treat the offset as ``(0, 0, 0)``.
    """

    attitude: list[AttitudeRow]
    source: str
    """Where the calibration came from, e.g. ``"default"`` (never calibrated) or ``"user"``."""
    last_modified: str
    """ISO-8601 timestamp of the last calibration, or empty if never calibrated."""
    marked_bad: bool
    """True if the calibration has been flagged as bad and should not be trusted."""


@dataclass
class PipetteOffset:
    """
    The stored pipette-offset calibration for one mount.

    The offset is the calibrated position correction (mm) applied to that
    pipette. ``(0, 0, 0)`` with ``source="default"`` means the mount has not been
    calibrated.
    """

    mount: Mount
    x_mm: float
    y_mm: float
    z_mm: float
    pipette_model: str
    """Attached pipette model, e.g. ``"p300_multi_v2.1"`` (empty if none)."""
    pipette_id: str
    """Attached pipette serial/id (empty if none)."""
    source: str
    last_modified: str
    """ISO-8601 timestamp of the last calibration, or empty if never calibrated."""


class CalibrationUnavailableError(Exception):
    """
    The robot's stored calibration is not accessible.

    Raised when the feature runs without ``with_robot_server=True`` — the
    HardwareAPI that holds the stored calibration is not available in standalone
    connector mode.
    """


class NoPipetteOnMountError(Exception):
    """No pipette is attached to the requested mount, so it has no offset calibration."""


def _source_str(source: object) -> str:
    """Return a plain label for a calibration SourceType (e.g. ``"default"``)."""
    return str(getattr(source, "value", source) or "")


def _timestamp_str(timestamp: object) -> str:
    """Return an ISO-8601 string for a datetime, or empty if there is none."""
    return timestamp.isoformat() if timestamp is not None and hasattr(timestamp, "isoformat") else ""


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

    def _require_hw_api(self, command: str) -> "HardwareControlAPI":
        """Return the HardwareAPI or raise if it is not available (standalone mode)."""
        hw_api = self._controller._hw_api
        if hw_api is None:
            msg = (
                f"{command} requires with_robot_server=True — the HardwareAPI holding "
                "the stored calibration is not available in standalone connector mode."
            )
            raise CalibrationUnavailableError(msg)
        return hw_api

    @sila.UnobservableCommand(errors=[CalibrationUnavailableError])
    async def get_deck_calibration(self) -> DeckCalibration:
        """
        Return the robot's stored deck-calibration attitude and provenance.

        The attitude is the 3x3 matrix a client feeds to ``machine_from_deck`` to
        convert deck coordinates to machine coordinates. OT-2 deck calibration
        carries no translation, so the deck offset is zero.

        Returns:
            DeckCalibration with the attitude rows, source, timestamp, and bad flag.
        """
        hw_api = self._require_hw_api("get_deck_calibration")
        deck = hw_api.robot_calibration.deck_calibration
        rows = [AttitudeRow(col_x=float(r[0]), col_y=float(r[1]), col_z=float(r[2])) for r in deck.attitude]
        return DeckCalibration(
            attitude=rows,
            source=_source_str(deck.source),
            last_modified=_timestamp_str(deck.last_modified),
            marked_bad=bool(getattr(deck.status, "markedBad", False)),
        )

    @sila.UnobservableCommand(errors=[CalibrationUnavailableError, NoPipetteOnMountError])
    async def get_pipette_offset(self, mount: Mount) -> PipetteOffset:
        """
        Return the stored pipette-offset calibration for one mount.

        Args:
            mount: Which mount to read.

        Returns:
            PipetteOffset with the correction in mm, the attached pipette, and provenance.
        """
        from opentrons.types import Mount as OTMount

        hw_api = self._require_hw_api("get_pipette_offset")
        instrument = hw_api.hardware_instruments.get(OTMount[mount.name])
        if instrument is None:
            msg = f"no pipette attached to the {mount.name} mount"
            raise NoPipetteOnMountError(msg)
        calibration = instrument.pipette_offset
        offset = calibration.offset
        return PipetteOffset(
            mount=mount,
            x_mm=float(offset.x),
            y_mm=float(offset.y),
            z_mm=float(offset.z),
            pipette_model=str(instrument.model or ""),
            pipette_id=str(instrument.pipette_id or ""),
            source=_source_str(calibration.source),
            last_modified=_timestamp_str(calibration.last_modified),
        )

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
        from opentrons.hardware_control.motion_utilities import deck_from_machine
        from opentrons.hardware_control.types import Axis as OTAxis
        from opentrons.types import Point

        hw_api = self._controller._hw_api
        if hw_api is None:
            raise RuntimeError(
                "get_right_mount_calibration requires with_robot_server=True — "
                "the HardwareAPI is not available in standalone connector mode."
            )

        # Machine positions from the Smoothie driver cache (populated after homing).
        # hw_api.current_position() is intentionally avoided here: it requires the
        # hw_api's own homed-flags to be set, which they are not when homing was done
        # via the SiLA motion_control_feature (which calls the SmoothieDriver directly
        # rather than through the HardwareAPI's own home() path).
        pos = self._controller.position
        machine_a = pos.get("A", 0.0)

        # Deck attitude matrix from stored calibration.
        attitude = hw_api.robot_calibration.deck_calibration.attitude

        # Convert the current machine position to deck coordinates for the right mount.
        # deck_from_machine applies the inverse attitude transform — no homed-flag check.
        mount_deck = deck_from_machine(
            {OTAxis.X: pos.get("X", 0.0), OTAxis.Y: pos.get("Y", 0.0), OTAxis.Z_R: machine_a},
            attitude,
            Point(0, 0, 0),
            "OT-2 Standard",
        )
        mount_deck_z = mount_deck[OTAxis.Z_R]

        # Nozzle offset: distance from mount to nozzle end in deck Z (positive = below mount).
        # Read from the pipette model spec for the attached right pipette.
        nozzle_offset_z = await self._read_nozzle_offset_z()

        # Nozzle deck Z = mount deck Z - nozzle_offset_z
        # calibrated_nozzle_deck_a = machine A when nozzle is at deck Z=0
        #   = machine_a - nozzle_deck_z_current
        #   = machine_a - (mount_deck_z - nozzle_offset_z)
        calibrated_nozzle_deck_a = machine_a - (mount_deck_z - nozzle_offset_z)

        # Tip length from the opentrons_96_tiprack_300ul labware definition.
        versions = sorted(_TIPRACK_300UL_DIR.glob("*.json"), key=lambda p: int(p.stem))
        tiprack_def = json.loads(versions[-1].read_text())
        tip_length_mm = float(tiprack_def["parameters"]["tipLength"])

        return RightMountCalibration(
            nozzle_deck_a=calibrated_nozzle_deck_a,
            tip_length_mm=tip_length_mm,
        )

    async def _read_nozzle_offset_z(self) -> float:
        """
        Return the nozzle offset Z (mm) for the attached right-mount pipette.

        Reads the model string from the pipette EEPROM, then looks up the
        nozzleOffset[2] value from the opentrons pipette model spec. This is
        the distance from the mount carriage to the nozzle end in the downward
        direction (positive = below mount in deck coordinates).

        Falls back to the P300 multi gen2 value (35.52 mm) if the model is
        unreadable or not found.
        """
        _FALLBACK_NOZZLE_OFFSET_Z = 35.52  # P300 multi gen2 (v2.0 / v2.1)

        model = await self._controller.read_pipette_model("right")
        if not model:
            return _FALLBACK_NOZZLE_OFFSET_Z

        # Model strings are like "p300_multi_v2.0"; specs are keyed the same way.
        import opentrons_shared_data
        from pathlib import Path as _Path

        specs_path = (
            _Path(opentrons_shared_data.__file__).parent
            / "data"
            / "pipette"
            / "definitions"
            / "1"
            / "pipetteModelSpecs.json"
        )
        try:
            specs = json.loads(specs_path.read_text())
            offset = specs["config"][model]["nozzleOffset"]
            return float(offset[2])  # Z component
        except (KeyError, IndexError, ValueError):
            return _FALLBACK_NOZZLE_OFFSET_Z
