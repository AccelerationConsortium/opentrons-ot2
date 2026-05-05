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
