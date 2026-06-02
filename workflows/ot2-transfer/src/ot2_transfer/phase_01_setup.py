"""
Phase 01: Setup

Connects to the OT-2, homes the XYZ gantry, and loads the deck layout.

End state (checkpoint): Robot homed, labware objects instantiated — ready for transfers.
"""

from prefect import flow
from unitelabs.sdk import get_logger


from ._helpers import INSTRUMENT_NAME
from ._steps import connect_step, home_step, setup_deck_step


@flow(name="Phase 01: Setup", retries=1, retry_delay_seconds=60)
async def phase_setup(device_name: str = INSTRUMENT_NAME) -> dict:
    """
    Connect to the OT-2, home XYZ, and instantiate labware.

    Steps:
      1. connect_step    — connect to platform, verify pipettes, create OT2 handle
      2. home_step       — home XYZ gantry axes
      3. setup_deck_step — instantiate tip rack, source plate, dest plate

    Returns:
      dict with keys: ot2, tip_rack, source_plate, dest_plate
    """
    logger = get_logger()
    logger.info(f"Phase 01: Setup | device={device_name!r}")

    ot2, _client = await connect_step(device_name=device_name)
    await home_step(ot2=ot2)
    tip_rack, source_plate, dest_plate = await setup_deck_step(ot2=ot2)

    logger.info("Phase 01 complete — robot homed, deck loaded")
    return {
        "ot2": ot2,
        "tip_rack": tip_rack,
        "source_plate": source_plate,
        "dest_plate": dest_plate,
    }
