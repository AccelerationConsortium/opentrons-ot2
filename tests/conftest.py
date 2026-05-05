import sys
from unittest.mock import MagicMock

# gpiod is a Linux-only kernel library; stub it so tests run on any platform.
if "gpiod" not in sys.modules:
    sys.modules["gpiod"] = MagicMock()

try:
    import unitelabs.bus.testing.fixtures  # noqa: F401

    pytest_plugins = ["unitelabs.bus.testing.fixtures"]
except ImportError:
    pytest_plugins = []
