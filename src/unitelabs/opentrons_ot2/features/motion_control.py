"""
SiLA2 feature for OT-2 motion control.

Uses the OT2MotionController wrapper around Opentrons SmoothieDriver.
"""

from dataclasses import dataclass

from unitelabs.cdk import sila

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


# Valid axes
AXES = "XYZABC"


def _dict_to_position(pos: dict[str, float]) -> AxisPosition:
    """Convert position dict to AxisPosition dataclass."""
    return AxisPosition(
        x=pos.get("X", 0.0),
        y=pos.get("Y", 0.0),
        z=pos.get("Z", 0.0),
        a=pos.get("A", 0.0),
        b=pos.get("B", 0.0),
        c=pos.get("C", 0.0),
    )


class MotionControlFeature(sila.Feature):
    """
    SiLA2 feature for OT-2 motion control.

    Provides commands for gantry movement, homing, position queries,
    and emergency stop via the Opentrons SmoothieDriver.

    Axes:
    - X, Y: Gantry horizontal movement
    - Z: Left pipette mount vertical
    - A: Right pipette mount vertical
    - B: Left pipette plunger
    - C: Right pipette plunger
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
    async def home(self, axes: str = "XYZABC") -> HomeResult:
        """
        Home the specified axes.

        Uses the full Opentrons homing sequence including current management,
        unstick moves for plunger axes, and proper X/Y sequencing.

        Args:
            axes: String of axes to home (e.g., "XY", "ZABC", "XYZABC").
                  Default homes all axes. Valid axes: X, Y, Z, A, B, C.

        Returns:
            HomeResult with the homed axes and final position.
        """
        axes = axes.upper() or AXES
        valid_axes = set(AXES)
        requested = set(axes)

        if not requested.issubset(valid_axes):
            invalid = requested - valid_axes
            raise ValueError(f"Invalid axes: {invalid}. Valid axes are: {valid_axes}")

        position = await self._controller.home(axes=axes)

        return HomeResult(
            homed_axes=axes,
            position=_dict_to_position(position),
        )

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
        target = {
            "X": position.x,
            "Y": position.y,
            "Z": position.z,
            "A": position.a,
            "B": position.b,
            "C": position.c,
        }
        spd = speed if speed > 0 else None
        await self._controller.move(target=target, speed=spd)
        pos = await self._controller.get_position()
        return _dict_to_position(pos)

    @sila.UnobservableCommand()
    async def move_axis(self, axis: str, position: float, speed: float = 0.0) -> AxisPosition:
        """
        Move a single axis to an absolute position.

        Args:
            axis: Axis to move (X, Y, Z, A, B, or C).
            position: Target position in mm.
            speed: Movement speed in mm/sec (0 = default speed).

        Returns:
            The actual position after the move.
        """
        axis = axis.upper()
        if axis not in AXES:
            raise ValueError(f"Invalid axis: {axis}. Valid axes are: {AXES}")

        target = {axis: position}
        spd = speed if speed > 0 else None
        await self._controller.move(target=target, speed=spd)
        pos = await self._controller.get_position()
        return _dict_to_position(pos)

    @sila.UnobservableCommand()
    async def move_relative_axis(self, axis: str, delta: float, speed: float = 0.0) -> AxisPosition:
        """
        Move a single axis relative to current position.

        Args:
            axis: Axis to move (X, Y, Z, A, B, or C).
            delta: Distance to move in mm.
            speed: Movement speed in mm/sec (0 = default speed).

        Returns:
            The actual position after the move.
        """
        axis = axis.upper()
        if axis not in AXES:
            raise ValueError(f"Invalid axis: {axis}. Valid axes are: {AXES}")

        deltas = {axis: delta}
        spd = speed if speed > 0 else None
        await self._controller.move_relative(deltas=deltas, speed=spd)
        pos = await self._controller.get_position()
        return _dict_to_position(pos)

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
    async def probe(self, axis: str, distance: float) -> AxisPosition:
        """
        Probe along an axis until contact.

        Args:
            axis: Single axis to probe (X, Y, Z, A, B, or C).
            distance: Maximum probing distance in mm.

        Returns:
            Position where probe was triggered.
        """
        axis = axis.upper()
        if axis not in AXES:
            raise ValueError(f"Invalid axis: {axis}. Valid axes are: {AXES}")

        position = await self._controller.probe_axis(axis=axis, distance=distance)
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
        return HomedFlags(
            x=flags.get("X", False),
            y=flags.get("Y", False),
            z=flags.get("Z", False),
            a=flags.get("A", False),
            b=flags.get("B", False),
            c=flags.get("C", False),
        )

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
        r, g, b = self._controller.get_button_light()
        return ButtonLight(red=r, green=g, blue=b)

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
