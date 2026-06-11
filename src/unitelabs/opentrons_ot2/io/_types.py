"""Shared data types for module IO wrappers."""

from dataclasses import dataclass

from ._errors import ModuleOperationError


@dataclass
class Temperature:
    """Temperature reading."""

    current: float
    target: float | None = None


@dataclass
class RPM:
    """RPM reading."""

    current: int
    target: int | None = None


@dataclass
class DeviceInfo:
    """Identifying information for an attached module."""

    serial_number: str
    model: str
    firmware_version: str

    @classmethod
    def from_dict(cls, info: dict) -> "DeviceInfo":
        """
        Build from an opentrons device_info mapping (keys: serial, model, version).

        Raises:
            ModuleOperationError: if any expected key is missing — a missing key
                means the opentrons device-info contract changed, and reporting
                phantom empty values would hide that (opentrons itself raises
                ParseError here, see opentrons/drivers/utils.py).
        """
        missing = [key for key in ("serial", "model", "version") if key not in info]
        if missing:
            message = f"Module device info is missing expected keys {missing}: got {sorted(info)}"
            raise ModuleOperationError(message)
        return cls(
            serial_number=info["serial"],
            model=info["model"],
            firmware_version=info["version"],
        )
