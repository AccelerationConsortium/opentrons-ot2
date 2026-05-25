"""Integration tests for the in-process opentrons HTTP robot-server.

These tests exercise the HTTP API that our connector starts in-process when
``with_robot_server=True``.  The server is the standard opentrons robot-server
FastAPI app, but backed by our ``HardwareProxy`` instead of a fresh hardware
instance.  nginx on the OT-2 proxies TCP 31950 to the Unix domain socket we
bind.

Run against a live robot::

    uv run pytest tests/integration/http_api/ --robot 100.108.249.112:50051

All tests are marked ``robot_http_only`` and are skipped in the simulator test
suite.
"""

import pytest

# ── /health ───────────────────────────────────────────────────────────────────


@pytest.mark.robot_http_only
def test_health_returns_200(http_client):
    """GET /health responds with 200 OK."""
    response = http_client.get("/health")
    assert response.status_code == 200


@pytest.mark.robot_http_only
def test_health_robot_model_is_ot2(http_client):
    """GET /health identifies the robot as an OT-2."""
    data = http_client.get("/health").json()
    assert data["robot_model"] == "OT-2 Standard"


@pytest.mark.robot_http_only
def test_health_has_api_version(http_client):
    """GET /health includes a non-empty api_version string."""
    data = http_client.get("/health").json()
    assert isinstance(data["api_version"], str)
    assert data["api_version"]


@pytest.mark.robot_http_only
def test_health_has_name(http_client):
    """GET /health includes a robot name."""
    data = http_client.get("/health").json()
    assert isinstance(data["name"], str)
    assert data["name"]


# ── /pipettes ─────────────────────────────────────────────────────────────────


@pytest.mark.robot_http_only
def test_pipettes_returns_200(http_client):
    """GET /pipettes responds with 200 OK."""
    response = http_client.get("/pipettes")
    assert response.status_code == 200


@pytest.mark.robot_http_only
def test_pipettes_left_mount_present(http_client):
    """GET /pipettes returns a left-mount entry with model and id from hardware."""
    data = http_client.get("/pipettes").json()
    left = data.get("left", {})
    assert left.get("model"), "left pipette model missing — HardwareProxy may not be wired"
    assert left.get("id"), "left pipette id missing"


@pytest.mark.robot_http_only
def test_pipettes_right_mount_present(http_client):
    """GET /pipettes returns a right-mount entry with model and id from hardware."""
    data = http_client.get("/pipettes").json()
    right = data.get("right", {})
    assert right.get("model"), "right pipette model missing — HardwareProxy may not be wired"
    assert right.get("id"), "right pipette id missing"


# ── /modules ──────────────────────────────────────────────────────────────────


@pytest.mark.robot_http_only
def test_modules_returns_200(http_client):
    """GET /modules responds with 200 OK."""
    response = http_client.get("/modules")
    assert response.status_code == 200


@pytest.mark.robot_http_only
def test_modules_response_has_data_list(http_client):
    """GET /modules returns a JSON object with a 'data' list."""
    data = http_client.get("/modules").json()
    assert "data" in data
    assert isinstance(data["data"], list)


# ── /robot/lights ─────────────────────────────────────────────────────────────


@pytest.mark.robot_http_only
def test_lights_returns_200(http_client):
    """GET /robot/lights responds with 200 OK."""
    response = http_client.get("/robot/lights")
    assert response.status_code == 200


@pytest.mark.robot_http_only
def test_lights_has_on_field(http_client):
    """GET /robot/lights returns an object with a boolean 'on' field."""
    data = http_client.get("/robot/lights").json()
    assert "on" in data
    assert isinstance(data["on"], bool)


@pytest.mark.robot_http_only
def test_lights_toggle_roundtrip(http_client):
    """POST /robot/lights can toggle the light on then off."""
    initial = http_client.get("/robot/lights").json()["on"]

    http_client.post("/robot/lights", json={"on": not initial})
    assert http_client.get("/robot/lights").json()["on"] is not initial

    # restore
    http_client.post("/robot/lights", json={"on": initial})
    assert http_client.get("/robot/lights").json()["on"] is initial


# ── /robot/home ───────────────────────────────────────────────────────────────


@pytest.mark.robot_http_only
def test_home_returns_200(http_client):
    """POST /robot/home responds with 200 OK — hardware is reachable via HardwareProxy."""
    response = http_client.post("/robot/home", json={"target": "pipette", "mount": "left"})
    assert response.status_code == 200
