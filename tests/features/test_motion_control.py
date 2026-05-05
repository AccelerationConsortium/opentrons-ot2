from unittest.mock import MagicMock

import pytest

from unitelabs.opentrons_ot2.features.motion_control import MotionControlFeature


@pytest.fixture
def feature() -> MotionControlFeature:
    return MotionControlFeature(controller=MagicMock())


@pytest.mark.parametrize(
    ("red", "green", "blue"),
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, True),
        (False, False, False),
        (True, False, True),
    ],
)
def test_set_button_light_returns_requested_state(
    feature: MotionControlFeature,
    red: bool,
    green: bool,
    blue: bool,
) -> None:
    result = feature.set_button_light(red=red, green=green, blue=blue)
    assert result.red == red
    assert result.green == green
    assert result.blue == blue
