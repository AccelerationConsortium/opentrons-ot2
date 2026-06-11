"""Tests for module error translation: opentrons exceptions -> defined errors.

The controllers wrap driver/module calls so the features see one stable set of
defined errors regardless of which opentrons exception (comm vs module-specific)
was actually raised.
"""

import pytest

from opentrons.drivers.asyncio.communication.errors import NoResponse
from opentrons.drivers.temp_deck.driver import TempDeckError

from unitelabs.opentrons_ot2.io import (
    EngageHeightOutOfRangeError,
    MagneticModuleController,
    ModuleNotRespondingError,
    ModuleOperationError,
    TemperatureModuleController,
)


class _RaisingTempDriver:
    """Fake temp-deck driver whose calls raise a preset exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def set_temperature(self, celsius: float) -> None:
        raise self._exc


@pytest.mark.asyncio
async def test_comm_error_becomes_not_responding() -> None:
    ctrl = TemperatureModuleController(driver=_RaisingTempDriver(NoResponse(port="/dev/x", command="M104")))
    with pytest.raises(ModuleNotRespondingError):
        await ctrl.set_temperature(50.0)


@pytest.mark.asyncio
async def test_module_error_becomes_operation_error() -> None:
    ctrl = TemperatureModuleController(driver=_RaisingTempDriver(TempDeckError("over temperature")))
    with pytest.raises(ModuleOperationError):
        await ctrl.set_temperature(50.0)


class _RaisingMagModule:
    """Fake magnetic module that rejects an out-of-range engage height."""

    async def engage(self, height: float | None = None) -> None:
        raise ValueError("Invalid engage height for magneticModuleV2: 99. Must be 0 - 25.")


@pytest.mark.asyncio
async def test_engage_value_error_becomes_out_of_range() -> None:
    ctrl = MagneticModuleController.from_module(_RaisingMagModule())
    with pytest.raises(EngageHeightOutOfRangeError):
        await ctrl.engage(99.0)


class _OtherValueErrorMagModule:
    """Fake magnetic module raising a ValueError unrelated to engage height."""

    async def engage(self, height: float | None = None) -> None:
        raise ValueError("could not convert string to float: 'NaN'")


@pytest.mark.asyncio
async def test_unrelated_value_error_is_not_mislabeled_as_out_of_range() -> None:
    ctrl = MagneticModuleController.from_module(_OtherValueErrorMagModule())
    with pytest.raises(ValueError) as excinfo:
        await ctrl.engage(10.0)
    assert not isinstance(excinfo.value, EngageHeightOutOfRangeError)
