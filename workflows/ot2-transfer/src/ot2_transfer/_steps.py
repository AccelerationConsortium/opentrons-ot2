"""
OT-2 Transfer Steps (@task)

Scientifically atomic units of work for the plate-to-plate transfer workflow.
Each function is tracked by Prefect as a discrete step.
"""

from prefect import task
from prefect.cache_policies import NONE
from unitelabs.sdk import get_logger

from shared.ot2 import OT2, OT2Labware, OT2TipRack

from ._helpers import (
    DEST_PLATE_SLOT,
    INSTRUMENT_NAME,
    PLATE_DEFINITION,
    SOURCE_PLATE_SLOT,
    TIP_RACK_DEFINITION,
    TIP_RACK_SLOT,
    TRANSFER_VOLUME_UL,
    get_ot2_service,
)


@task(name="Step: Connect to OT-2", log_prints=True, retries=3, retry_delay_seconds=5)
async def connect_step(device_name: str = INSTRUMENT_NAME):
    """Connect to the OT-2, verify pipettes are attached, return OT2 handle."""
    logger = get_logger()
    logger.info(f"Connecting to OT-2: {device_name!r}")
    service, client = await get_ot2_service(device_name)
    pipettes = await service.pipette_feature.get_attached_pipettes()
    logger.info(f"Attached pipettes: {pipettes}")
    ot2 = OT2(service=service)
    return ot2, client


@task(name="Step: Home OT-2", log_prints=True, retries=0)
async def home_step(ot2: OT2) -> None:
    """Home XYZ gantry axes."""
    logger = get_logger()
    logger.info("Homing XYZ")
    await ot2.motion_control.home(axes="XYZ")
    logger.info("Homing complete")


@task(name="Step: Setup Deck", log_prints=True)
async def setup_deck_step(ot2: OT2) -> tuple[OT2TipRack, OT2Labware, OT2Labware]:
    """Instantiate labware objects for the configured deck slots."""
    logger = get_logger()
    tip_rack = OT2TipRack(TIP_RACK_DEFINITION, slot=TIP_RACK_SLOT)
    source_plate = OT2Labware(PLATE_DEFINITION, slot=SOURCE_PLATE_SLOT)
    dest_plate = OT2Labware(PLATE_DEFINITION, slot=DEST_PLATE_SLOT)
    logger.info(
        f"Deck: slot {TIP_RACK_SLOT}={TIP_RACK_DEFINITION} | "
        f"slot {SOURCE_PLATE_SLOT}={PLATE_DEFINITION} (source) | "
        f"slot {DEST_PLATE_SLOT}={PLATE_DEFINITION} (dest)"
    )
    logger.info(f"Tips remaining: {tip_rack.tips_remaining}")
    return tip_rack, source_plate, dest_plate


@task(name="Step: Transfer Column", log_prints=True, cache_policy=NONE, retries=0)
async def transfer_column_step(
    ot2: OT2,
    tip_rack: OT2TipRack,
    source_plate: OT2Labware,
    dest_plate: OT2Labware,
    column: int,
    mix_after: bool = False,
) -> None:
    """
    Transfer one column (8 wells) from source plate to destination plate.

    Performs: pick up tips → aspirate → dispense (with optional mixing) → discard tips.
    Tips are always discarded, even on pipetting errors.

    The individual SDK operations (pick_up_tip, aspirate, dispense, discard_tip) are
    atomic hardware calls — they are not wrapped in separate @task functions because
    tasks must not call other tasks. They are operations, not steps.
    """
    logger = get_logger()
    col_label = column + 1
    source_wells = source_plate.column(column)
    dest_wells = dest_plate.column(column)
    logger.info(f"Column {col_label}: transferring {TRANSFER_VOLUME_UL} µL x 8 wells, mix_after={mix_after}")

    await ot2.pipette.pick_up_tip(tip_rack.next_tips())
    try:
        await ot2.pipette.aspirate(source_wells, volume_ul=TRANSFER_VOLUME_UL)
        await ot2.pipette.dispense(dest_wells, volume_ul=TRANSFER_VOLUME_UL, mix_after=mix_after)
        logger.info(f"Column {col_label} transferred")
    except Exception as e:
        logger.error(f"Pipetting error on column {col_label}: {e}")
        raise
    finally:
        await ot2.pipette.discard_tip()
        logger.info("Tips discarded")
