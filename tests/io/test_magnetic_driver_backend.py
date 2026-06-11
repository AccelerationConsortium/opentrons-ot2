"""Driver-backend tests for MagneticModuleController.

MagDeckDriver has no engage()/disengage(); opentrons' own MagDeck drives it via
move(height) and home() + move(0) (hardware_control/modules/magdeck.py). The
controller's driver backend must map to those real driver methods.
"""

import pytest

from unitelabs.opentrons_ot2.io import MagneticModuleController


class _RecordingMagDriver:
    """Fake MagDeckDriver exposing only the methods the real driver has."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def move(self, position: float) -> None:
        self.calls.append(("move", position))

    async def home(self) -> None:
        self.calls.append(("home",))

    async def get_mag_position(self) -> float:
        self.calls.append(("get_mag_position",))
        return 0.0


@pytest.mark.asyncio
async def test_engage_uses_driver_move() -> None:
    driver = _RecordingMagDriver()
    ctrl = MagneticModuleController(driver=driver)
    await ctrl.engage(10.0)
    assert driver.calls == [("move", 10.0)]


@pytest.mark.asyncio
async def test_disengage_homes_then_moves_to_zero() -> None:
    driver = _RecordingMagDriver()
    ctrl = MagneticModuleController(driver=driver)
    await ctrl.disengage()
    assert driver.calls == [("home",), ("move", 0)]
