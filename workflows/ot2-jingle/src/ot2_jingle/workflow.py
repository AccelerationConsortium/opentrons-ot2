"""
Workflow: OT-2 Jingle

Plays Ode to Joy through the OT-2 Smoothie buzzer via the SiLA play_tone command.

Phases:
  01 — jingle: Connect and play.
"""

from prefect import flow
from unitelabs.sdk import get_logger

from ._helpers import INSTRUMENT_NAME
from .phase_01_jingle import phase_jingle


@flow(name="Workflow: OT-2 Jingle", retries=0)
async def ot2_jingle_flow(device_name: str = INSTRUMENT_NAME) -> None:
    """
    Play Ode to Joy on the OT-2 buzzer.

    Args:
        device_name: UniteLabs service name for the OT-2 connector.
    """
    logger = get_logger()
    logger.info(f"Starting OT-2 Jingle | device={device_name!r}")

    await phase_jingle(device_name=device_name)

    logger.info("OT-2 Jingle complete")
