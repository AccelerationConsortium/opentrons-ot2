"""Tests for play_tone / _play_pcm_blocking in OT2MotionController.

libasound.so.2 is not available in CI, so these tests patch the module-level
_libasound handle and verify the ctypes call sequence without real hardware.
"""

import ctypes
from unittest.mock import MagicMock, patch

import pytest

import unitelabs.opentrons_ot2.io.motion as motion_module
from unitelabs.opentrons_ot2.io.motion import _play_pcm_blocking


# ── _play_pcm_blocking ────────────────────────────────────────────────────────


def test_play_pcm_blocking_raises_when_no_libasound() -> None:
    with (
        patch.object(motion_module, "_libasound", None),
        pytest.raises(RuntimeError, match="libasound.so.2 not available"),
    ):
        _play_pcm_blocking((ctypes.c_int16 * 1)(0), 1)


def test_play_pcm_blocking_raises_on_open_failure() -> None:
    lib = MagicMock()
    lib.snd_pcm_open.return_value = -1
    with (
        patch.object(motion_module, "_libasound", lib),
        pytest.raises(RuntimeError, match="snd_pcm_open failed"),
    ):
        _play_pcm_blocking((ctypes.c_int16 * 1)(0), 1)


def test_play_pcm_blocking_raises_on_set_params_failure() -> None:
    lib = MagicMock()
    lib.snd_pcm_open.return_value = 0
    lib.snd_pcm_set_params.return_value = -1
    with (
        patch.object(motion_module, "_libasound", lib),
        pytest.raises(RuntimeError, match="snd_pcm_set_params failed"),
    ):
        _play_pcm_blocking((ctypes.c_int16 * 1)(0), 1)
    lib.snd_pcm_close.assert_called_once()


def test_play_pcm_blocking_happy_path() -> None:
    lib = MagicMock()
    lib.snd_pcm_open.return_value = 0
    lib.snd_pcm_set_params.return_value = 0
    n = 10
    pcm = (ctypes.c_int16 * n)(*([0] * n))
    with patch.object(motion_module, "_libasound", lib):
        _play_pcm_blocking(pcm, n)
    lib.snd_pcm_writei.assert_called_once()
    lib.snd_pcm_drain.assert_called_once()
    lib.snd_pcm_close.assert_called_once()


def test_play_pcm_blocking_closes_on_set_params_failure() -> None:
    """snd_pcm_close must be called even when set_params fails."""
    lib = MagicMock()
    lib.snd_pcm_open.return_value = 0
    lib.snd_pcm_set_params.return_value = -1
    with patch.object(motion_module, "_libasound", lib), pytest.raises(RuntimeError):
        _play_pcm_blocking((ctypes.c_int16 * 1)(0), 1)
    lib.snd_pcm_close.assert_called_once()


# ── play_tone (via OT2MotionController) ──────────────────────────────────────


async def test_play_tone_dispatches_to_executor() -> None:
    """play_tone must call _play_pcm_blocking via run_in_executor."""
    controller = await motion_module.OT2MotionController.build(simulate=True)

    calls: list[tuple] = []

    def fake_blocking(pcm: ctypes.Array, n_samples: int) -> None:
        calls.append((type(pcm).__name__, n_samples))

    with patch.object(motion_module, "_play_pcm_blocking", fake_blocking):
        await controller.play_tone(frequency_hz=440.0, duration_ms=100.0)

    assert len(calls) == 1
    _pcm_type, n_samples = calls[0]
    assert n_samples == pytest.approx(4410, abs=1)  # 44100 * 0.1


async def test_play_tone_zero_duration() -> None:
    controller = await motion_module.OT2MotionController.build(simulate=True)
    called = []
    with patch.object(motion_module, "_play_pcm_blocking", lambda pcm, n: called.append(n)):
        await controller.play_tone(frequency_hz=440.0, duration_ms=0.0)
    assert called == [0]
