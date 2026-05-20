"""
IO wrapper using the Opentrons driver layer.

This module provides a thin wrapper around the existing Opentrons driver
classes, avoiding reimplementation of low-level serial communication.

Uses:
- opentrons.drivers.smoothie_drivers.driver_3_0.SmoothieDriver
- opentrons.drivers.rpi_drivers.gpio.GPIOCharDev
- opentrons.config.robot_configs for default configuration
"""

import logging

# Import Opentrons driver components
from opentrons.config.robot_configs import load_ot2
from opentrons.drivers.smoothie_drivers.driver_3_0 import SmoothieDriver
from opentrons.drivers.smoothie_drivers.constants import (
    AXES,
)
from opentrons.drivers.smoothie_drivers.errors import SmoothieAlarm, SmoothieError
from opentrons.drivers.rpi_drivers.gpio import GPIOCharDev
from opentrons.drivers.rpi_drivers.gpio_simulator import SimulatingGPIOCharDev


log = logging.getLogger(__name__)


class _RaisingSmoothieDriver(SmoothieDriver):
    """
    SmoothieDriver that raises on alarm lock instead of silently swallowing it.

    The upstream driver swallows 'alarm lock' and 'after halt you should home'
    outside of a hard halt to avoid masking the original exception during
    recovery. Outside that context the silent fallthrough hides motion failures
    from callers entirely, so we raise instead.
    """

    def _handle_return(self, ret_code: str, is_alarm: bool = False, is_error: bool = False) -> None:
        if self._is_hard_halting.is_set():
            if is_alarm:
                self._is_hard_halting.clear()
                raise SmoothieAlarm(ret_code)
            if is_error:
                raise SmoothieError(ret_code)
        else:
            if is_alarm or is_error:
                if "instrument found" in ret_code.lower():
                    log.info("smoothie: %s", ret_code)
                raise SmoothieError(ret_code)


# Default port on OT-2
DEFAULT_SMOOTHIE_PORT = "/dev/ttyAMA0"


class OT2MotionController:
    """
    High-level motion controller using Opentrons SmoothieDriver.

    This is a thin wrapper around the existing Opentrons driver that:
    1. Uses the battle-tested SmoothieDriver implementation
    2. Provides a simplified interface for SiLA2 integration
    3. Handles GPIO for lights and buttons
    """

    def __init__(
        self,
        smoothie_driver: SmoothieDriver,
        gpio: GPIOCharDev | SimulatingGPIOCharDev,
    ):
        """
        Initialize with existing driver instances.

        Use the build() classmethod for normal construction.
        """
        self._driver = smoothie_driver
        self._gpio = gpio
        # Snapshot the hardware-revision-correct defaults chosen by the driver at
        # init time, before any caller can mutate them via set_active_current etc.
        self._default_active_currents: dict[str, float] = dict(smoothie_driver._active_current_settings.now)
        self._default_dwelling_currents: dict[str, float] = dict(smoothie_driver._dwelling_current_settings.now)

    @classmethod
    async def build(
        cls,
        port: str = DEFAULT_SMOOTHIE_PORT,
        simulate: bool = False,
    ) -> "OT2MotionController":
        """
        Build an OT2MotionController.

        Args:
            port: Serial port for Smoothie (default: /dev/ttyAMA0).
            simulate: If True, use simulators instead of real hardware.

        Returns:
            Configured OT2MotionController instance.
        """
        config = load_ot2()

        if simulate:
            log.info("Building OT2MotionController in simulation mode")
            gpio = SimulatingGPIOCharDev("simulated")
            driver = SmoothieDriver(
                config=config,
                gpio_chardev=gpio,
                connection=None,  # None = simulation mode
            )
        else:
            log.info("Building OT2MotionController for real hardware on %s", port)
            gpio = GPIOCharDev("gpiochip0")
            gpio.config_by_board_rev()
            await gpio.setup()
            log.info("GPIO: %s", type(gpio).__name__)
            try:
                log.info("Connecting to Smoothie on %s ...", port)
                driver = await _RaisingSmoothieDriver.build(
                    port=port,
                    config=config,
                    gpio_chardev=gpio,
                )
                log.info("Smoothie connected on %s", port)
            except Exception:
                log.exception(
                    "Failed to connect to Smoothie on %s — "
                    "check that no other process holds the port (e.g. opentrons-robot-server)",
                    port,
                )
                raise

        return cls(smoothie_driver=driver, gpio=gpio)

    @property
    def is_simulating(self) -> bool:
        """Check if running in simulation mode."""
        return self._driver.simulating

    @property
    def position(self) -> dict[str, float]:
        """Get current cached position."""
        return self._driver.position

    @property
    def homed_flags(self) -> dict[str, bool]:
        """Get homing status per axis."""
        return self._driver.homed_flags

    # ============ Motion Control ============

    async def home(self, axes: str = AXES) -> dict[str, float]:
        """
        Home specified axes.

        Uses the full Opentrons homing sequence including:
        - Current management
        - Unstick moves for plunger axes
        - Proper X/Y sequencing with backoff

        Args:
            axes: String of axes to home (e.g., "XYZABC" or "ZA").

        Returns:
            Dict of axis positions after homing.
        """
        return await self._driver.home(axis=axes)

    async def move(
        self,
        target: dict[str, float],
        speed: float | None = None,
    ) -> None:
        """
        Move to target position.

        Uses the full Opentrons move implementation including:
        - Current management
        - Backlash compensation for plungers
        - Move splitting for stuck axes

        Args:
            target: Dict of axis -> position (e.g., {"X": 100.0, "Y": 50.0}).
            speed: Optional speed in mm/sec.
        """
        await self._driver.move(target=target, speed=speed)

    async def move_relative(
        self,
        deltas: dict[str, float],
        speed: float | None = None,
    ) -> None:
        """
        Move relative to current position.

        Args:
            deltas: Dict of axis -> delta (e.g., {"X": 10.0, "Z": -5.0}).
            speed: Optional speed in mm/sec.
        """
        current = self.position
        target = {ax: current.get(ax, 0) + delta for ax, delta in deltas.items()}
        await self.move(target, speed=speed)

    async def get_position(self) -> dict[str, float]:
        """
        Query current position from hardware.

        Updates the internal cache and returns the position.
        """
        await self._driver.update_position()
        return self.position

    async def probe_axis(
        self,
        axis: str,
        distance: float,
    ) -> dict[str, float]:
        """
        Probe along an axis until contact.

        Args:
            axis: Single axis character (X, Y, Z, A, B, C).
            distance: Maximum probing distance in mm.

        Returns:
            Position where probe was triggered.
        """
        return await self._driver.probe_axis(axis=axis, probing_distance=distance)

    async def aspirate(
        self,
        axis: str,
        volume_ul: float,
        ul_per_mm: float,
        flow_rate_ul_s: float,
    ) -> None:
        """Move plunger axis down by volume_ul to draw liquid."""
        distance_mm = volume_ul / ul_per_mm
        speed_mm_s = flow_rate_ul_s / ul_per_mm
        await self.move_relative({axis: -distance_mm}, speed=speed_mm_s)

    async def dispense(
        self,
        axis: str,
        volume_ul: float,
        ul_per_mm: float,
        flow_rate_ul_s: float,
    ) -> None:
        """Move plunger axis up by volume_ul to expel liquid."""
        distance_mm = volume_ul / ul_per_mm
        speed_mm_s = flow_rate_ul_s / ul_per_mm
        await self.move_relative({axis: +distance_mm}, speed=speed_mm_s)

    # ============ Motor Current ============

    def set_active_current(self, currents: dict[str, float]) -> None:
        """Set active (moving) current per axis. Keys are axis letters, values in amps."""
        self._driver.set_active_current(currents)

    def set_dwelling_current(self, currents: dict[str, float]) -> None:
        """Set dwelling (idle) current per axis. Keys are axis letters, values in amps."""
        self._driver.set_dwelling_current(currents)

    def push_active_current(self) -> None:
        """Save active-current state onto the driver stack for later restore."""
        self._driver.push_active_current()

    def pop_active_current(self) -> None:
        """Restore active-current state from the top of the driver stack."""
        self._driver.pop_active_current()

    def default_active_currents(self) -> dict[str, float]:
        """Return the active currents the driver was initialized with (hardware-revision-correct)."""
        return dict(self._default_active_currents)

    def default_dwelling_currents(self) -> dict[str, float]:
        """Return the dwelling currents the driver was initialized with (hardware-revision-correct)."""
        return dict(self._default_dwelling_currents)

    # ============ Pipette ============

    async def read_pipette_model(self, mount: str) -> str:
        """Read the model string from the pipette EEPROM. Returns '' if no pipette attached."""
        result = await self._driver.read_pipette_model(mount)
        return result or ""

    async def read_pipette_id(self, mount: str) -> str:
        """Read the unique ID from the pipette EEPROM. Returns '' if unreadable."""
        result = await self._driver.read_pipette_id(mount)
        return result or ""

    async def configure_mount(
        self,
        axis: str,
        steps_per_mm: float,
        home_position_mm: float,
        max_travel_mm: float,
        retract_mm: float,
    ) -> None:
        """Write steps/mm and motion limits for a pipette mount to the Smoothie."""
        await self._driver.update_steps_per_mm({axis: steps_per_mm})
        await self._driver.update_pipette_config(
            axis,
            {"home": home_position_mm, "max_travel": max_travel_mm, "retract": retract_mm},
        )

    async def stop(self) -> None:
        """Emergency stop - halt all motion."""
        await self._driver.hard_halt()

    def resume(self) -> None:
        """Resume after pause."""
        self._driver.resume()

    def pause(self) -> None:
        """Pause motion."""
        self._driver.pause()

    # ============ GPIO Control ============

    def set_button_light(
        self,
        red: bool = False,
        green: bool = False,
        blue: bool = False,
    ) -> None:
        """
        Set button LED color.

        Args:
            red: Enable red LED.
            green: Enable green LED.
            blue: Enable blue LED.
        """
        self._gpio.set_button_light(red=red, green=green, blue=blue)

    def set_rail_lights(self, on: bool) -> None:
        """
        Control deck rail lights.

        Args:
            on: True to turn on, False to turn off.
        """
        self._gpio.set_rail_lights(on=on)

    def read_button(self) -> bool:
        """
        Read front button state.

        Returns:
            True if button is pressed.
        """
        return self._gpio.read_button()

    def read_door_switch(self) -> bool:
        """
        Read door switch state.

        Returns:
            True if door is closed.
        """
        return self._gpio.read_window_switches()

    def get_button_light(self) -> tuple[bool, bool, bool]:
        """
        Get current button LED state.

        Returns:
            Tuple of (red, green, blue) states.
        """
        return self._gpio.get_button_light()

    def get_rail_lights(self) -> bool:
        """
        Get current rail lights state.

        Returns:
            True if lights are on.
        """
        return self._gpio.get_rail_lights()

    # ============ System Info ============

    async def get_firmware_version(self) -> str:
        """Get Smoothie firmware version."""
        return await self._driver.get_fw_version()

    # ============ Connection Management ============

    async def connect(self, port: str | None = None) -> None:
        """
        Connect to Smoothie (if not already connected).

        Args:
            port: Optional port override.
        """
        if not await self._driver.is_connected():
            await self._driver.connect(port=port)

    async def disconnect(self) -> None:
        """Disconnect from Smoothie."""
        await self._driver.disconnect()

    async def reset_from_error(self) -> None:
        """Clear alarm lock state (M999)."""
        await self._driver._reset_from_error()

    async def smoothie_reset(self) -> None:
        """Full hardware GPIO reset of the Smoothie."""
        await self._driver._smoothie_reset()

    async def is_connected(self) -> bool:
        """Check if connected to Smoothie."""
        return await self._driver.is_connected()
