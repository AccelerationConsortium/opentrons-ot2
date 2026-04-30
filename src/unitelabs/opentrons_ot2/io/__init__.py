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

from .motion import OT2MotionController
from .modules import (
    HeaterShakerController,
    ThermocyclerController,
    TemperatureModuleController,
    MagneticModuleController,
    Temperature,
    RPM,
)

__all__ = [
    "RPM",
    "HeaterShakerController",
    "MagneticModuleController",
    "OT2MotionController",
    "Temperature",
    "TemperatureModuleController",
    "ThermocyclerController",
]
