"""
Phase 01: Home

Connects to the OT-2, homes all axes, and logs the final position.

End state (checkpoint): All axes homed, robot ready for use.

Note: uses @flow from prefect directly (not @phase from unitelabs.sdk) because
the deploy server requires @flow on the entrypoint and all phases must match
(all-or-nothing rule, AUT-62). Switch the entire workflow/phase pair to SDK
decorators once AUT-62 ships.
"""

from prefect import flow
from unitelabs.sdk import get_logger

from ._helpers import INSTRUMENT_NAME
from ._steps import connect_to_ot2_step, get_position_step, home_ot2_step


@flow(name="Phase 01: Home", retries=1, retry_delay_seconds=60)
async def phase_home(device_name: str = INSTRUMENT_NAME) -> None:
    """
    Connect to the OT-2, home all axes, and log final position.

    Steps:
      1. connect_to_ot2_step  — get service handle
      2. home_ot2_step        — home gantry axes (XYZ)
      3. get_position_step    — read and log final axis positions

    Args:
      device_name: UniteLabs service name for the OT-2 connector.
    """

    logger = get_logger()
    logger.info(f"Phase 01: Home | device={device_name!r}")

    ot2, _client = await connect_to_ot2_step(device_name=device_name)
    await home_ot2_step(ot2=ot2)
    await get_position_step(ot2=ot2)

    logger.info("Phase 01 complete — OT-2 homed and ready")
