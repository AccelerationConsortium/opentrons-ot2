"""
Phase 01: Setup

Connects to the OT-2, homes the XYZ gantry, reads deck calibration from the
robot's stored calibration data, and loads the deck layout with exact positions.

End state (checkpoint): Robot homed, calibration read, labware objects instantiated
with accurate deck coordinates -- ready for transfers.
"""

from prefect import flow
from unitelabs.sdk import get_logger


from ._helpers import INSTRUMENT_NAME
from ._steps import connect_step, get_calibration_step, home_step, setup_deck_step


@flow(name="Phase 01: Setup", retries=1, retry_delay_seconds=60)
async def phase_setup(device_name: str = INSTRUMENT_NAME) -> dict:
    """
    Connect to the OT-2, home XYZ, read calibration, and instantiate labware.

    Steps:
      1. connect_step        -- connect to platform, verify pipettes
      2. home_step           -- home XYZ gantry axes
      3. get_calibration_step -- read nozzle_deck_a and tip_length_mm from robot
      4. setup_deck_step     -- create OT2 handle and labware with calibrated positions

    Returns:
      dict with keys: ot2, tip_rack, source_plate, dest_plate
    """
    logger = get_logger()
    logger.info(f"Phase 01: Setup | device={device_name!r}")

    service, _client = await connect_step(device_name=device_name)
    await home_step(service=service)
    nozzle_deck_a, tip_length_mm = await get_calibration_step(service=service)
    ot2, tip_rack, source_plate, dest_plate = await setup_deck_step(
        service=service,
        nozzle_deck_a=nozzle_deck_a,
        tip_length_mm=tip_length_mm,
    )

    logger.info("Phase 01 complete -- robot homed, calibration loaded, deck ready")
    return {
        "ot2": ot2,
        "tip_rack": tip_rack,
        "source_plate": source_plate,
        "dest_plate": dest_plate,
    }
