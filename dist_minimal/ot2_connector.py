#!/usr/bin/env python3
"""Minimal OT-2 SiLA2 Connector - Single file distribution.

Usage:
    python ot2_connector.py [--port /dev/ttyACM0] [--simulate]

Requires: pyserial, unitelabs-cdk
"""

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

# Serial communication
import serial
import serial.tools.list_ports

# SiLA2 framework
from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig, sila

__version__ = "0.1.0"

# === GPIO Configuration ===
GPIO_PINS = {
    "button_red": 6,
    "button_green": 19,
    "button_blue": 26,
    "rail_lights": 13,
    "halt": 18,
    "reset": 24,
    "door_sw": 20,
    "button_input": 5,
}
GPIO_SYSFS = Path("/sys/class/gpio")

# === GCode Constants ===
GCODE_HOME = "G28.2"
GCODE_MOVE = "G0"
GCODE_GET_POSITION = "M114.2"
AXES = "XYZABC"
SMOOTHIE_VID, SMOOTHIE_PID = 0x04D8, 0xEE93
ACK = "ok\r\nok\r\n"
TERMINATOR = "\r\n\r\n"


# === Data Classes ===
@dataclass
class AxisPosition:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0


@dataclass
class ButtonLightState:
    red: bool = False
    green: bool = False
    blue: bool = False


# === IO: Smoothie Connection ===
def find_smoothie_port() -> str | None:
    for port in serial.tools.list_ports.comports():
        if port.vid == SMOOTHIE_VID and port.pid == SMOOTHIE_PID:
            return port.device
    return None


class SmoothieConnection:
    def __init__(self, port: str, baud_rate: int = 115200):
        self._port = port
        self._baud = baud_rate
        self._serial: serial.Serial | None = None
        self._lock = asyncio.Lock()

    async def connect(self):
        self._serial = serial.Serial(self._port, self._baud, timeout=5)
        await asyncio.sleep(1)
        if self._serial.in_waiting:
            self._serial.read(self._serial.in_waiting)

    async def disconnect(self):
        if self._serial:
            self._serial.close()
            self._serial = None

    async def send_command(self, command: str) -> str:
        if not self._serial:
            raise RuntimeError("Not connected")
        async with self._lock:
            self._serial.write(f"{command}{TERMINATOR}".encode())
            response = b""
            while ACK.encode() not in response:
                chunk = self._serial.read(self._serial.in_waiting or 1)
                if chunk:
                    response += chunk
                await asyncio.sleep(0.01)
            return response.decode(errors="replace")


class SimulatingSmoothieConnection:
    def __init__(self):
        self._position = dict.fromkeys(AXES, 0.0)

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def send_command(self, command: str) -> str:
        parts = command.split()
        cmd = parts[0] if parts else ""
        if cmd == GCODE_GET_POSITION:
            pos_str = " ".join(f"{ax}:{self._position[ax]:.3f}" for ax in AXES)
            return f"M114.2 {pos_str} ok\r\nok\r\n"
        if cmd == GCODE_MOVE:
            for part in parts[1:]:
                if part[0] in AXES:
                    self._position[part[0]] = float(part[1:])
        elif cmd == GCODE_HOME:
            for ax in AXES:
                if ax in command:
                    self._position[ax] = 0.0
        return "ok\r\nok\r\n"


# === IO: GPIO Controller ===
class GPIOController:
    def __init__(self):
        self._exported: set[int] = set()
        self._button_state = [False, False, False]
        self._rail_state = False

    def _export(self, pin: int):
        if pin not in self._exported:
            (GPIO_SYSFS / "export").write_text(str(pin))
            self._exported.add(pin)

    def _set_direction(self, pin: int, direction: str):
        (GPIO_SYSFS / f"gpio{pin}" / "direction").write_text(direction)

    def _write(self, pin: int, value: bool):
        (GPIO_SYSFS / f"gpio{pin}" / "value").write_text("1" if value else "0")

    def _read(self, pin: int) -> bool:
        return (GPIO_SYSFS / f"gpio{pin}" / "value").read_text().strip() == "1"

    def setup(self):
        for name, pin in GPIO_PINS.items():
            self._export(pin)
            direction = "in" if name in ("door_sw", "button_input") else "out"
            self._set_direction(pin, direction)

    def set_button_light(self, red: bool = False, green: bool = False, blue: bool = False):
        self._write(GPIO_PINS["button_red"], red)
        self._write(GPIO_PINS["button_green"], green)
        self._write(GPIO_PINS["button_blue"], blue)
        self._button_state = [red, green, blue]

    def get_button_light(self) -> tuple[bool, bool, bool]:
        return tuple(self._button_state)

    def set_rail_lights(self, on: bool):
        self._write(GPIO_PINS["rail_lights"], on)
        self._rail_state = on

    def get_rail_lights(self) -> bool:
        return self._rail_state

    def read_button(self) -> bool:
        return self._read(GPIO_PINS["button_input"])

    def read_door_switch(self) -> bool:
        return self._read(GPIO_PINS["door_sw"])

    def set_halt_pin(self, active: bool):
        self._write(GPIO_PINS["halt"], active)

    def set_reset_pin(self, active: bool):
        self._write(GPIO_PINS["reset"], active)


class SimulatingGPIOController:
    def __init__(self):
        self._button = [False, False, False]
        self._rails = False
        self._door = True

    def setup(self):
        pass

    def set_button_light(self, red=False, green=False, blue=False):
        self._button = [red, green, blue]

    def get_button_light(self):
        return tuple(self._button)

    def set_rail_lights(self, on):
        self._rails = on

    def get_rail_lights(self):
        return self._rails

    def read_button(self):
        return False

    def read_door_switch(self):
        return self._door

    def set_halt_pin(self, active):
        pass

    def set_reset_pin(self, active):
        pass


# === SiLA2 Feature: Motion Control ===
class MotionControlFeature(sila.Feature):
    def __init__(self, conn, gpio):
        super().__init__(originator="ca.accelerationconsortium", category="robots")
        self._conn = conn
        self._gpio = gpio
        self._position = dict.fromkeys(AXES, 0.0)

    def _parse_position(self, response: str) -> dict[str, float]:
        pos = {}
        for match in re.finditer(r"([XYZABC]):(-?\d+\.?\d*)", response):
            pos[match.group(1)] = float(match.group(2))
        return pos

    def _to_dataclass(self, pos: dict) -> AxisPosition:
        return AxisPosition(**{k.lower(): pos.get(k, 0.0) for k in AXES})

    @sila.UnobservableCommand()
    async def home(self, axes: str = "XYZABC") -> AxisPosition:
        """Home specified axes."""
        axes = axes.upper()
        seq = []
        if set(axes) & set("ZABC"):
            seq.append("".join(ax for ax in "ZABC" if ax in axes))
        if "X" in axes:
            seq.append("X")
        if "Y" in axes:
            seq.append("Y")
        for grp in seq:
            await self._conn.send_command(f"{GCODE_HOME} {grp}")
            for ax in grp:
                self._position[ax] = 0.0
        return self._to_dataclass(self._position)

    @sila.UnobservableCommand()
    async def move(self, x=None, y=None, z=None, a=None, b=None, c=None, speed=None) -> AxisPosition:
        """Move to absolute position."""
        targets = {k: v for k, v in {"X": x, "Y": y, "Z": z, "A": a, "B": b, "C": c}.items() if v is not None}
        if not targets:
            raise ValueError("At least one axis required")
        parts = [GCODE_MOVE] + [f"{ax}{v:.3f}" for ax, v in sorted(targets.items())]
        if speed:
            parts.append(f"F{speed:.1f}")
        await self._conn.send_command(" ".join(parts))
        self._position.update(targets)
        return self._to_dataclass(self._position)

    @sila.UnobservableCommand()
    async def get_position(self) -> AxisPosition:
        """Get current position."""
        resp = await self._conn.send_command(GCODE_GET_POSITION)
        self._position.update(self._parse_position(resp))
        return self._to_dataclass(self._position)

    @sila.UnobservableCommand()
    def set_lights(self, button: bool | None = None, rails: bool | None = None) -> dict:
        """Control lights."""
        if button is not None:
            self._gpio.set_button_light(blue=button)
        if rails is not None:
            self._gpio.set_rail_lights(rails)
        return {"button": self._gpio.get_button_light()[2], "rails": self._gpio.get_rail_lights()}

    @sila.UnobservableCommand()
    async def emergency_stop(self) -> str:
        """Emergency stop."""
        self._gpio.set_halt_pin(True)
        await asyncio.sleep(0.1)
        self._gpio.set_halt_pin(False)
        self._gpio.set_reset_pin(False)
        await asyncio.sleep(0.25)
        self._gpio.set_reset_pin(True)
        return "Emergency stop executed"


# === SiLA2 Feature: GPIO Control ===
class GPIOControlFeature(sila.Feature):
    def __init__(self, gpio):
        super().__init__(originator="ca.accelerationconsortium", category="robots")
        self._gpio = gpio

    @sila.UnobservableCommand()
    def set_button_light(self, red=False, green=False, blue=False) -> ButtonLightState:
        """Set button LED color."""
        self._gpio.set_button_light(red=red, green=green, blue=blue)
        r, g, b = self._gpio.get_button_light()
        return ButtonLightState(red=r, green=g, blue=b)

    @sila.UnobservableCommand()
    def get_button_light(self) -> ButtonLightState:
        r, g, b = self._gpio.get_button_light()
        return ButtonLightState(red=r, green=g, blue=b)

    @sila.UnobservableCommand()
    def set_rail_lights(self, on: bool) -> bool:
        self._gpio.set_rail_lights(on)
        return self._gpio.get_rail_lights()

    @sila.UnobservableCommand()
    def get_rail_lights(self) -> bool:
        return self._gpio.get_rail_lights()

    @sila.UnobservableCommand()
    def read_button(self) -> bool:
        return self._gpio.read_button()

    @sila.UnobservableCommand()
    def read_door_switch(self) -> bool:
        return self._gpio.read_door_switch()


# === Connector Configuration ===
@dataclass
class OT2Config(ConnectorBaseConfig):
    use_simulator: bool = True
    serial_port: str | None = None
    baud_rate: int = 115200
    sila_server: SiLAServerConfig = field(
        default_factory=lambda: SiLAServerConfig(
            name="Opentrons OT-2",
            type="LiquidHandler",
            description="SiLA2 connector for OT-2 motion/GPIO",
            version=__version__,
            vendor_url="https://opentrons.com/",
        )
    )


async def create_app(config: OT2Config):
    """Create connector application."""
    if config.use_simulator:
        conn = SimulatingSmoothieConnection()
        gpio = SimulatingGPIOController()
    else:
        port = config.serial_port or find_smoothie_port()
        if not port:
            raise RuntimeError("No Smoothie found")
        conn = SmoothieConnection(port, config.baud_rate)
        await conn.connect()
        gpio = GPIOController()
        gpio.setup()

    app = Connector(config)
    app.register(MotionControlFeature(conn, gpio))
    app.register(GPIOControlFeature(gpio))
    yield app

    if not config.use_simulator:
        await conn.disconnect()


# === CLI Entry Point ===
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OT-2 SiLA2 Connector")
    parser.add_argument("--port", help="Serial port (auto-detect if omitted)")
    parser.add_argument("--simulate", action="store_true", help="Use simulator")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--sila-port", type=int, default=50052, help="SiLA port")
    args = parser.parse_args()

    config = OT2Config(
        use_simulator=args.simulate,
        serial_port=args.port,
    )
    config.sila_server.host = args.host
    config.sila_server.port = args.sila_port

    from unitelabs.cdk import run

    run(create_app, config)
