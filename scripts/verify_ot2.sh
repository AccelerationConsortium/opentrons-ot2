#!/bin/sh
# Verify both services are up on the robot: Tailscale and the SiLA2 connector.
# Usage: ./scripts/verify_ot2.sh <host>
set -e

HOST="${1:?Usage: $0 <host>}"

echo "=== Tailscale ==="
ssh "root@$HOST" "systemctl is-active start-tailscale"
ssh "root@$HOST" '/data/tailscale_*/tailscale status'

echo ""
echo "=== SiLA2 connector ==="
ssh "root@$HOST" "systemctl is-active sila2-connector"
ssh "root@$HOST" "journalctl -u sila2-connector -n 20 --no-pager"
