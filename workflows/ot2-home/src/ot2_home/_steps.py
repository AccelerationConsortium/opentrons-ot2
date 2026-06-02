"""
OT-2 Steps (@task)

Scientifically atomic units of work for the Opentrons OT-2.
Each function is tracked by the workflow engine (Prefect) as a discrete step.

Note: uses @task from prefect directly (not @step from unitelabs.sdk) because
@step does not yet accept log_prints (AUT-249). Switch to @step once resolved.
"""

from prefect import task
from prefect.cache_policies import NONE
from unitelabs.sdk import get_logger

from ._helpers import INSTRUMENT_NAME, get_ot2_service


@task(name="Step: Connect to OT-2", log_prints=True, retries=3, retry_delay_seconds=5)
async def connect_to_ot2_step(device_name: str = INSTRUMENT_NAME):
    """
    Connect to the OT-2 connector and return the service handle.

    Args:
      device_name: UniteLabs service name for the OT-2 connector.

    Returns:
      Tuple of (ot2_service, client).
    """
    logger = get_logger()
    logger.info(f"Connecting to OT-2: {device_name!r}")
    ot2, client = await get_ot2_service(device_name)
    logger.info(f"Connected | modules: {list(ot2.modules.keys())}")
    return ot2, client


@task(name="Step: Home OT-2", log_prints=True, cache_policy=NONE, retries=0)
async def home_ot2_step(ot2, axes: str = "XYZ") -> None:
    """
    Home the specified axes on the OT-2.

    Args:
      ot2: Connected OT-2 service instance.
      axes: Axes to home (default: XYZ gantry axes; excludes A/B/C pipette plungers).
    """
    logger = get_logger()
    logger.info(f"Homing axes: {axes}")
    await ot2.motion_control_feature.home(axes=axes)
    logger.info("Homing complete")


@task(name="Step: Get OT-2 Position", log_prints=True, cache_policy=NONE)
async def get_position_step(ot2) -> str:
    """
    Read and log the current axis positions.

    Args:
      ot2: Connected OT-2 service instance.

    Returns:
      Position string for logging.
    """
    logger = get_logger()
    position = await ot2.motion_control_feature.get_position()
    logger.info(f"Position: {position}")
    return str(position)
