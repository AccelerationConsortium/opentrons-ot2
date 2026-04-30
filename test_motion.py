#!/usr/bin/env python3
"""Test motion using SmoothieConnection with Opentrons-style move."""

import asyncio
import importlib.util
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Load io module directly to bypass unitelabs.cdk dependency
spec = importlib.util.spec_from_file_location(
    "smoothie_io", "/root/ot2_sila2/src/unitelabs/opentrons_ot2/io/__init__.py"
)
smoothie_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoothie_io)

SmoothieConnection = smoothie_io.SmoothieConnection
find_smoothie_port = smoothie_io.find_smoothie_port


async def main():
    print("=== Motion Test with Proper Opentrons Pattern ===")
    print()

    conn = SmoothieConnection(find_smoothie_port())
    await conn.connect()
    print(f"Connected: {conn.is_connected}")
    print()

    # First home to establish known position
    print("1. Homing all axes...")
    position = await conn.home("XYZABC")
    home_z = position["Z"]
    print(f"   Home position: X={position['X']:.1f} Y={position['Y']:.1f} Z={position['Z']:.1f}")
    print()

    # Test simple XY move (safe, within bounds)
    print("2. Moving X to 200, Y to 200...")
    await conn.move({"X": 200.0, "Y": 200.0})
    pos = await conn.get_position()
    print(f"   Position: X={pos['X']:.1f} Y={pos['Y']:.1f}")
    print()

    # Test Z move DOWN (lower values are towards deck)
    # Stay well within bounds (home is at top)
    safe_z = max(10.0, home_z - 50.0)
    print(f"3. Moving Z down to {safe_z:.1f} (from home {home_z:.1f})...")
    await conn.move({"Z": safe_z})
    pos = await conn.get_position()
    print(f"   Position: Z={pos['Z']:.1f}")
    print()

    # Test combined move (stay within bounds)
    print("4. Combined move: X=300, Y=100...")
    await conn.move({"X": 300.0, "Y": 100.0})
    pos = await conn.get_position()
    print(f"   Position: X={pos['X']:.1f} Y={pos['Y']:.1f}")
    print()

    # Test plunger move (B axis) with backlash compensation
    print("5. Moving B axis (plunger) to 10mm...")
    await conn.move({"B": 10.0})
    pos = await conn.get_position()
    print(f"   Position: B={pos['B']:.3f}")
    print()

    # Move plunger back
    print("6. Moving B axis back to 5mm...")
    await conn.move({"B": 5.0})
    pos = await conn.get_position()
    print(f"   Position: B={pos['B']:.3f}")
    print()

    # Return Z to near home, then home all
    print("7. Returning to home position...")
    await conn.move({"Z": home_z - 5.0})  # Move Z up first (safety)
    await conn.home("XYZABC")
    pos = await conn.get_position()
    print(f"   Final: X={pos['X']:.1f} Y={pos['Y']:.1f} Z={pos['Z']:.1f} B={pos['B']:.3f}")
    print()

    await conn.disconnect()
    print("=== Motion Test Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
