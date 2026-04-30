"""
GPIO control for OT-2 Raspberry Pi.

Uses Linux character device interface for GPIO control.
This is a simplified implementation - the real OT-2 uses gpiod/libgpiod.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)


class DoorState(Enum):
    """Door switch state."""

    OPEN = "open"
    CLOSED = "closed"


@dataclass
class GPIOPins:
    """
    GPIO pin assignments for OT-2.

    These are the default pins - actual values depend on board revision.
    """

    # Button LED pins (accent colors)
    red_button: int = 6
    green_button: int = 19
    blue_button: int = 26

    # Deck rail lights
    frame_leds: int = 13

    # Button input
    button_input: int = 5

    # Door/window switches
    window_door_sw: int = 20
    window_sw_filt: int = 16
    door_sw_filt: int = 12

    # Smoothie control pins
    halt_pin: int = 18
    reset_pin: int = 24
    isp_pin: int = 25


class GPIOController:
    """
    GPIO controller using Linux sysfs interface.

    Note: On real OT-2, use libgpiod for proper chardev access.
    This implementation uses sysfs for compatibility.
    """

    GPIO_PATH = Path("/sys/class/gpio")

    def __init__(self, pins: GPIOPins | None = None):
        """
        Initialize GPIO controller.

        Args:
            pins: GPIO pin assignments. Uses defaults if None.
        """
        self._pins = pins or GPIOPins()
        self._exported: set[int] = set()

        # Cached states
        self._button_light = (False, False, False)
        self._rail_lights = False

    def _export_pin(self, pin: int) -> None:
        """Export a GPIO pin for use."""
        if pin in self._exported:
            return

        export_path = self.GPIO_PATH / "export"
        if export_path.exists():
            try:
                export_path.write_text(str(pin))
                self._exported.add(pin)
            except (OSError, PermissionError) as e:
                log.warning(f"Could not export GPIO {pin}: {e}")

    def _set_direction(self, pin: int, direction: str) -> None:
        """Set GPIO pin direction (in/out)."""
        direction_path = self.GPIO_PATH / f"gpio{pin}" / "direction"
        if direction_path.exists():
            try:
                direction_path.write_text(direction)
            except (OSError, PermissionError) as e:
                log.warning(f"Could not set direction for GPIO {pin}: {e}")

    def _write_pin(self, pin: int, value: bool) -> None:
        """Write value to GPIO pin."""
        value_path = self.GPIO_PATH / f"gpio{pin}" / "value"
        if value_path.exists():
            try:
                value_path.write_text("1" if value else "0")
            except (OSError, PermissionError) as e:
                log.warning(f"Could not write GPIO {pin}: {e}")

    def _read_pin(self, pin: int) -> bool:
        """Read value from GPIO pin."""
        value_path = self.GPIO_PATH / f"gpio{pin}" / "value"
        if value_path.exists():
            try:
                return value_path.read_text().strip() == "1"
            except (OSError, PermissionError) as e:
                log.warning(f"Could not read GPIO {pin}: {e}")
        return False

    def setup(self) -> None:
        """Initialize GPIO pins."""
        output_pins = [
            self._pins.red_button,
            self._pins.green_button,
            self._pins.blue_button,
            self._pins.frame_leds,
            self._pins.halt_pin,
            self._pins.reset_pin,
            self._pins.isp_pin,
        ]

        input_pins = [
            self._pins.button_input,
            self._pins.window_door_sw,
            self._pins.window_sw_filt,
            self._pins.door_sw_filt,
        ]

        for pin in output_pins:
            self._export_pin(pin)
            self._set_direction(pin, "out")

        for pin in input_pins:
            self._export_pin(pin)
            self._set_direction(pin, "in")

    def set_button_light(self, red: bool = False, green: bool = False, blue: bool = False) -> None:
        """
        Set button LED color.

        Args:
            red: Enable red LED.
            green: Enable green LED.
            blue: Enable blue LED.
        """
        self._write_pin(self._pins.red_button, red)
        self._write_pin(self._pins.green_button, green)
        self._write_pin(self._pins.blue_button, blue)
        self._button_light = (red, green, blue)

    def get_button_light(self) -> tuple[bool, bool, bool]:
        """
        Get current button LED state.

        Returns:
            Tuple of (red, green, blue) states.
        """
        return self._button_light

    def set_rail_lights(self, on: bool) -> None:
        """Turn deck rail lights on or off."""
        self._write_pin(self._pins.frame_leds, on)
        self._rail_lights = on

    def get_rail_lights(self) -> bool:
        """Get rail lights state."""
        return self._rail_lights

    def read_button(self) -> bool:
        """
        Read button press state.

        Returns:
            True if button is pressed.
        """
        # Button is active-low
        return not self._read_pin(self._pins.button_input)

    def read_door_switch(self) -> bool:
        """
        Read combined door/window switch.

        Returns:
            True if closed.
        """
        return self._read_pin(self._pins.window_door_sw)

    def read_top_window(self) -> bool:
        """Read top window switch."""
        return self._read_pin(self._pins.window_sw_filt)

    def read_front_door(self) -> bool:
        """Read front door switch."""
        return self._read_pin(self._pins.door_sw_filt)

    def get_door_state(self) -> DoorState:
        """Get door state."""
        return DoorState.CLOSED if self.read_door_switch() else DoorState.OPEN

    def set_halt_pin(self, on: bool) -> None:
        """Set the halt pin for emergency stop."""
        self._write_pin(self._pins.halt_pin, on)

    def set_reset_pin(self, on: bool) -> None:
        """Set the Smoothie reset pin."""
        self._write_pin(self._pins.reset_pin, on)

    def set_isp_pin(self, on: bool) -> None:
        """Set the ISP mode pin for firmware updates."""
        self._write_pin(self._pins.isp_pin, on)


class SimulatingGPIOController:
    """Simulated GPIO controller for testing."""

    def __init__(self):
        """Initialize simulator."""
        self._button_light = (False, False, False)
        self._rail_lights = False
        self._button_pressed = False
        self._door_closed = True

    def setup(self) -> None:
        """No-op for simulator."""
        log.info("Simulated GPIO initialized")

    def set_button_light(self, red: bool = False, green: bool = False, blue: bool = False) -> None:
        """Set simulated button LED."""
        self._button_light = (red, green, blue)

    def get_button_light(self) -> tuple[bool, bool, bool]:
        """Get simulated button LED state."""
        return self._button_light

    def set_rail_lights(self, on: bool) -> None:
        """Set simulated rail lights."""
        self._rail_lights = on

    def get_rail_lights(self) -> bool:
        """Get simulated rail lights state."""
        return self._rail_lights

    def read_button(self) -> bool:
        """Read simulated button state."""
        return self._button_pressed

    def read_door_switch(self) -> bool:
        """Read simulated door switch."""
        return self._door_closed

    def read_top_window(self) -> bool:
        """Read simulated top window."""
        return self._door_closed

    def read_front_door(self) -> bool:
        """Read simulated front door."""
        return self._door_closed

    def get_door_state(self) -> DoorState:
        """Get simulated door state."""
        return DoorState.CLOSED if self._door_closed else DoorState.OPEN

    def set_halt_pin(self, on: bool) -> None:
        """Simulate halt pin."""
        log.debug(f"Simulated halt pin: {on}")

    def set_reset_pin(self, on: bool) -> None:
        """Simulate reset pin."""
        log.debug(f"Simulated reset pin: {on}")

    def set_isp_pin(self, on: bool) -> None:
        """Simulate ISP pin."""
        log.debug(f"Simulated ISP pin: {on}")
