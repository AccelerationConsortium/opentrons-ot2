#!/bin/sh
# Deploy the latest successful "main" build to the OT-2.
# Checks the robot's architecture and Python version before doing anything else,
# so an incompatible wheel set is never pushed.
#
# Usage: ./scripts/setup_ot2.sh <host>
set -e

HOST="${1:?Usage: $0 <host>}"
REPO="AccelerationConsortium/opentrons-ot2"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Checking robot compatibility: $HOST ==="
ARCH="$(ssh "root@$HOST" "uname -m")"
PYVER="$(ssh "root@$HOST" "python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")'")"

if [ "$ARCH" != "armv7l" ]; then
    echo "ERROR: unsupported architecture '$ARCH' (expected armv7l). Refusing to deploy."
    exit 1
fi

case "$PYVER" in
    3.10) ARTIFACT="ot2-arm-wheels-py310" ;;
    3.12) ARTIFACT="ot2-arm-wheels-py312" ;;
    *)
        echo "ERROR: unsupported robot Python '$PYVER' (expected 3.10 or 3.12). Refusing to deploy."
        exit 1
        ;;
esac
echo "Robot: arch=$ARCH python=$PYVER -> $ARTIFACT"

echo ""
echo "=== Finding latest successful ARM wheel build on main ==="
RUN_ID="$(gh run list --repo "$REPO" --workflow build-ot2-arm-wheels.yml --branch main --status success --limit 1 --json databaseId -q '.[0].databaseId')"
if [ -z "$RUN_ID" ]; then
    echo "ERROR: no successful 'Build OT-2 ARM Wheels' run found on main."
    exit 1
fi
echo "Using run $RUN_ID"

echo ""
echo "=== Downloading wheels ==="
rm -rf "$SCRIPT_DIR/dist_arm"
gh run download "$RUN_ID" --repo "$REPO" --name "$ARTIFACT" --dir "$SCRIPT_DIR/dist_arm"
ls "$SCRIPT_DIR"/dist_arm/unitelabs_opentrons_ot2*.whl

echo ""
echo "=== Deploying ==="
sh "$SCRIPT_DIR/deploy.sh" "$HOST" dist_arm
sh "$SCRIPT_DIR/scripts/install_connector_service.sh" "$HOST"

echo ""
echo "=== Verifying ==="
sh "$SCRIPT_DIR/scripts/verify_ot2.sh" "$HOST"
