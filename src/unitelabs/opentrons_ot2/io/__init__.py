"""
IO module using Opentrons driver layer.

This module provides thin wrappers around the existing Opentrons drivers,
avoiding reimplementation of low-level protocols.

Controllers:
- OT2MotionController: Gantry and pipette motion via SmoothieDriver
- HeaterShakerController: Heater-Shaker module
- ThermocyclerController: Thermocycler module
- TemperatureModuleController: Temperature module
- MagneticModuleController: Magnetic module

Example usage:
    from unitelabs.opentrons_ot2.io import OT2MotionController

    async def main():
        controller = await OT2MotionController.build()
        await controller.home()
        await controller.move({"X": 100, "Y": 100})
        await controller.disconnect()
"""

from ._types import RPM, Temperature
from .heater_shaker import HeaterShakerController
from .magnetic_module import MagneticModuleController
from .motion import OT2MotionController
from .temperature_module import TemperatureModuleController
from .thermocycler import ThermocyclerController

__all__ = [
    "RPM",
    "HeaterShakerController",
    "MagneticModuleController",
    "OT2MotionController",
    "Temperature",
    "TemperatureModuleController",
    "ThermocyclerController",
]
