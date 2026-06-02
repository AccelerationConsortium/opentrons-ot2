"""
Workflow: OT-2 Plate-to-Plate Transfer

Picks up tips and transfers 100 µL of liquid from a source plate to a destination
plate across 3 columns, with post-dispense mixing on the final column.

Deck layout (configurable via constants in _helpers.py):
  Slot 1 — opentrons_96_tiprack_300ul
  Slot 2 — nest_96_wellplate_200ul_flat (source)
  Slot 3 — nest_96_wellplate_200ul_flat (destination)

Phases:
  01 — setup:    Connect, home XYZ, load deck layout
  02 — transfer: Column-by-column plate-to-plate transfers with final-column mixing

Note: uses @flow from prefect directly (not @workflow from unitelabs.sdk) because
the deploy server validates the entrypoint by looking for a @flow-decorated function
(AUT-62). Switch to @workflow once AUT-62 ships.
"""

from prefect import flow
from unitelabs.sdk import get_logger

from ._helpers import INSTRUMENT_NAME
from .phase_01_setup import phase_setup
from .phase_02_transfer import phase_transfer


@flow(name="Workflow: OT-2 Plate-to-Plate Transfer", retries=0)
async def ot2_transfer_flow(device_name: str = INSTRUMENT_NAME) -> None:
    """
    Orchestrate the full plate-to-plate transfer.

    Args:
      device_name: UniteLabs service name for the OT-2 connector.
    """
    logger = get_logger()
    logger.info(f"Starting OT-2 Plate-to-Plate Transfer | device={device_name!r}")

    result = await phase_setup(device_name=device_name)

    await phase_transfer(
        ot2=result["ot2"],
        tip_rack=result["tip_rack"],
        source_plate=result["source_plate"],
        dest_plate=result["dest_plate"],
    )

    logger.info("OT-2 Plate-to-Plate Transfer complete")
