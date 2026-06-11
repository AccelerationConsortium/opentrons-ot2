"""Regression tests for plunger home current handling in OT2MotionController.

The bare SmoothieDriver homes every axis at its active current. For plungers
(B, C) that defaults to 0.05 A, which lacks the torque to reach the endstop and
fails on real hardware with "Homing fail". OT2MotionController.home() must raise
the plunger current before homing each plunger (matching opentrons'
_do_plunger_home), then restore it.

Simulation can't reproduce the torque failure, so these tests verify the
command ordering: the plunger current is set above the 0.05 A idle default
*before* the plunger is homed, and restored afterward.
"""

import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.io.motion import _DEFAULT_PLUNGER_HOME_CURRENT_AMPS, OT2MotionController

_IDLE_PLUNGER_CURRENT = 0.05


@pytest_asyncio.fixture
async def controller() -> OT2MotionController:
    return await OT2MotionController.build(simulate=True)


def _spy_driver(controller: OT2MotionController, monkeypatch: pytest.MonkeyPatch) -> list:
    """Record ('set', settings) and ('home', axis) calls on the driver in order."""
    driver = controller._driver
    calls: list = []
    orig_set = driver.set_active_current
    orig_home = driver.home

    def spy_set(settings: dict) -> None:
        calls.append(("set", dict(settings)))
        return orig_set(settings)

    async def spy_home(axis: str) -> dict:
        calls.append(("home", axis))
        return await orig_home(axis=axis)

    monkeypatch.setattr(driver, "set_active_current", spy_set)
    monkeypatch.setattr(driver, "home", spy_home)
    return calls


@pytest.mark.asyncio
async def test_plunger_current_raised_before_home(controller, monkeypatch):
    calls = _spy_driver(controller, monkeypatch)
    await controller.home("B")

    # The active current for B must be raised above the idle default before B is homed.
    raised_to = None
    for kind, payload in calls:
        if kind == "set" and "B" in payload:
            raised_to = payload["B"]
        if kind == "home" and "B" in payload:
            assert raised_to is not None, f"B homed without setting current first: {calls}"
            assert raised_to > _IDLE_PLUNGER_CURRENT, f"B homed at idle current {raised_to}: {calls}"
            assert raised_to == _DEFAULT_PLUNGER_HOME_CURRENT_AMPS  # no hw_api in sim → default
            break
    else:
        raise AssertionError(f"B was never homed: {calls}")


@pytest.mark.asyncio
async def test_plunger_current_restored_after_home(controller, monkeypatch):
    calls = _spy_driver(controller, monkeypatch)
    await controller.home("B")

    # Last current write for B should restore the pre-home idle value, not leave it raised.
    b_writes = [payload["B"] for kind, payload in calls if kind == "set" and "B" in payload]
    assert b_writes, f"no current writes for B: {calls}"
    assert b_writes[-1] == pytest.approx(_IDLE_PLUNGER_CURRENT), f"B current not restored: {b_writes}"


@pytest.mark.asyncio
async def test_gantry_homed_before_plungers(controller, monkeypatch):
    calls = _spy_driver(controller, monkeypatch)
    await controller.home("XYZABC")

    home_calls = [axis for kind, axis in calls if kind == "home"]
    # Gantry/mounts home as one group first, then each plunger individually.
    assert home_calls[0] == "XYZA", home_calls
    assert set(home_calls[1:]) == {"B", "C"}, home_calls


@pytest.mark.asyncio
async def test_non_plunger_home_unchanged(controller, monkeypatch):
    calls = _spy_driver(controller, monkeypatch)
    await controller.home("XYZA")

    # No plungers requested → single grouped home, no plunger current juggling.
    assert [c for c in calls if c[0] == "home"] == [("home", "XYZA")], calls
