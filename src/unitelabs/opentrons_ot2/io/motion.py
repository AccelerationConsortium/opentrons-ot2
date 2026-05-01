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
from opentrons.drivers.rpi_drivers.gpio_simulator import SimulatingGPIOCharDev

# GPIOCharDev and build_gpio_chardev only available on Linux with gpiod
try:
    from opentrons.drivers.rpi_drivers import build_gpio_chardev
    from opentrons.drivers.rpi_drivers.gpio import GPIOCharDev
except ImportError:
    GPIOCharDev = SimulatingGPIOCharDev  # type: ignore[misc,assignment]

    def build_gpio_chardev(chip_name: str) -> SimulatingGPIOCharDev:  # type: ignore[misc]
        """Return a simulated GPIO device when gpiod is unavailable."""
        return SimulatingGPIOCharDev(chip_name)


log = logging.getLogger(__name__)

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
            # Use build_gpio_chardev for lights/button control. If board-revision
            # detection fails (incomplete pin map), fall back to SimulatingGPIOCharDev
            # for the Smoothie driver so reset-pin calls don't raise KeyError — motion
            # via serial still works, only GPIO peripherals (lights, button) are affected.
            real_gpio = build_gpio_chardev("gpiochip0")
            smoothie_gpio: GPIOCharDev | SimulatingGPIOCharDev
            if isinstance(real_gpio, SimulatingGPIOCharDev):
                log.warning("GPIO unavailable — check that no other process holds it (e.g. opentrons-robot-server)")
                smoothie_gpio = real_gpio
            else:
                try:
                    real_gpio.set_reset_pin(False)  # probe: will KeyError if pin map incomplete
                    smoothie_gpio = real_gpio
                    log.info("GPIO ready (%s)", type(real_gpio).__name__)
                except KeyError:
                    log.warning(
                        "GPIO pin map incomplete (board revision not detected) — "
                        "using simulated GPIO for Smoothie; lights and button unavailable"
                    )
                    smoothie_gpio = SimulatingGPIOCharDev("simulated")
            try:
                log.info("Connecting to Smoothie on %s ...", port)
                driver = await SmoothieDriver.build(
                    port=port,
                    config=config,
                    gpio_chardev=smoothie_gpio,
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

    async def stop(self) -> None:
        """Emergency stop - halt all motion."""
        await self._driver.hard_halt()

    async def resume(self) -> None:
        """Resume after pause."""
        self._driver.resume()

    async def pause(self) -> None:
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

    async def is_connected(self) -> bool:
        """Check if connected to Smoothie."""
        return await self._driver.is_connected()
