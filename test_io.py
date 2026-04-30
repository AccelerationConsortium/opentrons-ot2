#!/usr/bin/env python3
"""Test the SmoothieConnection class from the io module."""

import asyncio
import importlib.util

# Load io module directly from file (bypass __init__.py which requires unitelabs.cdk)
spec = importlib.util.spec_from_file_location(
    "smoothie_io", "/root/ot2_sila2/src/unitelabs/opentrons_ot2/io/__init__.py"
)
smoothie_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoothie_io)

SmoothieConnection = smoothie_io.SmoothieConnection
find_smoothie_port = smoothie_io.find_smoothie_port


async def main():
    print("=== Testing SmoothieConnection ===\n")

    # Find port
    port = find_smoothie_port()
    if not port:
        print("ERROR: Smoothie not found")
        return
    print(f"Found Smoothie at: {port}\n")

    # Create connection
    conn = SmoothieConnection(port)

    # Connect
    print("Connecting...")
    await conn.connect()
    print(f"Connected: {conn.is_connected}\n")

    # Test commands
    print("1. Firmware version (M115):")
    response = await conn.send_command("M115")
    print(f"   {response[:200]}\n")

    print("2. Current position (M114.2):")
    response = await conn.send_command("M114.2")
    print(f"   {response}\n")

    print("3. Limit switches (M119):")
    response = await conn.send_command("M119")
    print(f"   {response}\n")

    # Disconnect
    await conn.disconnect()
    print(f"Disconnected: {not conn.is_connected}")
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
