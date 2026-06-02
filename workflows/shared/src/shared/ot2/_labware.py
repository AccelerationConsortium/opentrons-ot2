from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import opentrons_shared_data

from ._constants import (
    APPROACH_CLEARANCE_MM,
    CALIBRATED_DECK_A,
    SLOT_ORIGINS,
    TIP_PRESS_MM,
    WORKING_CLEARANCE_MM,
)

_LABWARE_BASE = Path(opentrons_shared_data.__file__).parent / "data" / "labware" / "definitions" / "2"


def _load_definition(name: str) -> dict:
    labware_dir = _LABWARE_BASE / name
    versions = sorted(labware_dir.glob("*.json"), key=lambda p: int(p.stem))
    if not versions:
        msg = f"Labware '{name}' not found in opentrons_shared_data. Check the definition name."
        raise ValueError(msg)
    with open(versions[-1]) as f:
        return json.load(f)


@dataclasses.dataclass
class OT2Well:
    """
    A single well position expressed as absolute deck coordinates for the right mount.

    x, y    — horizontal position (mm) in the OT-2 deck coordinate system.
    approach_a — A-axis value for safe lateral positioning above the well.
    working_a  — A-axis value for the working depth (aspirate, dispense, or tip press).
    """

    x: float
    y: float
    approach_a: float
    working_a: float


class OT2Labware:
    """
    Wraps an opentrons labware definition and computes absolute deck coordinates
    for each well, given a deck slot and a calibrated deck height.

    The opentrons labware JSON defines well positions relative to the labware's
    front-left-bottom corner. This class adds the slot origin offset and the
    calibrated A-axis reference to produce coordinates ready for the SiLA
    motion_control_feature.
    """

    def __init__(
        self,
        definition_name: str,
        slot: int,
        calibrated_deck_a: float = CALIBRATED_DECK_A,
        approach_clearance_mm: float = APPROACH_CLEARANCE_MM,
        working_clearance_mm: float = WORKING_CLEARANCE_MM,
    ) -> None:
        self._def = _load_definition(definition_name)
        self._slot_x, self._slot_y = SLOT_ORIGINS[slot]
        self._deck_a = calibrated_deck_a
        self._approach_clearance = approach_clearance_mm
        self._working_clearance = working_clearance_mm
        self._z_dim: float = self._def["dimensions"]["zDimension"]

    @property
    def definition_name(self) -> str:
        return self._def.get("parameters", {}).get("loadName", "unknown")

    def __getitem__(self, well_id: str) -> OT2Well:
        w = self._def["wells"][well_id]
        x = self._slot_x + w["x"]
        y = self._slot_y + w["y"]
        # w["z"] = height from labware bottom to well bottom (mm).
        # A increases upward; CALIBRATED_DECK_A is A when tip is at deck surface.
        approach_a = self._deck_a + self._z_dim + self._approach_clearance
        working_a = self._deck_a + w["z"] + self._working_clearance
        return OT2Well(x=x, y=y, approach_a=approach_a, working_a=working_a)

    def column(self, n: int) -> list[OT2Well]:
        """Return wells A-H of column n (0-indexed)."""
        return [self[f"{r}{n + 1}"] for r in "ABCDEFGH"]

    def row(self, r: str) -> list[OT2Well]:
        """Return all 12 wells in a given row (e.g. 'A')."""
        return [self[f"{r}{c}"] for c in range(1, 13)]

    def __repr__(self) -> str:
        return f"OT2Labware({self.definition_name!r}, slot, deck_a={self._deck_a})"


class OT2TipRack(OT2Labware):
    """
    Tip rack with column-by-column tip tracking.

    next_tips() returns the A-row well of the next available column and advances
    the internal counter, mirroring tip_rack.next_tips() in the Hamilton SDK.
    """

    def __init__(self, definition_name: str, slot: int, **kwargs) -> None:
        # working_clearance_mm=0 so working_a lands at the press depth, not above
        super().__init__(definition_name, slot, working_clearance_mm=0.0, **kwargs)
        self._next_col: int = 0
        self._tip_press_mm = TIP_PRESS_MM

    def __getitem__(self, well_id: str) -> OT2Well:
        w = self._def["wells"][well_id]
        x = self._slot_x + w["x"]
        y = self._slot_y + w["y"]
        approach_a = self._deck_a + self._z_dim + self._approach_clearance
        # Press TIP_PRESS_MM below the labware top to seat the tip firmly.
        working_a = self._deck_a + self._z_dim - self._tip_press_mm
        return OT2Well(x=x, y=y, approach_a=approach_a, working_a=working_a)

    def next_tips(self) -> OT2Well:
        """Return the A-row well of the next available column; advance the counter."""
        if self._next_col >= 12:
            raise RuntimeError("No tips remaining in tip rack.")
        well = self[f"A{self._next_col + 1}"]
        self._next_col += 1
        return well

    @property
    def tips_remaining(self) -> int:
        return (12 - self._next_col) * 8
