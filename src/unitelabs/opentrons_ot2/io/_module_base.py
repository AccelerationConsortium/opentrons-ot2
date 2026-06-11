"""
Shared base for module IO controllers.

Each module controller wraps one of two backends:

- a low-level driver that owns the serial port (via the subclass ``build``), or
- a high-level opentrons module object already attached to a shared
  ``HardwareControlAPI`` (via ``from_module``), whose own poller serialises
  concurrent callers.

The backend-agnostic plumbing — construction, connection state, and device
info — lives here so the concrete controllers only implement the
device-specific commands.
"""

import logging

from ._errors import translate_public_async_methods
from ._types import DeviceInfo

log = logging.getLogger(__name__)


class ModuleControllerBase:
    """
    Common backend dispatch shared by all module controllers.

    Exactly one of ``driver`` (a low-level serial driver) or ``module`` (a
    high-level opentrons module object) is set; both are intentionally untyped
    here since each subclass wraps a different concrete type.

    Every public async method — on this base (wrapped at module import, below)
    and on each subclass (via ``__init_subclass__``) — is wrapped to translate
    opentrons driver/comm exceptions into the defined module errors, so the
    features see one stable error set regardless of backend.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        translate_public_async_methods(cls)

    def __init__(self, driver: object = None, module: object = None) -> None:
        self._driver = driver
        self._module = module

    @classmethod
    def from_module(cls, module: object) -> "ModuleControllerBase":
        """Build a controller backed by a module already attached to a shared HardwareControlAPI."""
        return cls(module=module)

    async def disconnect(self) -> None:
        """Disconnect from the module. No-op when backed by a shared module (the API owns it)."""
        if self._module is None:
            await self._driver.disconnect()

    async def is_connected(self) -> bool:
        """Check connection status."""
        if self._module is not None:
            return True
        return await self._driver.is_connected()

    async def get_device_info(self) -> DeviceInfo:
        """Get device serial number, model, and firmware version."""
        if self._module is not None:
            return DeviceInfo.from_dict(dict(self._module.device_info))
        return DeviceInfo.from_dict(await self._driver.get_device_info())


translate_public_async_methods(ModuleControllerBase)
