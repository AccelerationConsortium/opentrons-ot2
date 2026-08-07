"""Unit tests for OT2MotionController.move_through batching.

Uses a real simulated SmoothieDriver (connection=None), no mocks — the
planning helpers are exercised directly so the generated G-code lines can be
inspected, which simulation-mode _send_command (a no-op) cannot verify.
"""

import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.io.motion import _MAX_BATCH_COMMAND_CHARS, OT2MotionController

_HOMED = {"X": 418.0, "Y": 353.0, "Z": 218.0, "A": 218.0, "B": 19.0, "C": 19.0}


@pytest_asyncio.fixture
async def controller() -> OT2MotionController:
    controller = await OT2MotionController.build(simulate=True)
    await controller.home()
    return controller


def _target(**overrides: float) -> dict[str, float]:
    target = dict(_HOMED)
    target.update(overrides)
    return target


def _plan(controller: OT2MotionController, moves: list[tuple[dict[str, float], float | None]]):
    steps, moving_axes = controller._filter_move_through_steps(moves)
    batches, speed_dirty = controller._assemble_move_through_batches(steps)
    return [(cmd.build(), end) for cmd, end in batches], moving_axes, speed_dirty


def test_every_line_stays_within_the_cap(controller: OT2MotionController):
    """Long batches split into multiple lines, none exceeding what driver.move itself sends."""
    moves = [(_target(X=40.0 + i * 0.3, Y=30.0, Z=100.0), 30.0) for i in range(40)]
    lines, _, _ = _plan(controller, moves)
    assert len(lines) > 1
    for line, _ in lines:
        assert len(line) <= _MAX_BATCH_COMMAND_CHARS


def test_currents_only_on_first_line(controller: OT2MotionController):
    """The M907 current command rides the first line only; the lock guarantees nothing changes currents mid-batch."""
    moves = [(_target(X=40.0 + i * 0.3), 30.0) for i in range(40)]
    lines, _, _ = _plan(controller, moves)
    assert len(lines) > 1
    assert "M907" in lines[0][0]
    for line, _ in lines[1:]:
        assert "M907" not in line


def test_speed_word_emitted_only_on_change_and_restored(controller: OT2MotionController):
    """F is modal: one F for the wiggle speed, one to restore the default at the end."""
    moves = [(_target(X=40.0 + i), 30.0) for i in range(3)]
    lines, _, speed_dirty = _plan(controller, moves)
    assert speed_dirty is True
    combined = controller._driver._combined_speed
    joined = " ".join(line for line, _ in lines)
    assert joined.count(f"G0 F{int(30.0 * 60)}") == 1
    assert joined.rstrip().endswith(f"G0 F{int(combined * 60)}")


def test_default_speed_batch_has_no_speed_words(controller: OT2MotionController):
    moves = [(_target(X=40.0 + i), None) for i in range(3)]
    lines, _, speed_dirty = _plan(controller, moves)
    assert speed_dirty is False
    assert "F" not in "".join(line for line, _ in lines).replace("M907", "")


def test_unchanged_axes_are_omitted_from_gcode(controller: OT2MotionController):
    """Only the axes that move appear as G0 words — the planner line stays short for wiggles."""
    moves = [(_target(X=40.0), None), (_target(X=41.0), None)]
    lines, moving_axes, _ = _plan(controller, moves)
    assert moving_axes == {"X"}
    (line, end) = lines[0]
    assert "G0 X40.0" in line
    assert "G0 X41.0" in line
    for axis in "YZABC":
        assert f"{axis}{_HOMED[axis]}" not in line.split("G4")[-1]
    # The cached end position still carries all axes.
    assert end == _target(X=41.0)


@pytest.mark.asyncio
async def test_noop_waypoints_send_nothing(controller: OT2MotionController):
    """Waypoints equal to the running position plan no motion at all."""
    steps, moving_axes = controller._filter_move_through_steps([(dict(_HOMED), None), (dict(_HOMED), 30.0)])
    assert steps == []
    assert moving_axes == set()
    before = dict(controller.position)
    await controller.move_through([(dict(_HOMED), None)])
    assert controller.position == before


@pytest.mark.asyncio
async def test_move_through_updates_position_cache(controller: OT2MotionController):
    await controller.move_through([(_target(X=50.0), None), (_target(X=50.0, Y=30.0, Z=100.0), 25.0)])
    assert controller.position == _target(X=50.0, Y=30.0, Z=100.0)
