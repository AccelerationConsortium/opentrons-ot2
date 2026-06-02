from __future__ import annotations

from ._pipette import OT2Pipette


class OT2:
    """
    Top-level handle for the OT-2, analogous to MicrolabSTAR in the Hamilton SDK.

    Wraps the SiLA service handle returned by client.get_service_by_name() and
    exposes a pipette interface that mirrors unitelabs.liquid_handling.hamilton.
    """

    def __init__(self, service) -> None:
        self._service = service
        self._pipette = OT2Pipette(
            motion_control=service.motion_control_feature,
        )

    @property
    def pipette(self) -> OT2Pipette:
        return self._pipette

    @property
    def motion_control(self):
        return self._service.motion_control_feature

    @property
    def pipette_feature(self):
        return self._service.pipette_feature
