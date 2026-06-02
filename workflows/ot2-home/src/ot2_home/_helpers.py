"""
OT-2 Helpers (SDK-level operations)

Plain async functions that wrap UniteLabs SDK calls.
NOT tracked by the workflow engine — only Steps (@task) are tracked.
"""

from unitelabs.sdk import Client

INSTRUMENT_NAME = "Opentrons OT-2"


async def get_ot2_service(device_name: str):
    """
    Connect to the OT-2 connector service by name.

    Args:
      device_name: UniteLabs service name for the OT-2 connector.

    Returns:
      Tuple of (ot2_service, client).

    Raises:
      ValueError: If the service is not found on the platform.
    """

    client = Client()
    service = await client.get_service_by_name(device_name)
    if service is None:
        msg = f"Service '{device_name}' not found. Check the device name and that it is connected to the platform."
        raise ValueError(msg)
    return service, client
