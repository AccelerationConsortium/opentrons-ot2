"""Simulation-mode tests for motor current commands on MotionControlFeature.

In simulation the driver updates its internal current dicts without sending
any G-code, so we can assert state changes directly via the driver's
_active_current_settings.now and _dwelling_current_settings.now dicts.
"""

import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.features.motion_control import Axis, AxisCurrent, MotionControlFeature
from unitelabs.opentrons_ot2.io.motion import OT2MotionController


@pytest_asyncio.fixture
async def feature() -> MotionControlFeature:
    controller = await OT2MotionController.build(simulate=True)
    return MotionControlFeature(controller)


def _active(feature: MotionControlFeature) -> dict:
    return feature._controller._driver._active_current_settings.now


def _dwelling(feature: MotionControlFeature) -> dict:
    return feature._controller._driver._dwelling_current_settings.now


# ── SetActiveCurrents ─────────────────────────────────────────────────────────


def test_set_active_currents_single_axis(feature: MotionControlFeature):
    feature.set_active_currents([AxisCurrent(axis=Axis.X, current_amps=0.5)])
    assert _active(feature)["X"] == pytest.approx(0.5)


def test_set_active_currents_all_axes(feature: MotionControlFeature):
    currents = [AxisCurrent(axis=ax, current_amps=0.4) for ax in Axis]
    feature.set_active_currents(currents)
    for ax in Axis:
        assert _active(feature)[ax.value] == pytest.approx(0.4)


def test_set_active_currents_partial_update_leaves_others(feature: MotionControlFeature):
    original_y = _active(feature)["Y"]
    feature.set_active_currents([AxisCurrent(axis=Axis.X, current_amps=0.6)])
    assert _active(feature)["Y"] == pytest.approx(original_y)


# ── SetDwellingCurrents ───────────────────────────────────────────────────────


def test_set_dwelling_currents_single_axis(feature: MotionControlFeature):
    feature.set_dwelling_currents([AxisCurrent(axis=Axis.Z, current_amps=0.2)])
    assert _dwelling(feature)["Z"] == pytest.approx(0.2)


def test_set_dwelling_currents_partial_update_leaves_others(feature: MotionControlFeature):
    original_x = _dwelling(feature)["X"]
    feature.set_dwelling_currents([AxisCurrent(axis=Axis.Z, current_amps=0.2)])
    assert _dwelling(feature)["X"] == pytest.approx(original_x)


# ── PushActiveCurrents / PopActiveCurrents ────────────────────────────────────


def test_push_pop_restores_previous_active_current(feature: MotionControlFeature):
    feature.set_active_currents([AxisCurrent(axis=Axis.X, current_amps=1.0)])
    feature.push_active_currents()
    feature.set_active_currents([AxisCurrent(axis=Axis.X, current_amps=0.1)])
    assert _active(feature)["X"] == pytest.approx(0.1)
    feature.pop_active_currents()
    assert _active(feature)["X"] == pytest.approx(1.0)


def test_push_pop_does_not_raise(feature: MotionControlFeature):
    feature.push_active_currents()
    feature.pop_active_currents()


# ── Default current properties ────────────────────────────────────────────────


def test_default_active_currents_covers_all_axes(feature: MotionControlFeature):
    defaults = feature.default_active_currents()
    axes = {c.axis for c in defaults}
    assert axes == set(Axis)


def test_default_dwelling_currents_covers_all_axes(feature: MotionControlFeature):
    defaults = feature.default_dwelling_currents()
    axes = {c.axis for c in defaults}
    assert axes == set(Axis)


def test_default_active_currents_are_positive(feature: MotionControlFeature):
    assert all(c.current_amps > 0 for c in feature.default_active_currents())


def test_default_active_currents_unchanged_after_set(feature: MotionControlFeature):
    before = {c.axis: c.current_amps for c in feature.default_active_currents()}
    feature.set_active_currents([AxisCurrent(axis=Axis.X, current_amps=0.1)])
    after = {c.axis: c.current_amps for c in feature.default_active_currents()}
    assert before == after
