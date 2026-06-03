"""
OT-2 Jingle Steps (@task)

Each function is tracked by Prefect as a discrete step.
"""

from prefect import task
from prefect.cache_policies import NONE
from unitelabs.sdk import get_logger

from ._helpers import INSTRUMENT_NAME, ODE_TO_JOY, get_ot2_service


@task(name="Step: Connect to OT-2", log_prints=True, retries=3, retry_delay_seconds=5)
async def connect_step(device_name: str = INSTRUMENT_NAME):
    """Connect to the OT-2 and return the service handle."""
    logger = get_logger()
    logger.info(f"Connecting to OT-2: {device_name!r}")
    service, client = await get_ot2_service(device_name)
    logger.info("Connected")
    return service, client


@task(name="Step: Play Jingle", log_prints=True, cache_policy=NONE, retries=0)
async def play_jingle_step(service) -> None:
    """Play Ode to Joy through the OT-2 buzzer."""
    logger = get_logger()
    logger.info(f"Playing Ode to Joy ({len(ODE_TO_JOY)} notes)")
    for freq_hz, duration_ms in ODE_TO_JOY:
        await service.motion_control_feature.play_tone(
            frequency_hz=freq_hz,
            duration_ms=duration_ms,
        )
    logger.info("Jingle complete")
