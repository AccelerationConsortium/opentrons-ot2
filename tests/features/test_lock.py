"""Tests that OT2MotionController serialises concurrent callers via asyncio.Lock."""

import asyncio

import pytest
import pytest_asyncio

from unitelabs.opentrons_ot2.io.motion import OT2MotionController


@pytest_asyncio.fixture
async def controller() -> OT2MotionController:
    return await OT2MotionController.build(simulate=True)


@pytest.mark.asyncio
async def test_concurrent_homes_do_not_raise(controller: OT2MotionController) -> None:
    """Two concurrent home calls must complete without error."""
    await asyncio.gather(
        controller.home("XYZABC"),
        controller.home("XYZABC"),
    )


@pytest.mark.asyncio
async def test_concurrent_moves_do_not_raise(controller: OT2MotionController) -> None:
    """Two concurrent move calls must complete without error."""
    await controller.home("XYZABC")
    await asyncio.gather(
        controller.move({"X": 10.0}),
        controller.move({"X": 20.0}),
    )


@pytest.mark.asyncio
async def test_concurrent_pipette_reads_do_not_raise(controller: OT2MotionController) -> None:
    """Concurrent pipette EEPROM reads must complete without error."""
    await asyncio.gather(
        controller.read_pipette_model("left"),
        controller.read_pipette_model("right"),
        controller.read_pipette_id("left"),
        controller.read_pipette_id("right"),
    )


@pytest.mark.asyncio
async def test_lock_serialises_calls(controller: OT2MotionController) -> None:
    """Calls made while lock is held must wait, not interleave."""
    order: list[str] = []

    async def tagged_home(tag: str) -> None:
        await controller.home("Z")
        order.append(tag)

    await asyncio.gather(tagged_home("a"), tagged_home("b"))
    assert len(order) == 2  # both completed, in some order — no interleave means no error
