#!/bin/sh
# Verify both services are up on the robot: Tailscale and the SiLA2 connector.
# Every check runs regardless of whether an earlier one failed -- exits non-zero
# only at the end, if anything failed.
# Usage: ./scripts/verify_ot2.sh <host>

HOST="${1:?Usage: $0 <host>}"
FAILED=0

check() {
    label="$1"
    shift
    if ssh "root@$HOST" "$@"; then
        echo "[PASS] $label"
    else
        echo "[FAIL] $label"
        FAILED=1
    fi
}

echo "=== Tailscale ==="
check "start-tailscale service active" systemctl is-active start-tailscale
check "tailscale status" '/data/tailscale_*/tailscale status'

echo ""
echo "=== SiLA2 connector ==="
check "sila2-connector service active" systemctl is-active sila2-connector
check "sila2-connector logs (last 20 lines)" journalctl -u sila2-connector -n 20 --no-pager

echo ""
echo "=== opentrons HTTP API (port 31950) ==="
# The systemd/log checks above only prove the process is running -- not that the
# in-process robot-server actually answers. HardwareNotYetInitialized (light
# controller never populated, or hardware init genuinely stuck) shows up here,
# not in "service active".
# Every check below is passed to check() as ONE single-quoted shell argument (never
# split across several), because check() forwards "$@" straight to ssh -- ssh rejoins
# multiple arguments with plain spaces before the remote shell reparses them, which
# silently destroys any quoting boundary between separate arguments. Being one single-
# quoted argument means no literal ' may appear anywhere inside; the heredoc delimiter
# is double-quoted (<<"PYEOF", not <<'PYEOF') for exactly that reason. A double-quoted
# (or single-quoted) heredoc delimiter disables all $/backtick expansion in the body,
# so python's own double-quoted strings inside pass through untouched.
check "GET /health returns 200" 'python3 <<"PYEOF"
import urllib.request
req = urllib.request.Request("http://localhost:31950/health", headers={"Opentrons-Version": "*"})
urllib.request.urlopen(req, timeout=10)
PYEOF'

# POST /runs is the endpoint that actually needs the light controller (see
# _create_app_with_robot_server's docstring) -- /health alone does not exercise it.
# Clean up the created run immediately so repeated verify runs do not accumulate.
check "POST /runs creates a run (201)" 'python3 <<"PYEOF"
import json
import urllib.request
headers = {"Opentrons-Version": "*"}
req = urllib.request.Request("http://localhost:31950/runs", method="POST", headers=headers, data=json.dumps({}).encode())
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(req, timeout=10) as resp:
    run_id = json.load(resp)["data"]["id"]
urllib.request.urlopen(
    urllib.request.Request("http://localhost:31950/runs/" + run_id, method="DELETE", headers=headers),
    timeout=10,
)
PYEOF'

exit $FAILED
