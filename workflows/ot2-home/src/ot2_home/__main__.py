"""
Console entrypoint for local runs.

  uv run --env-file .env --directory ot2-home workflow
  uv run --env-file .env --directory ot2-home workflow --device "My OT-2"
"""

import argparse
import asyncio

from ._helpers import INSTRUMENT_NAME
from .workflow import ot2_home_flow


def main() -> None:
    """Parse args and run the workflow."""

    parser = argparse.ArgumentParser(description="Run ot2-home locally.")
    parser.add_argument(
        "--device",
        default=INSTRUMENT_NAME,
        help="UniteLabs service name for the OT-2 (default: %(default)r).",
    )
    args = parser.parse_args()
    asyncio.run(ot2_home_flow(device_name=args.device))


if __name__ == "__main__":
    main()
