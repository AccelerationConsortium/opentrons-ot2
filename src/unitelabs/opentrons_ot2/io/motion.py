"""
IO wrapper using the Opentrons driver layer.

This module provides a thin wrapper around the existing Opentrons driver
classes, avoiding reimplementation of low-level serial communication.

Uses:
- opentrons.drivers.smoothie_drivers.driver_3_0.SmoothieDriver
- opentrons.drivers.rpi_drivers.gpio.GPIOCharDev
- opentrons.config.robot_configs for default configuration
"""

import asyncio
import ctypes
import logging
import math
from pathlib import Path

# Import Opentrons driver components
from opentrons.config.robot_configs import load_ot2
from opentrons.hardware_control import HardwareControlAPI
from opentrons.drivers.smoothie_drivers.driver_3_0 import SmoothieDriver
from opentrons.drivers.smoothie_drivers.constants import AXES
from opentrons.drivers.smoothie_drivers.errors import SmoothieAlarm, SmoothieError
from opentrons.drivers.rpi_drivers.gpio import GPIOCharDev
from opentrons.drivers.rpi_drivers.gpio_simulator import SimulatingGPIOCharDev

from .hardware_proxy import _TimedLock

# ALSA constants and library handle for play_tone.
# libasound.so.2 is only present on the OT-2 (Linux/ARM); None on other platforms.
try:
    _libasound = ctypes.CDLL("libasound.so.2")
except OSError:
    _libasound = None
_SND_PCM_FORMAT_S16_LE = 2
_SND_PCM_ACCESS_RW_INTERLEAVED = 3
_SND_PCM_STREAM_PLAYBACK = 0
_ALSA_SAMPLE_RATE = 44100

log = logging.getLogger(__name__)


def _play_pcm_blocking(pcm: ctypes.Array, n_samples: int) -> None:
    """Write a signed 16-bit mono PCM buffer to ALSA hw:0,0 (blocking)."""
    if _libasound is None:
        msg = "libasound.so.2 not available on this platform"
        raise RuntimeError(msg)
    handle = ctypes.c_void_p()
    if _libasound.snd_pcm_open(ctypes.byref(handle), b"hw:0,0", _SND_PCM_STREAM_PLAYBACK, 0) < 0:
        msg = "snd_pcm_open failed"
        raise RuntimeError(msg)
    try:
        if (
            _libasound.snd_pcm_set_params(
                handle,
                ctypes.c_int(_SND_PCM_FORMAT_S16_LE),
                ctypes.c_int(_SND_PCM_ACCESS_RW_INTERLEAVED),
                ctypes.c_uint(1),
                ctypes.c_uint(_ALSA_SAMPLE_RATE),
                ctypes.c_int(1),
                ctypes.c_uint(500_000),
            )
            < 0
        ):
            msg = "snd_pcm_set_params failed"
            raise RuntimeError(msg)
        _libasound.snd_pcm_writei(handle, pcm, ctypes.c_ulong(n_samples))
        _libasound.snd_pcm_drain(handle)
    finally:
        _libasound.snd_pcm_close(handle)


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

# Plunger axes (left=B, right=C) home at their *active* current. The OT-2 robot
# config default for plungers is 0.05 A (idle/holding level) — too little torque
# to drive the plunger to its endstop, so a bare ``G28.2 B``/``C`` returns
# "Homing fail". Opentrons' own home raises the plunger to the attached pipette's
# run current first (see HardwareControlAPI._do_plunger_home), then homes it
# separately from the gantry. We mirror that, falling back to this default when
# no pipette run current is available (e.g. standalone mode without a HardwareAPI).
_PLUNGER_AXES = "BC"
_DEFAULT_PLUNGER_HOME_CURRENT_AMPS = 0.5


class OT2MotionController:
    """
    High-level motion controller using Opentrons SmoothieDriver.

    This is a thin wrapper around the existing Opentrons driver that:
    1. Uses the battle-tested SmoothieDriver implementation
    2. Provides a simplified interface for SiLA2 integration
    3. Handles GPIO for lights and buttons
    """

    _hw_api: "HardwareControlAPI | None" = None

    def __init__(
        self,
        smoothie_driver: SmoothieDriver,
        gpio: GPIOCharDev | SimulatingGPIOCharDev,
        lock: asyncio.Lock | None = None,
        lock_timeout_s: float | None = None,
    ):
        """
        Initialize with existing driver instances.

        Use the build() classmethod for normal construction, or from_api() when
        sharing a driver with HardwareControlAPI in the in-process server mode.
        """
        self._driver = smoothie_driver
        self._gpio = gpio
        # Snapshot the hardware-revision-correct defaults chosen by the driver at
        # init time, before any caller can mutate them via set_active_current etc.
        # SimulatingDriver (used by API.build_hardware_simulator) does not expose
        # current settings, so we fall back to an empty dict in that case.
        self._default_active_currents: dict[str, float] = (
            dict(smoothie_driver._active_current_settings.now)
            if hasattr(smoothie_driver, "_active_current_settings")
            else {}
        )
        self._default_dwelling_currents: dict[str, float] = (
            dict(smoothie_driver._dwelling_current_settings.now)
            if hasattr(smoothie_driver, "_dwelling_current_settings")
            else {}
        )
        # SmoothieDriver has a single serial connection — concurrent callers must not interleave.
        # An external lock may be supplied to share serialisation with HardwareProxy.
        raw_lock = lock if lock is not None else asyncio.Lock()
        self._lock: _TimedLock = _TimedLock(raw_lock, lock_timeout_s)

    @classmethod
    async def build(
        cls,
        port: str = DEFAULT_SMOOTHIE_PORT,
        simulate: bool = False,
        lock_timeout_s: float | None = None,
    ) -> "OT2MotionController":
        """
        Build an OT2MotionController.

        Args:
            port: Serial port for Smoothie (default: /dev/ttyAMA0).
            simulate: If True, use simulators instead of real hardware.
            lock_timeout_s: Seconds to wait for the hardware lock before raising TimeoutError.

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

        return cls(smoothie_driver=driver, gpio=gpio, lock_timeout_s=lock_timeout_s)

    @classmethod
    def from_api(
        cls,
        hw_api: "HardwareControlAPI",
        lock: asyncio.Lock,
        lock_timeout_s: float | None = None,
    ) -> "OT2MotionController":
        """
        Build an OT2MotionController that shares a driver and lock with a HardwareControlAPI.

        Used in the in-process server mode where both the SiLA2 gRPC server and the
        opentrons HTTP server must share a single SmoothieDriver. The caller creates
        one asyncio.Lock and passes it to both this method and HardwareProxy so that
        all callers from both servers are serialised through the same lock.

        On real hardware, ``hw_api``'s backend is ``Controller``, whose own
        move/home/current methods just forward to its ``_smoothie_driver`` — so
        that object genuinely is the one true mover, and sharing it here is safe.
        On a simulated ``hw_api`` (``Simulator`` backend), movement is implemented
        by ``Simulator`` itself; its ``_smoothie_driver`` is a bare ``SimulatingDriver``
        stub it only ever pokes for a few incidental things (home flags, dwelling
        current, steps-per-mm) and never asks to move. That stub doesn't implement
        the rest of the interface this class drives directly (``move``, ``position``,
        ``probe_axis``, ``set_active_current``, ...), so it can't be shared the same
        way — we build a real (simulated) ``SmoothieDriver`` of our own instead, the
        same one ``build(simulate=True)`` already uses.

        Args:
            hw_api: An already-built HardwareControlAPI (OT-2, not OT-3).
            lock: Shared asyncio.Lock — must be the same instance passed to HardwareProxy.
            lock_timeout_s: Seconds to wait for the lock before raising TimeoutError.

        Returns:
            OT2MotionController wrapping the same SmoothieDriver as hw_api on real
            hardware, or its own standalone simulated SmoothieDriver when hw_api is
            a simulator.
        """
        backend = hw_api._backend  # type: ignore[attr-defined]
        if isinstance(backend._smoothie_driver, SmoothieDriver):
            smoothie_driver = backend._smoothie_driver
        else:
            log.info(
                "HardwareControlAPI backend's _smoothie_driver is a %s, not a real "
                "SmoothieDriver (simulator backend) — building a standalone simulated "
                "SmoothieDriver instead of sharing it",
                type(backend._smoothie_driver).__name__,
            )
            smoothie_driver = SmoothieDriver(
                config=load_ot2(),
                gpio_chardev=backend.gpio_chardev,
                connection=None,  # None = simulation mode
            )
        controller = cls(
            smoothie_driver=smoothie_driver,
            gpio=backend.gpio_chardev,
            lock=lock,
            lock_timeout_s=lock_timeout_s,
        )
        controller._hw_api = hw_api
        return controller

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

    @property
    def axis_bounds(self) -> dict[str, float]:
        """Software travel limit (max mm) per axis. Min is always 0.0."""
        return self._driver.axis_bounds

    @property
    def board_revision(self) -> str:
        """Board hardware revision read from GPIO pins (e.g. 'A', 'B', 'C', 'UNKNOWN')."""
        return self._gpio.board_rev.name

    async def get_serial_number(self) -> str:
        """Read OT-2 serial number from /var/serial. Returns '' if unavailable."""
        try:
            return (await asyncio.to_thread(Path("/var/serial").read_text)).strip()
        except OSError:
            return ""

    async def disengage_axes(self, axes: str) -> None:
        """Disengage stepper motors for the given axes (M18 G-code)."""
        async with self._lock:
            await self._driver.disengage_axis(axes)

    # ============ Motion Control ============

    async def home(self, axes: str = AXES) -> dict[str, float]:
        """
        Home specified axes.

        Uses the full Opentrons homing sequence including:
        - Current management
        - Unstick moves for plunger axes
        - Proper X/Y sequencing with backoff

        Plunger axes (B, C) are homed individually at the attached pipette's run
        current (or a safe default), separately from the gantry/mounts — the bare
        driver would otherwise home them at the 0.05 A idle current, which lacks
        the torque to reach the endstop and fails with "Homing fail".

        Args:
            axes: String of axes to home (e.g., "XYZABC" or "ZA").

        Returns:
            Dict of axis positions after homing.
        """
        plunger_axes = [ax for ax in axes if ax in _PLUNGER_AXES]
        other_axes = "".join(ax for ax in axes if ax not in _PLUNGER_AXES)
        async with self._lock:
            position: dict[str, float] = {}
            # Home gantry + mounts together first (their default currents are adequate),
            # then each plunger on its own at an adequate current — matching the
            # sequence in opentrons HardwareControlAPI.home().
            if other_axes:
                position = await self._driver.home(axis=other_axes)
            for ax in plunger_axes:
                position = await self._home_plunger(ax)
            return position

    async def _home_plunger(self, axis: str) -> dict[str, float]:
        """Home a single plunger axis at an adequate current, restoring the prior current after."""
        home_current = self._plunger_home_current(axis)
        previous_current = self._driver.current.get(axis)
        self._driver.set_active_current({axis: home_current})
        try:
            return await self._driver.home(axis=axis)
        finally:
            if previous_current is not None:
                self._driver.set_active_current({axis: previous_current})

    def _plunger_home_current(self, axis: str) -> float:
        """Run current for a plunger home: the attached pipette's run current if known, else a default."""
        if self._hw_api is not None:
            try:
                from opentrons.types import Mount

                mount = Mount.LEFT if axis == "B" else Mount.RIGHT
                instrument = self._hw_api.hardware_instruments.get(mount)
                if instrument is not None:
                    return float(instrument.plunger_motor_current.run)
            except Exception:  # noqa: BLE001 — any lookup failure falls back to the safe default current
                log.warning(
                    "Could not read pipette run current for axis %s; using default %.2f A",
                    axis,
                    _DEFAULT_PLUNGER_HOME_CURRENT_AMPS,
                    exc_info=True,
                )
        return _DEFAULT_PLUNGER_HOME_CURRENT_AMPS

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
        async with self._lock:
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
        async with self._lock:
            current = self.position
            target = {ax: current.get(ax, 0) + delta for ax, delta in deltas.items()}
            await self._driver.move(target=target, speed=speed)

    async def get_position(self) -> dict[str, float]:
        """
        Query current position from hardware.

        Updates the internal cache and returns the position.
        """
        async with self._lock:
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
        async with self._lock:
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
        async with self._lock:
            current = self.position
            target = {axis: current.get(axis, 0) - distance_mm}
            await self._driver.move(target=target, speed=speed_mm_s)

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
        async with self._lock:
            current = self.position
            target = {axis: current.get(axis, 0) + distance_mm}
            await self._driver.move(target=target, speed=speed_mm_s)

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
        async with self._lock:
            result = await self._driver.read_pipette_model(mount)
        return result or ""

    async def read_pipette_id(self, mount: str) -> str:
        """Read the unique ID from the pipette EEPROM. Returns '' if unreadable."""
        async with self._lock:
            result = await self._driver.read_pipette_id(mount)
        return result or ""

    # ============ Calibration ============

    async def update_steps_per_mm(self, updates: dict[str, float]) -> None:
        """Write steps/mm for one or more axes via M92."""
        async with self._lock:
            await self._driver.update_steps_per_mm(updates)

    async def update_pipette_config(self, axis: str, data: dict[str, float]) -> None:
        """
        Write M365 pipette motion parameters for one axis.

        Valid keys: "home" (M365.0), "max_travel" (M365.1),
        "debounce" (M365.2, global), "retract" (M365.3).
        """
        async with self._lock:
            await self._driver.update_pipette_config(axis, data)

    async def stop(self) -> None:
        """Emergency stop - halt all motion."""
        async with self._lock:
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
        async with self._lock:
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

    async def play_tone(self, frequency_hz: float, duration_ms: float) -> None:
        """
        Play a single tone through the OT-2 speaker via libasound (ALSA hw:0,0).

        The Smoothie M300 G-code is accepted by the firmware but no buzzer is
        wired to it on the OT-2. Audio goes through the Raspberry Pi bcm2835
        output (hw:0,0), kept enabled by the opentrons GPIO driver at startup.
        snd_pcm_writei blocks so we run it in a thread executor.
        """
        n_samples = int(_ALSA_SAMPLE_RATE * duration_ms / 1000.0)
        pcm = (ctypes.c_int16 * n_samples)(
            *(int(32767 * math.sin(2 * math.pi * frequency_hz * i / _ALSA_SAMPLE_RATE)) for i in range(n_samples))
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _play_pcm_blocking, pcm, n_samples)

    async def reset_from_error(self) -> None:
        """Clear alarm lock state (M999)."""
        async with self._lock:
            await self._driver._reset_from_error()

    async def smoothie_reset(self) -> None:
        """Full hardware GPIO reset of the Smoothie."""
        async with self._lock:
            await self._driver._smoothie_reset()

    async def is_connected(self) -> bool:
        """Check if connected to Smoothie."""
        return await self._driver.is_connected()
