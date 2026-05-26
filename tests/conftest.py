import sys
import types
from unittest.mock import MagicMock

# gpiod is a Linux-only kernel library; stub it so tests run on any platform.
if "gpiod" not in sys.modules:
    sys.modules["gpiod"] = MagicMock()

# robot_server is an Opentrons-internal package not published to PyPI.
# Stub it when it is not installed so the with_robot_server=True wiring tests
# (test_create_app_with_robot_server.py) can run in CI without the real package.
# When the real robot_server IS installed (e.g. the HTTP integration step), the
# real package is used and these stubs are not inserted.
try:
    import robot_server as _  # noqa: F401
except ImportError:
    _rs = types.ModuleType("robot_server")
    _rs_hw = types.ModuleType("robot_server.hardware")
    _rs_hw._hw_api_accessor = MagicMock(name="_hw_api_accessor")
    _rs_hw._init_task_accessor = MagicMock(name="_init_task_accessor")
    _rs_app = types.ModuleType("robot_server.app")
    _rs_app.app = MagicMock(name="robot_server_app")
    sys.modules["robot_server"] = _rs
    sys.modules["robot_server.hardware"] = _rs_hw
    sys.modules["robot_server.app"] = _rs_app

try:
    import unitelabs.bus.testing.fixtures  # noqa: F401

    pytest_plugins = ["unitelabs.bus.testing.fixtures"]
except ImportError:
    pytest_plugins = []
