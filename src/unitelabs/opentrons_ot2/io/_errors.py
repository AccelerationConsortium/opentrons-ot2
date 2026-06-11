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


# Defined errors every module command can raise; the features pass this to their
# SiLA command declarations (plus any command-specific errors).
COMMON_MODULE_ERRORS = (ModuleNotRespondingError, ModuleOperationError)


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

    # Marker so translate_public_async_methods never wraps a method twice
    # (functools.wraps copies fn.__dict__, so set this after decorating).
    wrapper._translates_module_errors = True  # type: ignore[attr-defined]
    return wrapper


def translate_public_async_methods(cls: type) -> None:
    """
    Apply ``translate_module_errors`` to every public async instance method of cls.

    Only methods defined directly on ``cls`` (``vars(cls)``) are wrapped; already
    wrapped methods are skipped, so applying this to both a base class and its
    subclasses is safe.
    """
    for name, attr in list(vars(cls).items()):
        if name.startswith("_") or not inspect.iscoroutinefunction(attr):
            continue
        if getattr(attr, "_translates_module_errors", False):
            continue
        setattr(cls, name, translate_module_errors(attr))
