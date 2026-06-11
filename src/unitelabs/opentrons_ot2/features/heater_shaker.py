"""SiLA2 feature for Heater-Shaker module control."""

import enum
import logging
import typing
from dataclasses import dataclass

from unitelabs.cdk import sila
from unitelabs.cdk.sila import constraints

from ..io import (
    DeviceInfo,
    HeaterShakerController,
    ModuleNotRespondingError,
    ModuleOperationError,
    Temperature,
    RPM,
)

# Sourced from opentrons: heater-shaker temperature validated 0-95 C
# (opentrons/protocol_api/module_validation_and_errors.py: HEATER_SHAKER_TEMPERATURE_MAX=95),
# shaking speed 0-3000 RPM (opentrons/hardware_control/modules/heater_shaker.py).
_TempCelsius = typing.Annotated[float, constraints.MinimalInclusive(0.0), constraints.MaximalInclusive(95.0)]
_Rpm = typing.Annotated[int, constraints.MinimalInclusive(0), constraints.MaximalInclusive(3000)]


log = logging.getLogger(__name__)


class LatchStatus(enum.Enum):
    """Heater-shaker labware latch position (mirrors opentrons HeaterShakerLabwareLatchStatus)."""

    OPENING = "opening"
    IDLE_OPEN = "idle_open"
    CLOSING = "closing"
    IDLE_CLOSED = "idle_closed"
    IDLE_UNKNOWN = "idle_unknown"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> "LatchStatus":
        # A status value outside this set (e.g. from a newer opentrons version)
        # must not crash the command with an undefined SiLA error.
        log.warning("Unrecognized heater-shaker latch status %r; reporting UNKNOWN", value)
        return cls.UNKNOWN


@dataclass
class HeaterShakerStatus:
    """Current status of heater-shaker module."""

    temperature_current: float
    temperature_target: float | None
    rpm_current: int
    rpm_target: int | None
    latch_status: LatchStatus


class HeaterShakerFeature(sila.Feature):
    """
    SiLA2 feature for Heater-Shaker module.

    Provides commands for:
    - Temperature control (heating)
    - Shaking control (orbital motion)
    - Labware latch control
    """

    def __init__(self, controller: HeaterShakerController):
        """
        Initialize the heater-shaker feature.

        Args:
            controller: The HeaterShakerController instance.
        """
        super().__init__(originator="ca.accelerationconsortium", category="modules")
        self._controller = controller

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def set_temperature(self, temperature_celsius: _TempCelsius) -> Temperature:
        """
        Set the target temperature.

        Args:
            temperature_celsius: Target temperature in Celsius (valid range 0-95 C;
                the module heats only, so the effective minimum is ambient).

        Returns:
            Current and target temperature.
        """
        await self._controller.set_temperature(temperature_celsius)
        return await self._controller.get_temperature()

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def get_temperature(self) -> Temperature:
        """
        Get the current temperature.

        Returns:
            Current and target temperature.
        """
        return await self._controller.get_temperature()

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def deactivate_heater(self) -> Temperature:
        """
        Turn off the heater.

        Returns:
            Current and target temperature after deactivation.
        """
        await self._controller.deactivate_heater()
        return await self._controller.get_temperature()

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def set_rpm(self, rpm: _Rpm) -> RPM:
        """
        Set the shaking speed.

        Args:
            rpm: Target shaking speed in revolutions per minute (valid range 0-3000;
                0 stops shaking).

        Returns:
            Current and target RPM.
        """
        await self._controller.set_rpm(rpm)
        return await self._controller.get_rpm()

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def get_rpm(self) -> RPM:
        """
        Get the current shaking speed.

        Returns:
            Current and target RPM.
        """
        return await self._controller.get_rpm()

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def stop_shaking(self) -> RPM:
        """
        Stop shaking and return to home position.

        Returns:
            Current and target RPM after stopping.
        """
        await self._controller.stop_shaking()
        return await self._controller.get_rpm()

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def open_latch(self) -> LatchStatus:
        """
        Open the labware latch.

        Returns:
            Latch status after opening.
        """
        await self._controller.open_latch()
        status = await self._controller.get_latch_status()
        return LatchStatus(status.value)

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def close_latch(self) -> LatchStatus:
        """
        Close the labware latch.

        Returns:
            Latch status after closing.
        """
        await self._controller.close_latch()
        status = await self._controller.get_latch_status()
        return LatchStatus(status.value)

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def get_latch_status(self) -> LatchStatus:
        """
        Get the current latch status.

        Returns:
            Latch status (idle_open, idle_closed, opening, closing, etc.).
        """
        status = await self._controller.get_latch_status()
        return LatchStatus(status.value)

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def get_status(self) -> HeaterShakerStatus:
        """
        Get complete module status.

        Returns:
            Temperature, RPM, and latch status.
        """
        temp = await self._controller.get_temperature()
        rpm = await self._controller.get_rpm()
        latch = await self._controller.get_latch_status()

        return HeaterShakerStatus(
            temperature_current=temp.current,
            temperature_target=temp.target,
            rpm_current=rpm.current,
            rpm_target=rpm.target,
            latch_status=LatchStatus(latch.value),
        )

    @sila.UnobservableCommand(errors=[ModuleNotRespondingError, ModuleOperationError])
    async def get_device_info(self) -> DeviceInfo:
        """
        Get device information.

        Returns:
            Serial number, model, and firmware version.
        """
        return await self._controller.get_device_info()
