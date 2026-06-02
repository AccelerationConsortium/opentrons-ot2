from __future__ import annotations

from ._constants import (
    P300_ASPIRATE_FLOW_RATE_UL_S,
    P300_DISPENSE_FLOW_RATE_UL_S,
    P300_UL_PER_MM,
    SAFE_TRAVEL_A,
    TRASH_X,
    TRASH_Y,
)
from ._labware import OT2Well

_MIX_VOLUME_FRACTION = 0.8  # mix at 80% of transfer volume when mix_after=True
_TRASH_LOWER_A = SAFE_TRAVEL_A - 30.0  # A value to enter trash opening
_TRASH_EJECT_DELTA = -20.0  # relative bump to eject tip into trash


class OT2Pipette:
    """
    High-level pipette operations for the OT-2 right mount (P300 8-Channel GEN2).

    Wraps motion_control_feature SiLA commands into labware-aware operations that
    mirror the MicrolabSTAR SDK interface used by the Hamilton workflow template:
      pick_up_tip / aspirate / dispense / discard_tip.

    Movement pattern: raise to safe travel height -> move X/Y -> lower to target.
    This avoids diagonal sweeps that could clip labware.

    Coordinate convention
    ---------------------
    OT2Labware computes well.approach_a and well.working_a assuming the NOZZLE
    is the reference point (no tip). For aspirate/dispense operations where a tip
    is attached, the working depth must be raised by tip_length_mm so the TIP END
    (not the nozzle) reaches the target liquid height. This class tracks the
    current tip length and applies that correction automatically.
    """

    def __init__(
        self,
        motion_control,
        tip_length_mm: float = 0.0,
        ul_per_mm: float = P300_UL_PER_MM,
        aspirate_flow_rate_ul_s: float = P300_ASPIRATE_FLOW_RATE_UL_S,
        dispense_flow_rate_ul_s: float = P300_DISPENSE_FLOW_RATE_UL_S,
        mix_cycles: int = 3,
    ) -> None:
        self._mc = motion_control
        self._tip_length_mm = tip_length_mm
        self._ul_per_mm = ul_per_mm
        self._aspirate_flow_rate = aspirate_flow_rate_ul_s
        self._dispense_flow_rate = dispense_flow_rate_ul_s
        self._mix_cycles = mix_cycles
        self.has_tip: bool = False
        self._current_tip_length: float = 0.0  # set on pick_up_tip, cleared on discard_tip

    # ------------------------------------------------------------------
    # Internal movement helpers
    # ------------------------------------------------------------------

    async def _raise(self) -> None:
        await self._mc.move_axis(axis="a", position=SAFE_TRAVEL_A, speed=0.0)

    async def _move_xy(self, x: float, y: float) -> None:
        await self._mc.move_axis(axis="x", position=x, speed=0.0)
        await self._mc.move_axis(axis="y", position=y, speed=0.0)

    async def _approach(self, well: OT2Well) -> None:
        """Raise, move X/Y, then lower to approach height above the well."""
        await self._raise()
        await self._move_xy(well.x, well.y)
        await self._mc.move_axis(axis="a", position=well.approach_a, speed=0.0)

    def _working_a(self, well: OT2Well) -> float:
        """
        Effective working depth for the current tip state.

        well.working_a is the NOZZLE position at working depth (no tip).
        When a tip is attached the nozzle must be higher by tip_length_mm so
        the tip end reaches the same deck height.
        """
        return well.working_a + self._current_tip_length

    # ------------------------------------------------------------------
    # Public interface (mirrors MicrolabSTAR lh.pipettes.*)
    # ------------------------------------------------------------------

    async def pick_up_tip(self, well: OT2Well) -> None:
        """Move to the tip rack well, press onto tips, retract."""
        await self._approach(well)
        # well.working_a for a tip rack is the nozzle press depth (no tip correction needed)
        await self._mc.move_axis(axis="a", position=well.working_a, speed=0.0)
        await self._raise()
        self.has_tip = True
        self._current_tip_length = self._tip_length_mm

    async def aspirate(self, wells: list[OT2Well], volume_ul: float) -> None:
        """
        Move above wells[0] (A-row of the column), descend to working depth,
        aspirate, then retract to approach height.

        The 8-channel pipette treats a column as a single unit — only the A-row
        position is needed for movement; all 8 channels engage simultaneously.
        """
        well = wells[0]
        await self._approach(well)
        await self._mc.move_axis(axis="a", position=self._working_a(well), speed=0.0)
        await self._mc.aspirate(
            mount="right",
            volume_ul=volume_ul,
            ul_per_mm=self._ul_per_mm,
            flow_rate_ul_s=self._aspirate_flow_rate,
        )
        await self._mc.move_axis(axis="a", position=well.approach_a, speed=0.0)

    async def dispense(
        self,
        wells: list[OT2Well],
        volume_ul: float,
        mix_after: bool = False,
        mix_volume_ul: float | None = None,
    ) -> None:
        """
        Move above wells[0], descend, dispense, optionally mix, then retract.

        mix_after runs self._mix_cycles of aspirate + dispense at the destination
        at mix_volume_ul (defaults to 80% of volume_ul).
        """
        well = wells[0]
        mix_vol = mix_volume_ul if mix_volume_ul is not None else volume_ul * _MIX_VOLUME_FRACTION
        await self._approach(well)
        await self._mc.move_axis(axis="a", position=self._working_a(well), speed=0.0)
        await self._mc.dispense(
            mount="right",
            volume_ul=volume_ul,
            ul_per_mm=self._ul_per_mm,
            flow_rate_ul_s=self._dispense_flow_rate,
        )
        if mix_after:
            for _ in range(self._mix_cycles):
                await self._mc.aspirate(
                    mount="right",
                    volume_ul=mix_vol,
                    ul_per_mm=self._ul_per_mm,
                    flow_rate_ul_s=self._aspirate_flow_rate,
                )
                await self._mc.dispense(
                    mount="right",
                    volume_ul=mix_vol,
                    ul_per_mm=self._ul_per_mm,
                    flow_rate_ul_s=self._dispense_flow_rate,
                )
        await self._mc.move_axis(axis="a", position=well.approach_a, speed=0.0)

    async def discard_tip(self) -> None:
        """Move to the fixed trash bin and eject the tip."""
        await self._raise()
        await self._move_xy(TRASH_X, TRASH_Y)
        await self._mc.move_axis(axis="a", position=_TRASH_LOWER_A, speed=0.0)
        await self._mc.move_relative_axis(axis="a", delta=_TRASH_EJECT_DELTA, speed=0.0)
        await self._raise()
        self.has_tip = False
        self._current_tip_length = 0.0
