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

echo "Stopping all connector processes on robot..."
ssh "root@$HOST" "
pkill -9 -f '$VENV/bin/connector' 2>/dev/null || true
sleep 2
remaining=\$(ps aux | grep '$VENV/bin/connector' | grep -v grep | wc -l)
if [ \"\$remaining\" -gt 0 ]; then
    echo 'ERROR: connector processes still running after kill:' >&2
    ps aux | grep '$VENV/bin/connector' | grep -v grep >&2
    exit 1
fi
echo 'All connector processes stopped.'
"

echo "Starting connector on robot..."
scp "$(dirname "$0")/start_connector.sh" "root@$HOST:/data/start_connector.sh"
ssh "root@$HOST" "
nohup sh /data/start_connector.sh > /data/connector.log 2>&1 &
echo \"Connector started (PID \$!)\"
"

echo "Done. Logs: ssh root@$HOST tail -f /data/connector.log"
