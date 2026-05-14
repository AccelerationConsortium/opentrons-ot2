"""Tests for /dev/ot_module* detection logic."""

from pathlib import Path
from unittest.mock import patch

import pytest

from unitelabs.opentrons_ot2.io.modules import scan_module_ports


def _glob(paths: list[str]):
    """Return a Path.glob mock that yields Path objects for the given strings."""
    return lambda _self, _pattern: [Path(p) for p in paths]


# ── Happy path ──────────────────────────────────────────────────────────────


def test_no_modules_returns_empty():
    with patch("pathlib.Path.glob", _glob([])):
        assert scan_module_ports() == {}


@pytest.mark.parametrize(
    ("symlink", "expected_type"),
    [
        ("/dev/ot_module_magdeck0", "magnetic"),
        ("/dev/ot_module_tempdeck0", "temperature"),
        ("/dev/ot_module_thermocycler0", "thermocycler"),
        ("/dev/ot_module_heatershaker0", "heater_shaker"),
        # index > 0 still matches
        ("/dev/ot_module_magdeck1", "magnetic"),
        ("/dev/ot_module_tempdeck2", "temperature"),
        # case-insensitive
        ("/dev/ot_module_Thermocycler0", "thermocycler"),
        ("/dev/ot_module_HeaterShaker0", "heater_shaker"),
    ],
)
def test_single_module_detected(symlink: str, expected_type: str):
    with patch("pathlib.Path.glob", _glob([symlink])):
        result = scan_module_ports()
    assert result == {expected_type: symlink}


def test_multiple_modules_all_detected():
    paths = [
        "/dev/ot_module_magdeck0",
        "/dev/ot_module_tempdeck0",
        "/dev/ot_module_thermocycler0",
        "/dev/ot_module_heatershaker0",
    ]
    with patch("pathlib.Path.glob", _glob(paths)):
        result = scan_module_ports()

    assert result == {
        "magnetic": "/dev/ot_module_magdeck0",
        "temperature": "/dev/ot_module_tempdeck0",
        "thermocycler": "/dev/ot_module_thermocycler0",
        "heater_shaker": "/dev/ot_module_heatershaker0",
    }


# ── Noise suppression ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "symlink",
    [
        # OT-2 udev tempfiles — negative lookbehind must suppress these
        "/dev/.#ot_module_tempdeck0",
        "/dev/.#ot_module_thermocycler0",
        # Flex udev tempfiles — negative lookahead must suppress these
        "/dev/ot_module_tempdeck0.tmp-c1:0",
        "/dev/ot_module_heatershaker0.tmp-c2:1",
        # Completely unrecognised device
        "/dev/ot_module_unknown0",
        # Non-module device in /dev
        "/dev/ttyUSB0",
    ],
)
def test_spurious_paths_ignored(symlink: str):
    with patch("pathlib.Path.glob", _glob([symlink])):
        assert scan_module_ports() == {}


def test_mixed_valid_and_spurious():
    paths = [
        "/dev/.#ot_module_tempdeck0",  # udev tempfile — ignored
        "/dev/ot_module_thermocycler0.tmp-c1:0",  # Flex tempfile — ignored
        "/dev/ot_module_magdeck0",  # valid
    ]
    with patch("pathlib.Path.glob", _glob(paths)):
        result = scan_module_ports()

    assert result == {"magnetic": "/dev/ot_module_magdeck0"}
