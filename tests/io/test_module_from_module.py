"""Tests for the from_module() adapters on the module controllers.

In with_robot_server mode the controllers wrap the high-level module objects
that the shared HardwareControlAPI already owns, instead of opening the serial
port a second time. These tests use fake module objects (duck-typed to the
opentrons module-object API) to assert each controller method maps to the right
module call/property and that disconnect() is a no-op (the API owns the tty).
"""

from typing import ClassVar

import pytest

from unitelabs.opentrons_ot2.io import (
    DeviceInfo,
    HeaterShakerController,
    MagneticModuleController,
    TemperatureModuleController,
    ThermocyclerController,
)


class _Recorder:
    def __init__(self):
        self.calls = []

    def record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))


# ── Temperature module ────────────────────────────────────────────────────────


class FakeTempDeck(_Recorder):
    temperature = 25.0
    target = 37.0
    device_info: ClassVar[dict] = {"serial": "T1", "model": "temp_v2", "version": "1.0"}

    async def start_set_temperature(self, celsius):
        self.record("start_set_temperature", celsius)

    async def deactivate(self):
        self.record("deactivate")


@pytest.mark.asyncio
async def test_temperature_from_module_maps_calls():
    mod = FakeTempDeck()
    ctrl = TemperatureModuleController.from_module(mod)

    await ctrl.set_temperature(50.0)
    assert ("start_set_temperature", (50.0,), {}) in mod.calls

    t = await ctrl.get_temperature()
    assert (t.current, t.target) == (25.0, 37.0)

    await ctrl.deactivate()
    assert ("deactivate", (), {}) in mod.calls

    assert await ctrl.get_device_info() == DeviceInfo.from_dict(mod.device_info)
    assert await ctrl.is_connected() is True
    await ctrl.disconnect()  # no-op, must not raise


# ── Heater-Shaker ─────────────────────────────────────────────────────────────


class FakeHeaterShaker(_Recorder):
    temperature = 30.0
    target_temperature = 60.0
    speed = 500
    target_speed = 1000
    labware_latch_status = "idle_closed"
    device_info: ClassVar[dict] = {"serial": "HS1", "model": "hs_v1", "version": "2.0"}

    async def start_set_temperature(self, celsius):
        self.record("start_set_temperature", celsius)

    async def deactivate_heater(self):
        self.record("deactivate_heater")

    async def set_speed(self, rpm):
        self.record("set_speed", rpm)

    async def deactivate_shaker(self):
        self.record("deactivate_shaker")

    async def open_labware_latch(self):
        self.record("open_labware_latch")

    async def close_labware_latch(self):
        self.record("close_labware_latch")


@pytest.mark.asyncio
async def test_heater_shaker_from_module_maps_calls():
    mod = FakeHeaterShaker()
    ctrl = HeaterShakerController.from_module(mod)

    await ctrl.set_temperature(55.0)
    assert ("start_set_temperature", (55.0,), {}) in mod.calls

    t = await ctrl.get_temperature()
    assert (t.current, t.target) == (30.0, 60.0)

    await ctrl.set_rpm(800)
    assert ("set_speed", (800,), {}) in mod.calls

    r = await ctrl.get_rpm()
    assert (r.current, r.target) == (500, 1000)

    await ctrl.stop_shaking()
    assert ("deactivate_shaker", (), {}) in mod.calls

    await ctrl.open_latch()
    await ctrl.close_latch()
    assert ("open_labware_latch", (), {}) in mod.calls
    assert ("close_labware_latch", (), {}) in mod.calls

    assert await ctrl.get_latch_status() == "idle_closed"
    assert await ctrl.get_device_info() == DeviceInfo.from_dict(mod.device_info)
    await ctrl.disconnect()  # no-op


# ── Thermocycler ──────────────────────────────────────────────────────────────


class _LidStatus:
    name = "OPEN"


class FakeThermocycler(_Recorder):
    temperature = 70.0
    target = 95.0
    lid_temp = 100.0
    lid_target = 105.0
    lid_status = _LidStatus()
    device_info: ClassVar[dict] = {"serial": "TC1", "model": "tc_v2", "version": "3.0"}

    async def open(self):
        self.record("open")

    async def close(self):
        self.record("close")

    async def set_target_lid_temperature(self, celsius):
        self.record("set_target_lid_temperature", celsius)

    async def set_target_block_temperature(self, celsius, hold_time_seconds=None, volume=None):
        self.record("set_target_block_temperature", celsius, hold_time_seconds, volume)

    async def deactivate_lid(self):
        self.record("deactivate_lid")

    async def deactivate_block(self):
        self.record("deactivate_block")

    async def deactivate(self):
        self.record("deactivate")


@pytest.mark.asyncio
async def test_thermocycler_from_module_maps_calls():
    mod = FakeThermocycler()
    ctrl = ThermocyclerController.from_module(mod)

    await ctrl.open_lid()
    await ctrl.close_lid()
    assert ("open", (), {}) in mod.calls
    assert ("close", (), {}) in mod.calls

    assert await ctrl.get_lid_status() == "open"

    await ctrl.set_lid_temperature(105.0)
    assert ("set_target_lid_temperature", (105.0,), {}) in mod.calls

    await ctrl.set_plate_temperature(95.0, hold_time=30.0, volume=25.0)
    assert ("set_target_block_temperature", (95.0, 30.0, 25.0), {}) in mod.calls

    lid = await ctrl.get_lid_temperature()
    assert (lid.current, lid.target) == (100.0, 105.0)

    plate = await ctrl.get_plate_temperature()
    assert (plate.current, plate.target) == (70.0, 95.0)

    await ctrl.deactivate_lid()
    await ctrl.deactivate_block()
    await ctrl.deactivate_all()
    assert ("deactivate_lid", (), {}) in mod.calls
    assert ("deactivate_block", (), {}) in mod.calls
    assert ("deactivate", (), {}) in mod.calls

    assert await ctrl.get_device_info() == DeviceInfo.from_dict(mod.device_info)
    await ctrl.disconnect()  # no-op


# ── Magnetic module ───────────────────────────────────────────────────────────


class FakeMagDeck(_Recorder):
    current_height = 12.5
    device_info: ClassVar[dict] = {"serial": "M1", "model": "mag_v2", "version": "1.5"}

    async def engage(self, height=None):
        self.record("engage", height)

    async def deactivate(self):
        self.record("deactivate")


@pytest.mark.asyncio
async def test_magnetic_from_module_maps_calls():
    mod = FakeMagDeck()
    ctrl = MagneticModuleController.from_module(mod)

    await ctrl.engage(8.0)
    assert ("engage", (8.0,), {}) in mod.calls or ("engage", (), {"height": 8.0}) in mod.calls

    await ctrl.disengage()
    assert ("deactivate", (), {}) in mod.calls

    assert await ctrl.get_mag_position() == 12.5
    assert await ctrl.get_device_info() == DeviceInfo.from_dict(mod.device_info)
    await ctrl.disconnect()  # no-op
