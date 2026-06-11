"""Shared data types for module IO wrappers."""

from dataclasses import dataclass


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
        """Build from an opentrons device_info mapping (keys: serial, model, version)."""
        return cls(
            serial_number=info.get("serial", ""),
            model=info.get("model", ""),
            firmware_version=info.get("version", ""),
        )
