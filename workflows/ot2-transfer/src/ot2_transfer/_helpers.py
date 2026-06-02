from unitelabs.sdk import Client

INSTRUMENT_NAME = "Opentrons OT-2"

# Deck slot assignments
TIP_RACK_SLOT = 1
SOURCE_PLATE_SLOT = 2
DEST_PLATE_SLOT = 3

# Labware definition names (from opentrons_shared_data)
TIP_RACK_DEFINITION = "opentrons_96_tiprack_300ul"
PLATE_DEFINITION = "nest_96_wellplate_200ul_flat"

# Transfer parameters
TRANSFER_VOLUME_UL = 100.0
COLUMNS_TO_TRANSFER = 3


async def get_ot2_service(device_name: str):
    client = Client()
    service = await client.get_service_by_name(device_name)
    if service is None:
        msg = f"Service '{device_name}' not found. Check the device name and that it is connected to the platform."
        raise ValueError(msg)
    return service, client
