"""
SiLA2 feature for OT-2 motion control.

Uses the OT2MotionController wrapper around Opentrons SmoothieDriver.
"""

import enum
import typing
from dataclasses import dataclass

from opentrons.drivers.smoothie_drivers.errors import TipProbeError
from unitelabs.cdk import sila
from unitelabs.cdk.sila import constraints

from ..io import OT2MotionController


@dataclass
class AxisPosition:
    """Position of all robot axes in mm."""

    x: float
    y: float
    z: float
    a: float
    b: float
    c: float


@dataclass
class HomeResult:
    """Result of a home operation."""

    homed_axes: str
    position: AxisPosition


@dataclass
class HomedFlags:
    """Homing status for each axis."""

    x: bool
    y: bool
    z: bool
    a: bool
    b: bool
    c: bool


@dataclass
class ButtonLight:
    """Button LED state."""

    red: bool
    green: bool
    blue: bool


class Axis(enum.Enum):
    """Robot axis. Value is the Smoothie axis letter."""

    X = "X"
    Y = "Y"
    Z = "Z"
    A = "A"
    B = "B"
    C = "C"


class Mount(enum.Enum):
    """Pipette mount. Value is the plunger Axis for that mount."""

    LEFT = Axis.B
    RIGHT = Axis.C


@dataclass
class AxisCurrent:
    """
    Motor current setting for a single axis.

    OT-2 hardware defaults (from opentrons/config/defaults_ot2.py):
        Active (moving):  X=1.25 A, Y=1.25 A, Z=0.8 A, A=0.8 A, B=0.05 A, C=0.05 A
        Dwelling (idle):  X=0.3 A,  Y=0.3 A,  Z=0.1 A,  A=0.1 A,  B=0.05 A, C=0.05 A
    """

    axis: Axis
    current_amps: typing.Annotated[float, constraints.MinimalInclusive(0.0), constraints.MaximalInclusive(2.0)]


def _dict_to_position(pos: dict[str, float]) -> AxisPosition:
    """Convert Smoothie position dict (string-keyed) to AxisPosition."""
    return AxisPosition(**{ax.value.lower(): pos.get(ax.value, 0.0) for ax in Axis})


class MotionControlFeature(sila.Feature):
    """
    SiLA2 feature for OT-2 motion control.

    Provides commands for gantry movement, homing, position queries,
    and emergency stop via the Opentrons SmoothieDriver.

    Axes:
    - X: Gantry right (+X) / left (-X). Limit switch at +X.
    - Y: Gantry back (+Y) / forward toward front window (-Y). Limit switch at +Y.
    - Z: Left pipette mount up (+Z) / down (-Z). Limit switch at +Z.
    - A: Right pipette mount up (+A) / down (-A). Limit switch at +A.
    - B: Left pipette plunger up (+B) / down (-B). Limit switch at +B.
    - C: Right pipette plunger up (+C) / down (-C). Limit switch at +C.
    """

    def __init__(self, controller: OT2MotionController):
        """
        Initialize the motion control feature.

        Args:
            controller: The OT2MotionController instance.
        """
        super().__init__(originator="ca.accelerationconsortium", category="robots")
        self._controller = controller

    @sila.UnobservableCommand()
    async def home(self, axes: list[Axis]) -> HomeResult:
        """
        Home the specified axes.

        Uses the full Opentrons homing sequence including current management,
        unstick moves for plunger axes, and proper X/Y sequencing.

        Args:
            axes: Axes to home. Pass all six to home the full robot.

        Returns:
            HomeResult with the homed axes and final position.
        """
        axes_str = "".join(a.value for a in axes)
        position = await self._controller.home(axes=axes_str)
        return HomeResult(homed_axes=axes_str, position=_dict_to_position(position))

    @sila.UnobservableCommand()
    async def move_to(self, position: AxisPosition, speed: float = 0.0) -> AxisPosition:
        """
        Move to an absolute position.

        Uses the full Opentrons move implementation including backlash
        compensation for plunger axes and current management.

        Args:
            position: Target position for all axes in mm.
            speed: Movement speed in mm/sec (0 = default speed).

        Returns:
            The actual position after the move.
        """
        target = {ax.value: getattr(position, ax.value.lower()) for ax in Axis}
        spd = speed if speed > 0 else None
        await self._controller.move(target=target, speed=spd)
        pos = await self._controller.get_position()
        return _dict_to_position(pos)

    @sila.UnobservableCommand()
    async def move_axis(self, axis: Axis, position: float, speed: float = 0.0) -> AxisPosition:
        """
        Move a single axis to an absolute position.

        Args:
            axis: Axis to move.
            position: Target position in mm.
            speed: Movement speed in mm/sec (0 = default speed).

        Returns:
            The actual position after the move.
        """
        spd = speed if speed > 0 else None
        await self._controller.move(target={axis.value: position}, speed=spd)
        return _dict_to_position(await self._controller.get_position())

    @sila.UnobservableCommand()
    async def move_relative_axis(self, axis: Axis, delta: float, speed: float = 0.0) -> AxisPosition:
        """
        Move a single axis relative to current position.

        Args:
            axis: Axis to move.
            delta: Distance to move in mm.
            speed: Movement speed in mm/sec (0 = default speed).

        Returns:
            The actual position after the move.
        """
        spd = speed if speed > 0 else None
        await self._controller.move_relative(deltas={axis.value: delta}, speed=spd)
        return _dict_to_position(await self._controller.get_position())

    @sila.UnobservableCommand()
    async def get_position(self) -> AxisPosition:
        """
        Get the current position of all axes.

        Returns:
            Current position of all axes in mm.
        """
        position = await self._controller.get_position()
        return _dict_to_position(position)

    @sila.UnobservableCommand()
    async def aspirate(
        self,
        mount: Mount,
        volume_ul: float,
        ul_per_mm: float,
        flow_rate_ul_s: float,
    ) -> AxisPosition:
        """
        Draw liquid by moving the plunger axis down.

        The connector exposes this primitive move only — liquid-class logic
        (blowout, mix, touch-tip, sequence ordering) stays on the client.

        Args:
            mount: Pipette mount (left = axis B, right = axis C).
            volume_ul: Volume to aspirate in µL.
            ul_per_mm: Plunger conversion factor for the attached pipette (µL/mm).
            flow_rate_ul_s: Aspiration flow rate in µL/s.

        Returns:
            Axis positions after the move.
        """
        axis = mount.value
        await self._controller.aspirate(axis.value, volume_ul, ul_per_mm, flow_rate_ul_s)
        return _dict_to_position(await self._controller.get_position())

    @sila.UnobservableCommand()
    async def dispense(
        self,
        mount: Mount,
        volume_ul: float,
        ul_per_mm: float,
        flow_rate_ul_s: float,
    ) -> AxisPosition:
        """
        Expel liquid by moving the plunger axis up.

        The connector exposes this primitive move only — liquid-class logic
        (blowout, mix, touch-tip, sequence ordering) stays on the client.

        Args:
            mount: Pipette mount (left = axis B, right = axis C).
            volume_ul: Volume to dispense in µL.
            ul_per_mm: Plunger conversion factor for the attached pipette (µL/mm).
            flow_rate_ul_s: Dispense flow rate in µL/s.

        Returns:
            Axis positions after the move.
        """
        axis = mount.value
        await self._controller.dispense(axis.value, volume_ul, ul_per_mm, flow_rate_ul_s)
        return _dict_to_position(await self._controller.get_position())

    @sila.UnobservableCommand(errors=[TipProbeError])
    async def probe(self, axis: Axis, distance: float) -> AxisPosition:
        """
        Probe along an axis until contact.

        Args:
            axis: Axis to probe.
            distance: Maximum probing distance in mm.

        Returns:
            Position where probe was triggered.
        """
        position = await self._controller.probe_axis(axis=axis.value, distance=distance)
        return _dict_to_position(position)

    @sila.UnobservableCommand()
    async def emergency_stop(self) -> str:
        """
        Emergency stop - immediately halt all motion.

        After calling this, you must re-home before resuming operation.

        Returns:
            Status message confirming the emergency stop.
        """
        await self._controller.stop()
        return "Emergency stop executed. Re-home required before resuming."

    @sila.UnobservableCommand()
    async def pause(self) -> str:
        """Pause motion execution."""
        self._controller.pause()
        return "Motion paused"

    @sila.UnobservableCommand()
    async def resume(self) -> str:
        """Resume motion execution after pause."""
        self._controller.resume()
        return "Motion resumed"

    @sila.UnobservableProperty()
    def is_simulating(self) -> bool:
        """Check if running in simulation mode."""
        return self._controller.is_simulating

    def _build_homed_flags(self) -> HomedFlags:
        flags = self._controller.homed_flags
        return HomedFlags(**{ax.value.lower(): flags.get(ax.value, False) for ax in Axis})

    @sila.UnobservableProperty()
    def homed_flags(self) -> HomedFlags:
        """Get homing status for each axis."""
        return self._build_homed_flags()

    @sila.UnobservableCommand()
    async def get_firmware_version(self) -> str:
        """Get the Smoothie firmware version."""
        return await self._controller.get_firmware_version()

    @sila.UnobservableCommand()
    async def reset_from_error(self) -> HomedFlags:
        """Clear alarm lock state (M999). Returns homed flags after reset."""
        await self._controller.reset_from_error()
        return self._build_homed_flags()

    @sila.UnobservableCommand()
    async def smoothie_reset(self) -> HomedFlags:
        """Perform a full hardware GPIO reset of the Smoothie. Returns homed flags after reset."""
        await self._controller.smoothie_reset()
        return self._build_homed_flags()

    # ============ GPIO Control ============

    @sila.UnobservableCommand()
    def set_button_light(
        self,
        red: bool = False,
        green: bool = False,
        blue: bool = False,
    ) -> ButtonLight:
        """
        Set the front button LED color.

        Args:
            red: Enable red LED.
            green: Enable green LED.
            blue: Enable blue LED.

        Returns:
            Current button light state.
        """
        self._controller.set_button_light(red=red, green=green, blue=blue)
        return ButtonLight(red=red, green=green, blue=blue)

    @sila.UnobservableCommand()
    def get_button_light(self) -> ButtonLight:
        """
        Get the current button LED state.

        Returns:
            Button light state with red, green, blue booleans.
        """
        r, g, b = self._controller.get_button_light()
        return ButtonLight(red=r, green=g, blue=b)

    @sila.UnobservableCommand()
    def set_rail_lights(self, on: bool) -> bool:
        """
        Control the deck rail lights.

        Args:
            on: True to turn on, False to turn off.

        Returns:
            Current rail lights state.
        """
        self._controller.set_rail_lights(on=on)
        return self._controller.get_rail_lights()

    @sila.UnobservableProperty()
    def rail_lights(self) -> bool:
        """Get the current rail lights state."""
        return self._controller.get_rail_lights()

    @sila.UnobservableCommand()
    def read_button(self) -> bool:
        """
        Read the front button state.

        Returns:
            True if button is pressed.
        """
        return self._controller.read_button()

    @sila.UnobservableCommand()
    def read_door_switch(self) -> bool:
        """
        Read the door/window switch state.

        Returns:
            True if door is closed.
        """
        return self._controller.read_door_switch()

    # ============ Motor Current ============

    @sila.UnobservableCommand()
    def set_active_currents(self, currents: list[AxisCurrent]) -> None:
        """
        Set the active (moving) current for one or more axes.

        Only the axes included in the list are updated; omitted axes keep their
        current value. Hardware limit: 0.0-2.0 A per axis.
        """
        self._controller.set_active_current({c.axis.value: c.current_amps for c in currents})

    @sila.UnobservableCommand()
    def set_dwelling_currents(self, currents: list[AxisCurrent]) -> None:
        """
        Set the dwelling (idle) current for one or more axes.

        Only the axes included in the list are updated; omitted axes keep their
        current value. Hardware limit: 0.0-2.0 A per axis.
        """
        self._controller.set_dwelling_current({c.axis.value: c.current_amps for c in currents})

    @sila.UnobservableCommand()
    def push_active_currents(self) -> None:
        """Save the current active-current state onto the driver stack."""
        self._controller.push_active_current()

    @sila.UnobservableCommand()
    def pop_active_currents(self) -> None:
        """Restore the active-current state from the top of the driver stack."""
        self._controller.pop_active_current()
