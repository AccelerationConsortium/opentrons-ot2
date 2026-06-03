"""
Phase 01: Jingle

Connects to the OT-2 and plays Ode to Joy through the Smoothie buzzer.
"""

from prefect import flow
from unitelabs.sdk import get_logger

from ._helpers import INSTRUMENT_NAME
from ._steps import connect_step, play_jingle_step


@flow(name="Phase 01: Jingle", retries=0)
async def phase_jingle(device_name: str = INSTRUMENT_NAME) -> None:
    """
    Connect to the OT-2 and play Ode to Joy.

    Args:
        device_name: UniteLabs service name for the OT-2 connector.
    """
    logger = get_logger()
    logger.info(f"Phase 01: Jingle | device={device_name!r}")

    service, _client = await connect_step(device_name=device_name)
    await play_jingle_step(service=service)

    logger.info("Phase 01 complete")
