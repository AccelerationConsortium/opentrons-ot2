"""
Console entrypoint for local runs.

  uv run --env-file .env --directory ot2-jingle workflow
  uv run --env-file .env --directory ot2-jingle workflow --device "My OT-2"
"""

import argparse
import asyncio

from ._helpers import INSTRUMENT_NAME
from .workflow import ot2_jingle_flow


def main() -> None:
    """Parse args and run the workflow."""
    parser = argparse.ArgumentParser(description="Play a jingle on the OT-2 buzzer.")
    parser.add_argument(
        "--device",
        default=INSTRUMENT_NAME,
        help="UniteLabs service name for the OT-2 (default: %(default)r).",
    )
    args = parser.parse_args()
    asyncio.run(ot2_jingle_flow(device_name=args.device))


if __name__ == "__main__":
    main()
