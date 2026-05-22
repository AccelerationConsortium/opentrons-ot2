import sys
import types
from unittest.mock import MagicMock

# gpiod is a Linux-only kernel library; stub it so tests run on any platform.
if "gpiod" not in sys.modules:
    sys.modules["gpiod"] = MagicMock()

# robot_server is an Opentrons-internal package not published to PyPI.
# Stub it so the with_robot_server=True code path can be exercised in CI.
if "robot_server" not in sys.modules:
    _rs = types.ModuleType("robot_server")
    _rs_hw = types.ModuleType("robot_server.hardware")
    _rs_hw._hw_api_accessor = MagicMock(name="_hw_api_accessor")
    _rs_hw._init_task_accessor = MagicMock(name="_init_task_accessor")
    _rs_app_setup = types.ModuleType("robot_server.app_setup")
    _rs_app_setup.app = MagicMock(name="robot_server_app")
    sys.modules["robot_server"] = _rs
    sys.modules["robot_server.hardware"] = _rs_hw
    sys.modules["robot_server.app_setup"] = _rs_app_setup

try:
    import unitelabs.bus.testing.fixtures  # noqa: F401

    pytest_plugins = ["unitelabs.bus.testing.fixtures"]
except ImportError:
    pytest_plugins = []
