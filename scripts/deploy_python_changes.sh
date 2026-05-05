#!/bin/sh
# Usage: ./scripts/deploy_python_changes.sh <host> [venv_path]
# Syncs src/unitelabs/opentrons_ot2/ straight into the installed package in
# the venv on the robot — no wheel rebuild, no reinstall.
set -e

HOST="${1:?Usage: $0 <host> [venv_path]}"
VENV="${2:-/var/sila2_ot2}"
REMOTE_PKG="$VENV/lib/python3.10/site-packages/unitelabs/opentrons_ot2"
LOCAL_SRC="$(dirname "$0")/../src/unitelabs/opentrons_ot2/"

echo "Copying to root@$HOST:$REMOTE_PKG ..."
scp -r "$LOCAL_SRC"/* "root@$HOST:$REMOTE_PKG/"

echo "Clearing __pycache__ on robot..."
ssh "root@$HOST" "find '$REMOTE_PKG' -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true"

echo "Restarting sila2-connector service on robot..."
ssh "root@$HOST" "systemctl restart sila2-connector && systemctl status sila2-connector --no-pager"

echo "Done. Logs: ssh root@$HOST 'journalctl -u sila2-connector -f'"
