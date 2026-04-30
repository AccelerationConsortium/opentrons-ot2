#!/usr/bin/env python3
"""Test motion using Opentrons SmoothieDriver directly."""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from opentrons.config.robot_configs import load_ot2
from opentrons.drivers.smoothie_drivers.driver_3_0 import SmoothieDriver
from opentrons.drivers.smoothie_drivers.constants import AXES
from opentrons.drivers.rpi_drivers.gpio_simulator import SimulatingGPIOCharDev

DEFAULT_SMOOTHIE_PORT = "/dev/ttyAMA0"


async def main():
    print("=== Motion Test using Opentrons SmoothieDriver ===")
    print()

    config = load_ot2()
    print(f"Config loaded: serial_speed={config.serial_speed}")

    # Use simulated GPIO (skip real GPIO)
    gpio = SimulatingGPIOCharDev("simulated")

    print(f"Connecting to Smoothie at {DEFAULT_SMOOTHIE_PORT}...")
    driver = await SmoothieDriver.build(
        port=DEFAULT_SMOOTHIE_PORT,
        config=config,
        gpio_chardev=gpio,
    )
    print(f"Connected! Simulating: {driver.simulating}")
    print()

    # Get firmware version
    fw = await driver.get_fw_version()
    print(f"Firmware: {fw}")
    print()

    # Home all axes
    print("1. Homing all axes...")
    pos = await driver.home(axis=AXES)
    print(f"   Home position: X={pos['X']:.1f} Y={pos['Y']:.1f} Z={pos['Z']:.1f}")
    print()

    # Simple XY move
    print("2. Moving X to 200, Y to 200...")
    await driver.move(target={"X": 200.0, "Y": 200.0})
    await driver.update_position()
    pos = driver.position
    print(f"   Position: X={pos['X']:.1f} Y={pos['Y']:.1f}")
    print()

    # Z move (down from home)
    safe_z = pos["Z"] - 30.0
    print(f"3. Moving Z down to {safe_z:.1f}...")
    await driver.move(target={"Z": safe_z})
    await driver.update_position()
    pos = driver.position
    print(f"   Position: Z={pos['Z']:.1f}")
    print()

    # Combined XY move
    print("4. Moving X=300, Y=150...")
    await driver.move(target={"X": 300.0, "Y": 150.0})
    await driver.update_position()
    pos = driver.position
    print(f"   Position: X={pos['X']:.1f} Y={pos['Y']:.1f}")
    print()

    # Tip shake - rapid oscillation to shake off liquid
    print("5. Tip shake (rapid Z oscillations)...")
    base_z = pos["Z"]
    shake_amplitude = 5.0  # mm
    shake_speed = 100.0  # mm/sec (fast)
    num_shakes = 5

    for i in range(num_shakes):
        await driver.move(target={"Z": base_z - shake_amplitude}, speed=shake_speed)
        await driver.move(target={"Z": base_z}, speed=shake_speed)
        print(f"   Shake {i + 1}/{num_shakes}")
    print("   Tip shake complete")
    print()

    # Home to finish
    print("6. Homing to finish...")
    pos = await driver.home(axis=AXES)
    print(f"   Final: X={pos['X']:.1f} Y={pos['Y']:.1f} Z={pos['Z']:.1f}")
    print()

    # Disconnect
    await driver.disconnect()
    print("=== Motion Test Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
