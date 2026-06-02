"""
Phase 02: Transfer

Executes column-by-column plate-to-plate liquid transfers.
Columns 1 and 2 are transferred without mixing; the final column is transferred
with post-dispense mixing (3 cycles x 80 uL).

End state (checkpoint): All columns transferred, tips discarded,
source plate depleted in the target columns, destination plate filled.
"""

from prefect import flow
from unitelabs.sdk import get_logger

from shared.ot2 import OT2, OT2Labware, OT2TipRack

from ._helpers import COLUMNS_TO_TRANSFER
from ._steps import transfer_column_step


@flow(name="Phase 02: Transfer", retries=0)
async def phase_transfer(
    ot2: OT2,
    tip_rack: OT2TipRack,
    source_plate: OT2Labware,
    dest_plate: OT2Labware,
) -> None:
    """
    Transfer columns from source plate to destination plate.

    Columns 1 to N-1: no mixing.
    Column N (final): post-dispense mixing (3 cycles x 80 uL).

    Steps:
      1..N-1. transfer_column_step — no mix
      N.      transfer_column_step — mix_after=True
    """
    logger = get_logger()
    logger.info(f"Phase 02: Transfer | columns=1-{COLUMNS_TO_TRANSFER}")

    for col in range(COLUMNS_TO_TRANSFER - 1):
        await transfer_column_step(
            ot2=ot2,
            tip_rack=tip_rack,
            source_plate=source_plate,
            dest_plate=dest_plate,
            column=col,
            mix_after=False,
        )

    await transfer_column_step(
        ot2=ot2,
        tip_rack=tip_rack,
        source_plate=source_plate,
        dest_plate=dest_plate,
        column=COLUMNS_TO_TRANSFER - 1,
        mix_after=True,
    )

    logger.info(f"Phase 02 complete — {COLUMNS_TO_TRANSFER} columns transferred")
