#!/bin/sh
# Deploy the SiLA2 OT-2 connector to the robot.
#
# Usage:
#   ./deploy.sh [hostname] [wheel_dir]
#
# Arguments:
#   hostname   Robot hostname or IP (default: ot2cep20240218r04)
#   wheel_dir  Local directory containing built ARM wheels (default: dist_arm)
#
# The wheel directory must contain the output of the "Build OT-2 ARM Wheels"
# GitHub Actions workflow. Download the ot2-arm-wheels artifact and unzip it
# into dist_arm/ before running this script.

set -e

HOST="${1:-ot2cep20240218r04}"
WHEEL_DIR="${2:-dist_arm}"
VENV_PATH="/var/sila2_ot2"
REMOTE_DIR="/root/dist_arm"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$SCRIPT_DIR/config/ot2_config.local.json" ]; then
    CONFIG_SRC="$SCRIPT_DIR/config/ot2_config.local.json"
    echo "Config: config/ot2_config.local.json (local override)"
else
    CONFIG_SRC="$SCRIPT_DIR/config/ot2_config.json"
fi

if [ ! -d "$SCRIPT_DIR/$WHEEL_DIR" ]; then
    echo "ERROR: Wheel directory '$WHEEL_DIR' not found."
    echo "Download the ot2-arm-wheels artifact from GitHub Actions and unzip into dist_arm/."
    exit 1
fi

echo "=== OT-2 SiLA2 Connector Deploy ==="
echo "Host:      $HOST"
echo "Wheels:    $WHEEL_DIR"
echo "Venv:      $VENV_PATH"

echo ""
echo "Copying wheels and scripts to $HOST:$REMOTE_DIR ..."
ssh "root@$HOST" "rm -rf $REMOTE_DIR && mkdir -p $REMOTE_DIR"
scp -O "$SCRIPT_DIR/scripts/install.sh" "$SCRIPT_DIR/$WHEEL_DIR"/*.whl "root@$HOST:$REMOTE_DIR/"
scp -O "$SCRIPT_DIR/$CONFIG_SRC" "root@$HOST:$REMOTE_DIR/ot2_config.json"

echo ""
echo "Installing on robot ..."
ssh "root@$HOST" "rm -rf $VENV_PATH /var/user-packages/var/sila2_ot2 && sh $REMOTE_DIR/install.sh $VENV_PATH"

echo ""
echo "Precompiling system site-packages bytecode into /var/cache/sila2-pycache ..."
ssh "root@$HOST" "mkdir -p /var/cache/sila2-pycache && PYTHONPYCACHEPREFIX=/var/cache/sila2-pycache python3 -m compileall -q /usr/lib/python3.12/site-packages/ 2>/dev/null; true"

echo ""
echo "Verifying ..."
ssh "root@$HOST" "$VENV_PATH/bin/python -c 'import grpc, unitelabs.opentrons_ot2; print(\"OK grpc=\"+grpc.__version__)'"

echo ""
echo "=== Deploy complete ==="
echo "Start with:"
echo "  ssh root@$HOST \"nohup $VENV_PATH/bin/connector start --app unitelabs.opentrons_ot2:create_app --config-path $VENV_PATH/config.json > /var/log/sila2_ot2.log 2>&1 &\""
