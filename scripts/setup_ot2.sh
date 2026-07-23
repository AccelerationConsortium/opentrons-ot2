#!/bin/sh
# Deploy the latest successful "main" build to the OT-2.
# Checks the robot's architecture and Python version before doing anything else,
# so an incompatible wheel set is never pushed. Downloads wheels from the rolling
# "ot2-latest" GitHub Release (published by .github/workflows/build-ot2-arm-wheels.yml
# on every push to main) via plain curl -- no gh CLI or auth token required.
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
echo "=== Downloading wheels from latest main build ==="
rm -rf "$SCRIPT_DIR/dist_arm"
mkdir -p "$SCRIPT_DIR/dist_arm"
ZIP="/tmp/${ARTIFACT}.zip"
if ! curl -sL --fail "https://github.com/$REPO/releases/download/ot2-latest/${ARTIFACT}.zip" -o "$ZIP"; then
    echo "ERROR: could not download $ARTIFACT.zip from the 'ot2-latest' release."
    echo "Has the 'Build OT-2 ARM Wheels' workflow finished on main yet? Check:"
    echo "  https://github.com/$REPO/releases/tag/ot2-latest"
    exit 1
fi
unzip -q -o "$ZIP" -d "$SCRIPT_DIR/dist_arm"
rm -f "$ZIP"
ls "$SCRIPT_DIR"/dist_arm/unitelabs_opentrons_ot2*.whl

echo ""
echo "=== Deploying ==="
sh "$SCRIPT_DIR/deploy.sh" "$HOST" dist_arm
sh "$SCRIPT_DIR/scripts/install_connector_service.sh" "$HOST"

echo ""
echo "=== Verifying ==="
sh "$SCRIPT_DIR/scripts/verify_ot2.sh" "$HOST"
