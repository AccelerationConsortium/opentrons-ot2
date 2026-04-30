#!/usr/bin/env python3
"""Test homing using SmoothieConnection class with proper Opentrons sequence."""

import asyncio
import importlib.util
import logging

# Enable debug logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Load io module directly to bypass unitelabs.cdk dependency
spec = importlib.util.spec_from_file_location(
    "smoothie_io", "/root/ot2_sila2/src/unitelabs/opentrons_ot2/io/__init__.py"
)
smoothie_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoothie_io)

SmoothieConnection = smoothie_io.SmoothieConnection
SmoothieConfig = smoothie_io.SmoothieConfig
find_smoothie_port = smoothie_io.find_smoothie_port


async def main():
    print("=== Homing Test with Proper Opentrons Sequence ===")
    print()

    conn = SmoothieConnection(find_smoothie_port())
    await conn.connect()
    print(f"Connected: {conn.is_connected}")
    print()

    # Check initial limit switch state
    print("Initial limit switch state:")
    switches = await conn._check_limit_switches()
    for ax, val in sorted(switches.items()):
        print(f"  {ax}_max: {val}")
    print()

    # Home all axes using proper sequence
    print("Starting home sequence (ZABC, then X with Y backoff, then Y with retract)...")
    print()

    try:
        position = await conn.home("XYZABC")
        print()
        print("Final position after homing:")
        for ax, val in sorted(position.items()):
            print(f"  {ax}: {val:.3f}")
    except Exception as e:
        print(f"Homing failed: {e}")
        # Get position anyway
        resp = await conn.send_command("M114.2")
        print(f"Current position: {resp}")

    print()
    await conn.disconnect()
    print("=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
