"""
Defined hardware errors for module controllers, and translation from opentrons.

The module features surface these as SiLA Defined Execution Errors. Translation
lives at the controller (io) layer because the underlying opentrons exception
type depends on the backend in use (low-level driver vs high-level module
object) — catching them here means the features see one stable set of errors
regardless of path.

Coverage (source-verified):
- ModuleNotRespondingError  <- opentrons comm-layer SerialException / NoResponse
- ModuleOperationError      <- ThermocyclerError, TempDeckError, MagDeckError
- EngageHeightOutOfRangeError is raised explicitly by the magnetic controller
  (the magnetic module raises a plain ValueError for an out-of-range height).

Known gap: the heater-shaker has no dedicated opentrons exception class, so its
operational failures surface as comm errors (ModuleNotRespondingError) or, if
neither, as undefined errors. This should be revisited once the real
heater-shaker failure exceptions are observed on hardware.
"""

import functools
import inspect
import typing

from opentrons.drivers.asyncio.communication.errors import SerialException
from opentrons.drivers.mag_deck.driver import MagDeckError
from opentrons.drivers.temp_deck.driver import TempDeckError
from opentrons.hardware_control.modules.thermocycler import ThermocyclerError

_OPERATION_ERRORS = (ThermocyclerError, TempDeckError, MagDeckError)


class ModuleNotRespondingError(Exception):
    """
    The module did not respond — it may be disconnected or powered off.

    Check that the module is connected to the OT-2 and powered on, then retry.
    """


class ModuleOperationError(Exception):
    """
    The module reported an error while carrying out the requested operation.

    The underlying driver/module message is preserved to aid recovery (e.g.
    re-seat labware, check the module's status indicators, or power-cycle it).
    """


class EngageHeightOutOfRangeError(Exception):
    """The requested magnet engage height is outside the module's allowed range."""


def translate_module_errors(
    fn: typing.Callable[..., typing.Awaitable[object]],
) -> typing.Callable[..., typing.Awaitable[object]]:
    """Wrap an async controller method, translating opentrons exceptions to defined errors."""

    @functools.wraps(fn)
    async def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return await fn(*args, **kwargs)
        except SerialException as e:
            raise ModuleNotRespondingError(str(e)) from e
        except _OPERATION_ERRORS as e:
            raise ModuleOperationError(str(e)) from e

    return wrapper


def translate_public_async_methods(cls: type) -> None:
    """Apply ``translate_module_errors`` to every public async instance method of cls."""
    for name, attr in list(vars(cls).items()):
        if not name.startswith("_") and inspect.iscoroutinefunction(attr):
            setattr(cls, name, translate_module_errors(attr))
