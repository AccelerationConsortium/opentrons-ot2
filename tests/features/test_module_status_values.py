"""Value-level tests for module feature status reporting.

Covers the engaged/position consistency of the magnetic feature and the
UNKNOWN fallback of the status enums (an unrecognized value from a newer
opentrons version must not surface as an undefined SiLA error).
"""

import pytest

from unitelabs.opentrons_ot2.features.heater_shaker import LatchStatus
from unitelabs.opentrons_ot2.features.magnetic import MagneticModuleFeature
from unitelabs.opentrons_ot2.features.thermocycler import LidStatus


class _FakeMagController:
    """Fake controller whose magnet position is wherever it was engaged to."""

    def __init__(self) -> None:
        self._position = 0.0

    async def engage(self, height: float) -> None:
        self._position = height

    async def get_mag_position(self) -> float:
        return self._position


@pytest.mark.asyncio
async def test_engage_at_zero_reports_disengaged() -> None:
    feature = MagneticModuleFeature(_FakeMagController())
    status = await feature.engage(0.0)
    assert status.engaged is False
    assert status.position == 0.0
    # engage() and get_status() must agree on the same physical state
    assert (await feature.get_status()).engaged is False


@pytest.mark.asyncio
async def test_engage_above_zero_reports_engaged() -> None:
    feature = MagneticModuleFeature(_FakeMagController())
    status = await feature.engage(10.0)
    assert status.engaged is True
    assert (await feature.get_status()).engaged is True


def test_latch_status_falls_back_to_unknown() -> None:
    assert LatchStatus("not-a-real-status") is LatchStatus.UNKNOWN


def test_lid_status_falls_back_to_unknown() -> None:
    assert LidStatus("not-a-real-status") is LidStatus.UNKNOWN
