#!/bin/sh
# Deploy the latest successful "main" build to the OT-2 as a self-contained binary --
# no venv, no pip, no Python required on the robot at all.
# Checks the robot's architecture and Python version before doing anything else, so an
# incompatible build is never pushed (the OT-2 generation determines which of the two
# binary variants applies -- see Dockerfile.build vs Dockerfile.build.py312).
# Downloads from the rolling "ot2-latest" GitHub Release (published by
# .github/workflows/build-ot2-arm-wheels.yml on every push to main) via plain curl --
# no gh CLI or auth token required.
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
    3.10) ARTIFACT="ot2-connector-arm-py310" ;;
    3.12) ARTIFACT="ot2-connector-arm-py312" ;;
    *)
        echo "ERROR: unsupported robot Python '$PYVER' (expected 3.10 or 3.12). Refusing to deploy."
        exit 1
        ;;
esac
echo "Robot: arch=$ARCH python=$PYVER -> $ARTIFACT"

echo ""
echo "=== Downloading connector binary from latest main build ==="
rm -rf "$SCRIPT_DIR/dist_connector"
mkdir -p "$SCRIPT_DIR/dist_connector"
TARBALL="/tmp/${ARTIFACT}.tar.gz"
if ! curl -sL --fail "https://github.com/$REPO/releases/download/ot2-latest/${ARTIFACT}.tar.gz" -o "$TARBALL"; then
    echo "ERROR: could not download $ARTIFACT.tar.gz from the 'ot2-latest' release."
    echo "Has the 'Build OT-2 ARM Wheels' workflow finished on main yet? Check:"
    echo "  https://github.com/$REPO/releases/tag/ot2-latest"
    exit 1
fi
tar xzf "$TARBALL" -C "$SCRIPT_DIR/dist_connector"
rm -f "$TARBALL"
ls "$SCRIPT_DIR/dist_connector/connector"

echo ""
echo "=== Deploying ==="
sh "$SCRIPT_DIR/deploy_executable.sh" "$HOST" dist_connector
sh "$SCRIPT_DIR/scripts/install_connector_service.sh" "$HOST"

echo ""
echo "=== Verifying ==="
sh "$SCRIPT_DIR/scripts/verify_ot2.sh" "$HOST"
