#!/bin/sh
# Deploy the self-contained connector binary to the OT-2.
# Does not require pip, a venv, or any Python on the robot.
#
# Usage:
#   ./deploy_executable.sh [hostname] [connector_dir]
#
# Arguments:
#   hostname       Robot hostname or IP (default: ot2cep20240218r04)
#   connector_dir  Local directory containing the connector binary and config
#                  (default: dist_connector). Must contain:
#                    - connector  (the PyInstaller binary)
#                    - ot2_config.json
#
# Download the ot2-connector-arm artifact from GitHub Actions and unzip into
# dist_connector/ before running this script.
set -e

HOST="${1:-ot2cep20240218r04}"
CONNECTOR_DIR="${2:-dist_connector}"
INSTALL_PATH="/var/sila2_ot2"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$SCRIPT_DIR/$CONNECTOR_DIR/connector" ]; then
    echo "ERROR: connector binary not found in '$CONNECTOR_DIR/'."
    echo "Download the ot2-connector-arm artifact from GitHub Actions and unzip into dist_connector/."
    exit 1
fi

echo "=== OT-2 SiLA2 Connector Deploy (executable) ==="
echo "Host:      $HOST"
echo "Binary:    $CONNECTOR_DIR/connector"
echo "Install:   $INSTALL_PATH/connector"

echo ""
echo "Copying connector binary to $HOST ..."
ssh "root@$HOST" "mount -o remount,rw / && mkdir -p $INSTALL_PATH"
scp -O "$SCRIPT_DIR/$CONNECTOR_DIR/connector" "root@$HOST:$INSTALL_PATH/connector"
if [ -f "$SCRIPT_DIR/config/ot2_config.local.json" ]; then
    CONFIG_FILE="$SCRIPT_DIR/config/ot2_config.local.json"
    echo "Config: config/ot2_config.local.json (local override)"
else
    CONFIG_FILE="$SCRIPT_DIR/$CONNECTOR_DIR/ot2_config.json"
fi
scp -O "$CONFIG_FILE" "root@$HOST:$INSTALL_PATH/config.json"
ssh "root@$HOST" "chmod +x $INSTALL_PATH/connector"

echo ""
echo "Verifying ..."
ssh "root@$HOST" "$INSTALL_PATH/connector --help"

echo ""
echo "=== Deploy complete ==="
echo "Install the service with:"
echo "  sh scripts/install_connector_service.sh $HOST"
