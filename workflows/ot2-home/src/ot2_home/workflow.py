"""
Workflow: OT-2 Home

Connects to the Opentrons OT-2 via the UniteLabs platform and homes all axes.

Phases:
  01 — home: Connect, home XYZABC, log final position.

Note: uses @flow from prefect directly (not @workflow from unitelabs.sdk) because
the deploy server validates the entrypoint by looking for a @flow-decorated function
(AUT-62, "In Testing" as of 2026-05-20). Switch to @workflow once AUT-62 ships —
and switch phase_01_home.py at the same time (all-or-nothing rule).
"""

from prefect import flow
from unitelabs.sdk import get_logger

from ._helpers import INSTRUMENT_NAME
from .phase_01_home import phase_home


@flow(name="Workflow: OT-2 Home", retries=0)
async def ot2_home_flow(device_name: str = INSTRUMENT_NAME) -> None:
    """
    Home the OT-2 and verify it is ready.

    Args:
      device_name: UniteLabs service name for the OT-2 connector.
    """

    logger = get_logger()
    logger.info(f"Starting OT-2 Home | device={device_name!r}")

    await phase_home(device_name=device_name)

    logger.info("OT-2 Home complete")
