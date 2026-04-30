#!/usr/bin/env python3
"""Simple SiLA2 client to test OT-2 connector commands."""

import asyncio
import sys

from unitelabs.cdk.client import SilaClient


async def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "ot2cep20240218r04.local"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 50052

    print(f"Connecting to SiLA2 server at {host}:{port}...")

    async with SilaClient(host, port) as client:
        print("Connected!")
        print(f"Server: {client.server_name}")
        print(f"Features: {[f.display_name for f in client.features]}")

        # Find motion control feature
        motion = None
        for feature in client.features:
            if "Motion" in feature.display_name or "motion" in feature.identifier:
                motion = feature
                break

        if not motion:
            print("ERROR: MotionControlFeature not found")
            return

        print(f"\nUsing feature: {motion.display_name}")
        print(f"Commands: {[c.display_name for c in motion.commands]}")

        # Call home command
        print("\n=== Calling home(axes='XYZABC') ===")
        result = await motion.home(axes="XYZABC")
        print(f"Result: {result}")

        # Get position
        print("\n=== Calling get_position() ===")
        pos = await motion.get_position()
        print(f"Position: {pos}")


if __name__ == "__main__":
    asyncio.run(main())
