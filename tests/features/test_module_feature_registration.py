"""SiLA-definition smoke test for the module features (no hardware).

The module features are only registered at runtime when a module is attached, so
nothing else exercises their SiLA feature-definition generation. Registering each
with a dummy controller and starting the connector builds the SiLA definitions,
catching invalid command/return types (e.g. the DeviceInfo structure, status
enums) without needing an attached module.
"""

import pytest

from unitelabs.cdk import Connector, SiLAServerConfig
from unitelabs.opentrons_ot2 import OpentronsOt2Config
from unitelabs.opentrons_ot2.features import (
    HeaterShakerFeature,
    MagneticModuleFeature,
    TemperatureModuleFeature,
    ThermocyclerFeature,
)

_MODULE_FEATURES = [
    TemperatureModuleFeature,
    HeaterShakerFeature,
    ThermocyclerFeature,
    MagneticModuleFeature,
]


@pytest.mark.parametrize("feature_cls", _MODULE_FEATURES)
@pytest.mark.asyncio
async def test_module_feature_sila_definition_builds(feature_cls) -> None:
    config = OpentronsOt2Config(
        use_simulator=True,
        sila_server=SiLAServerConfig(hostname="127.0.0.1", port=0, tls=False),
        cloud_server_endpoint=None,
        discovery=None,
    )
    connector = Connector(config)
    # SiLA generation introspects the method signatures/type hints, not the
    # controller instance, so a placeholder controller is sufficient here.
    connector.register(feature_cls(object()))
    await connector.start()
    try:
        assert connector.sila_server.protobuf is not None
    finally:
        await connector.stop()
