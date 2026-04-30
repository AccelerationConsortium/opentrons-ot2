"""
Low-level serial communication with the Smoothie motion controller.

Based on the Opentrons GCode protocol:
- Serial connection at configurable baud rate (default 115200)
- Commands terminated with \\r\\n\\r\\n
- Responses acknowledged with "ok\\r\\nok\\r\\n"

Motor current, speed, and homing sequence based on Opentrons driver_3_0.py.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import serial
import serial.tools.list_ports

log = logging.getLogger(__name__)

SMOOTHIE_COMMAND_TERMINATOR = "\r\n\r\n"
SMOOTHIE_ACK = "ok\r\nok\r\n"
DEFAULT_TIMEOUT = 12.0
DEFAULT_BAUD_RATE = 115200

# Default port on OT-2 (internal UART on Raspberry Pi)
DEFAULT_SMOOTHIE_PORT = "/dev/ttyAMA0"

# Motor current settings from Opentrons (in Amps)
# Active currents (high) for movement/homing
ACTIVE_CURRENTS = {"X": 1.25, "Y": 1.25, "Z": 0.5, "A": 0.5, "B": 0.05, "C": 0.05}
# Dwelling currents (low) for holding position
DWELL_CURRENTS = {"X": 0.3, "Y": 0.3, "Z": 0.1, "A": 0.1, "B": 0.05, "C": 0.05}

# Homed positions (mm from home switch)
HOMED_POSITION = {"X": 418.0, "Y": 353.0, "Z": 218.0, "A": 218.0, "B": 19.0, "C": 19.0}

# Homing speeds (mm/sec)
XY_HOMING_SPEED = 80.0
Y_RETRACT_SPEED = 8.0
Y_RETRACT_DISTANCE = 3  # mm
Y_BACKOFF_SLOW_SPEED = 50.0
Y_BACKOFF_LOW_CURRENT = 0.8
Y_SWITCH_BACK_OFF_MM = 28
Y_SWITCH_REVERSE_BACK_OFF_MM = 10

# Unstick settings for B/C plunger axes
UNSTICK_DISTANCE = 1.0  # mm
UNSTICK_SPEED = 1.0  # mm/sec
CURRENT_CHANGE_DELAY = 0.005  # seconds

# Movement settings
DEFAULT_AXES_SPEED = 400.0  # mm/sec
PLUNGER_BACKLASH_MM = 0.3  # backlash compensation for B/C axes
GCODE_ROUNDING_PRECISION = 3  # decimal places for coordinates


class SmoothieError(Exception):
    """Error from Smoothie controller."""


@dataclass
class SmoothieConfig:
    """Configuration for the Smoothie connection."""

    baud_rate: int = DEFAULT_BAUD_RATE
    timeout: float = DEFAULT_TIMEOUT
    active_currents: dict = field(default_factory=lambda: ACTIVE_CURRENTS.copy())
    dwell_currents: dict = field(default_factory=lambda: DWELL_CURRENTS.copy())


def find_smoothie_port() -> str | None:
    """
    Find the Smoothie board serial port.

    On OT-2, the Smoothie communicates via internal UART (/dev/ttyAMA0).
    For external USB connections, searches for matching device descriptions.

    Returns:
        The port path (e.g., /dev/ttyAMA0) or None if not found.
    """
    import os

    # Check default OT-2 internal UART first
    if os.path.exists(DEFAULT_SMOOTHIE_PORT):
        return DEFAULT_SMOOTHIE_PORT

    # Search USB serial ports
    for port in serial.tools.list_ports.comports():
        if "smoothie" in port.description.lower() or "ft232" in port.description.lower():
            return port.device

    return None


class SmoothieConnection:
    """Async serial connection to the Smoothie controller."""

    def __init__(self, port: str, config: SmoothieConfig | None = None):
        """
        Initialize the connection.

        Args:
            port: Serial port path (e.g., /dev/ttyACM0).
            config: Optional configuration.
        """
        self._port = port
        self._config = config or SmoothieConfig()
        self._serial: serial.Serial | None = None
        self._lock = asyncio.Lock()
        self._position: dict[str, float] = dict.fromkeys("XYZABC", 0.0)
        self._speed: float = DEFAULT_AXES_SPEED

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._serial is not None and self._serial.is_open

    @property
    def position(self) -> dict[str, float]:
        """Get cached position."""
        return self._position.copy()

    async def connect(self) -> None:
        """Open the serial connection."""
        if self.is_connected:
            return

        loop = asyncio.get_event_loop()
        self._serial = await loop.run_in_executor(
            None,
            lambda: serial.Serial(
                port=self._port,
                baudrate=self._config.baud_rate,
                timeout=self._config.timeout,
            ),
        )
        await asyncio.sleep(0.5)
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        log.info(f"Connected to Smoothie at {self._port}")

    async def disconnect(self) -> None:
        """Close the serial connection."""
        if self._serial:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._serial.close)
            self._serial = None
            log.info("Disconnected from Smoothie")

    async def send_command(self, command: str, timeout: float | None = None, wait: bool = True) -> str:
        """
        Send a GCode command and wait for response.

        Args:
            command: GCode command (without terminator).
            timeout: Optional timeout override.
            wait: If True, send M400 after command to wait for execution (default: True).

        Returns:
            Response string from Smoothie.

        Raises:
            SmoothieError: If not connected, communication fails, or alarm detected.
        """
        if not self.is_connected:
            msg = "Not connected to Smoothie"
            raise SmoothieError(msg)

        async with self._lock:
            loop = asyncio.get_event_loop()
            full_command = command + SMOOTHIE_COMMAND_TERMINATOR

            await loop.run_in_executor(None, lambda: self._serial.write(full_command.encode()))

            response = await loop.run_in_executor(None, lambda: self._read_until_ack(timeout or self._config.timeout))

            # Check for alarm or error in response
            self._check_response(response, command)

            # Send M400 to wait for command execution (unless it's M400/M999 itself)
            if wait and not command.strip().upper().startswith(("M400", "M999")):
                await loop.run_in_executor(
                    None, lambda: self._serial.write(("M400" + SMOOTHIE_COMMAND_TERMINATOR).encode())
                )
                wait_response = await loop.run_in_executor(
                    None, lambda: self._read_until_ack(timeout or self._config.timeout)
                )
                self._check_response(wait_response, "M400")

            return response

    def _check_response(self, response: str, command: str) -> None:
        """
        Check response for alarm or error conditions.

        Args:
            response: Response string from Smoothie.
            command: The command that was sent (for error message).

        Raises:
            SmoothieError: If alarm or error detected.
        """
        lower = response.lower()

        # Check for alarm
        if "alarm" in lower:
            log.error(f"ALARM detected: command={command}, response={response}")
            raise SmoothieError(f"ALARM: {response}")

        # Check for error (but ignore "ok" which contains "o" and "k")
        if "error" in lower or "err:" in lower:
            # Ignore "alarm lock" errors during recovery
            if "alarm lock" not in lower and "after halt" not in lower:
                log.error(f"ERROR detected: command={command}, response={response}")
                raise SmoothieError(f"ERROR: {response}")

    async def reset_from_error(self) -> None:
        """
        Reset Smoothie from error/alarm state.

        Sends M999 to clear alarm and waits briefly for stabilization.
        """
        await asyncio.sleep(0.1)  # wait for smoothie to stabilize
        log.info("Resetting from error state (M999)")
        # Send M999 without wait (it clears the alarm)
        if self.is_connected:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._serial.write(("M999" + SMOOTHIE_COMMAND_TERMINATOR).encode())
            )
            await loop.run_in_executor(None, lambda: self._read_until_ack(self._config.timeout))
            await asyncio.sleep(0.1)

    def _read_until_ack(self, timeout: float) -> str:
        """Read response until we get the full ack (ok\\r\\nok\\r\\n)."""
        import time

        start = time.time()
        response = b""

        while time.time() - start < timeout:
            if self._serial.in_waiting:
                response += self._serial.read(self._serial.in_waiting)
            if SMOOTHIE_ACK.encode() in response:
                break
            time.sleep(0.01)

        return response.decode(errors="replace")

    async def _set_current(self, currents: dict[str, float]) -> None:
        """Set motor currents with M907 command."""
        cmd_parts = ["M907"] + [f"{ax}{val}" for ax, val in sorted(currents.items())]
        cmd = " ".join(cmd_parts)
        await self.send_command(cmd)
        await asyncio.sleep(CURRENT_CHANGE_DELAY)

    async def _activate_axes(self, axes: str) -> None:
        """Set axes to high current for movement."""
        currents = {ax: self._config.active_currents[ax] for ax in axes if ax in self._config.active_currents}
        if currents:
            await self._set_current(currents)
            log.debug(f"Activated axes {axes} with currents {currents}")

    async def _dwell_axes(self, axes: str) -> None:
        """Set axes to low current for holding."""
        currents = {ax: self._config.dwell_currents[ax] for ax in axes if ax in self._config.dwell_currents}
        if currents:
            await self._set_current(currents)
            log.debug(f"Dwelled axes {axes} with currents {currents}")

    async def _set_max_speed(self, speeds: dict[str, float]) -> None:
        """Set maximum axis speeds with M203.1 command."""
        cmd_parts = ["M203.1"] + [f"{ax}{val}" for ax, val in sorted(speeds.items())]
        await self.send_command(" ".join(cmd_parts))

    async def _check_limit_switches(self) -> dict[str, bool]:
        """Check limit switch states with M119 command."""
        resp = await self.send_command("M119")
        switches = {}
        for part in resp.split():
            if "_max:" in part.lower():
                ax = part.split("_")[0].upper()
                val = "1" in part
                switches[ax] = val
        return switches

    async def _unstick_axes(self, axes: str) -> None:
        """
        Move plunger axes slightly to break static friction before homing.

        Only applies to B and C axes (plungers). When at limit switch,
        we need to move away before we can home properly.
        """
        plunger_axes = [ax for ax in axes.upper() if ax in "BC"]
        if not plunger_axes:
            return

        log.info(f"Unsticking axes {plunger_axes}")

        # Set relative mode
        await self.send_command("G91", wait=False)

        # Move each axis down slightly at low speed
        # Use try/except because moving while at limit can trigger alarm
        for ax in plunger_axes:
            try:
                await self._activate_axes(ax)
                await self._set_max_speed({ax: UNSTICK_SPEED})
                # Move away from switch - use wait=False to avoid M400 during unstick
                await self.send_command(f"G0 {ax}-{UNSTICK_DISTANCE} F{UNSTICK_SPEED * 60}", wait=False)
            except SmoothieError:
                # If alarm during unstick, reset and continue
                log.warning(f"Alarm during unstick of {ax}, resetting")
                await self.reset_from_error()

        # Back to absolute mode
        await self.send_command("G90", wait=False)

    async def _home_x(self) -> None:
        """Home X axis with Y backoff sequence (Opentrons pattern)."""
        log.info("Homing X axis")

        # Move Y forward to clear any collision, using low current
        await self._set_current({"Y": Y_BACKOFF_LOW_CURRENT})
        await self._set_max_speed({"Y": Y_BACKOFF_SLOW_SPEED})

        # Relative move: back off Y switch, then reverse
        await self.send_command("G91")  # relative
        await self.send_command(f"G0 Y-{Y_SWITCH_BACK_OFF_MM}")
        await self.send_command(f"G0 Y{Y_SWITCH_REVERSE_BACK_OFF_MM}")
        await self.send_command("G90")  # absolute
        await self._dwell_axes("Y")

        # Now safe to home X
        await self._set_max_speed({"X": XY_HOMING_SPEED})
        await self._activate_axes("X")
        await self.send_command("G28.2 X", timeout=60)
        await self._dwell_axes("X")

    async def _home_y(self) -> None:
        """Home Y axis with retract sequence (Opentrons pattern)."""
        log.info("Homing Y axis")

        await self._set_max_speed({"Y": XY_HOMING_SPEED})
        await self._activate_axes("Y")

        # First home at fast speed
        await self.send_command("G28.2 Y", timeout=60)

        # Retract 3mm
        await self._set_max_speed({"Y": Y_RETRACT_SPEED})
        await self.send_command("G91")  # relative
        await self.send_command(f"G0 Y-{Y_RETRACT_DISTANCE}")
        await self.send_command("G90")  # absolute

        # Home again at slow speed for accuracy
        await self.send_command("G28.2 Y", timeout=30)

        # Retract again
        await self.send_command("G91")
        await self.send_command(f"G0 Y-{Y_RETRACT_DISTANCE}")
        await self.send_command("G90")

        await self._dwell_axes("Y")

    async def home(self, axes: str = "XYZABC") -> dict[str, float]:
        """
        Home specified axes using Opentrons homing sequence.

        Sequence: ZABC first, then X (with Y backoff), then Y (with retract).

        Args:
            axes: String of axes to home (e.g., "XYZABC" or "ZA").

        Returns:
            Dict of axis positions after homing.
        """
        axes = axes.upper()
        log.info(f"Homing axes: {axes}")

        # Clear any existing alarm
        await self.reset_from_error()

        # Check if B/C at limit switches - need to unstick first
        switches = await self._check_limit_switches()
        stuck_axes = [ax for ax in "BC" if ax in axes and switches.get(ax, False)]
        if stuck_axes:
            log.warning(f"Axes {stuck_axes} at limit switches, unsticking first")
            await self._unstick_axes("".join(stuck_axes))
            # Reset again after unstick in case of alarm
            await self.reset_from_error()

        # Home sequence: first ZABC (vertical), then X, then Y
        # ZABC can be homed together
        vertical_axes = "".join(ax for ax in "ZABC" if ax in axes)
        if vertical_axes:
            log.info(f"Homing vertical axes: {vertical_axes}")
            await self._activate_axes(vertical_axes)
            try:
                await self.send_command(f"G28.2 {vertical_axes}", timeout=120)
            except SmoothieError as e:
                log.warning(f"Alarm during homing vertical axes: {e}")
                await self.reset_from_error()
                # Retry homing
                await self.send_command(f"G28.2 {vertical_axes}", timeout=120)
            await self._dwell_axes(vertical_axes)

        # Home X (requires Y backoff)
        if "X" in axes:
            await self._home_x()

        # Home Y (with retract sequence)
        if "Y" in axes:
            await self._home_y()

        # Get final position
        resp = await self.send_command("M114.2")
        position = {}
        for part in resp.split():
            if ":" in part and part[0] in "XYZABC":
                try:
                    ax, val = part.split(":")
                    position[ax] = float(val)
                except (ValueError, IndexError):
                    pass

        # Update position cache
        self._position.update(position)

        log.info(f"Homing complete. Position: {position}")
        return position

    async def get_position(self) -> dict[str, float]:
        """
        Query current position from Smoothie and update cache.

        Returns:
            Dict of axis positions.
        """
        resp = await self.send_command("M114.2")
        position = {}
        for part in resp.split():
            if ":" in part and part[0] in "XYZABC":
                try:
                    ax, val = part.split(":")
                    position[ax] = float(val)
                except (ValueError, IndexError):
                    pass
        self._position.update(position)
        return position

    async def move(
        self,
        target: dict[str, float],
        speed: float | None = None,
    ) -> None:
        """
        Move to target position using Opentrons motion pattern.

        Implements:
        - Current management (activate moving axes, dwell non-moving)
        - Backlash compensation for B/C plunger axes
        - Speed control
        - Position cache update

        Args:
            target: Dict of axis -> position (e.g., {"X": 100.0, "Y": 50.0}).
            speed: Optional speed in mm/sec (default: 400).
        """
        from math import isclose

        # Filter to only axes that actually need to move
        moving_target = {}
        for ax, coord in target.items():
            ax = ax.upper()
            if ax not in "XYZABC":
                continue
            # Only include if significantly different from current position
            if not isclose(coord, self._position.get(ax, 0), rel_tol=1e-05, abs_tol=1e-08):
                moving_target[ax] = coord

        if not moving_target:
            log.debug(f"No axes need to move for target {target}")
            return

        log.info(f"Moving to {moving_target}")

        # Identify plunger axes moving in positive direction (need backlash compensation)
        plunger_backlash_axes = [
            ax for ax, val in moving_target.items() if ax in "BC" and self._position.get(ax, 0) < val
        ]

        # Build move target with backlash compensation
        backlash_target = {ax: moving_target[ax] for ax in plunger_backlash_axes}
        compensated_target = moving_target.copy()
        for ax in plunger_backlash_axes:
            compensated_target[ax] = moving_target[ax] + PLUNGER_BACKLASH_MM

        # Determine which axes are moving vs stationary
        moving_axes = "".join(moving_target.keys())
        non_moving_axes = "".join(ax for ax in "XYZABC" if ax not in moving_axes)

        # Set currents: activate moving, dwell non-moving
        await self._dwell_axes(non_moving_axes)
        await self._activate_axes(moving_axes)

        # Set speed
        move_speed = speed or self._speed

        # Build the move command
        # G0 X... Y... Z... F... (F is feedrate in mm/min, so multiply by 60)
        coord_parts = " ".join(
            f"{ax}{val:.{GCODE_ROUNDING_PRECISION}f}" for ax, val in sorted(compensated_target.items())
        )
        cmd = f"G0 {coord_parts} F{move_speed * 60:.0f}"

        try:
            await self.send_command(cmd)

            # If backlash compensation was applied, do correction move
            if backlash_target:
                correction_parts = " ".join(
                    f"{ax}{val:.{GCODE_ROUNDING_PRECISION}f}" for ax, val in sorted(backlash_target.items())
                )
                await self.send_command(f"G0 {correction_parts}")

            # Update position cache
            self._position.update(moving_target)

        finally:
            # Dwell plunger axes after movement (they get hot)
            plunger_moved = "".join(ax for ax in "BC" if ax in moving_axes)
            if plunger_moved:
                await self._dwell_axes(plunger_moved)

        log.debug(f"Move complete. Position: {self._position}")


class SimulatingSmoothieConnection:
    """Simulated Smoothie connection for testing."""

    def __init__(self):
        """Initialize the simulator."""
        self._position = {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0, "B": 0.0, "C": 0.0}
        self._homed = dict.fromkeys(self._position, False)
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    async def connect(self) -> None:
        """Simulate connection."""
        self._connected = True
        log.info("Connected to simulated Smoothie")

    async def disconnect(self) -> None:
        """Simulate disconnection."""
        self._connected = False
        log.info("Disconnected from simulated Smoothie")

    async def send_command(self, command: str, timeout: float | None = None) -> str:
        """
        Simulate command execution.

        Args:
            command: GCode command.
            timeout: Ignored in simulation.

        Returns:
            Simulated response.
        """
        cmd = command.strip().upper()

        if cmd.startswith("G28"):
            axes = cmd[4:].strip() or "XYZABC"
            for ax in axes:
                if ax in self._position:
                    self._position[ax] = 0.0
                    self._homed[ax] = True
            return "ok\r\nok\r\n"

        if cmd.startswith("G0"):
            parts = cmd[2:].strip().split()
            for part in parts:
                if part and part[0] in self._position:
                    try:
                        self._position[part[0]] = float(part[1:])
                    except ValueError:
                        pass
            return "ok\r\nok\r\n"

        if cmd.startswith("M114"):
            pos_str = " ".join(f"{ax}:{val:.3f}" for ax, val in self._position.items())
            return f"M114.2 {pos_str}\r\nok\r\nok\r\n"

        if cmd.startswith("M119"):
            return "M119 X:0 Y:0 Z:0 A:0 B:0 C:0\r\nok\r\nok\r\n"

        return "ok\r\nok\r\n"

    @property
    def position(self) -> dict[str, float]:
        """Get current simulated position."""
        return self._position.copy()
