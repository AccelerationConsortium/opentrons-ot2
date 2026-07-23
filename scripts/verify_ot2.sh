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

exit $FAILED
