#!/bin/sh
set -e
cd "$(dirname "$0")"

VENV_PATH="${1:-/var/sila2_ot2}"
CONFIG_DEST="$VENV_PATH/config.json"

echo "Installing to $VENV_PATH..."
# --system-site-packages exposes robot_server (an OT-2 system package, not on PyPI)
# and its deps (uvicorn, wsproto, etc.) to the venv. Our bundled wheels are installed
# on top and take precedence over system packages where versions differ.
python3 -m venv --system-site-packages "$VENV_PATH"
# --root / overrides /etc/pip.conf's "root = /var/user-packages" (which would
# otherwise redirect installs away from the venv's own site-packages)
"$VENV_PATH/bin/pip" install --root / --no-index --no-deps *.whl

if [ -f ot2_config.local.json ]; then
    cp ot2_config.local.json "$CONFIG_DEST"
    echo "Config installed to $CONFIG_DEST (from local override)"
elif [ -f ot2_config.json ]; then
    cp ot2_config.json "$CONFIG_DEST"
    echo "Config installed to $CONFIG_DEST"
fi

echo "Done. Run with: $VENV_PATH/bin/python -m unitelabs.opentrons_ot2 --config-path $CONFIG_DEST"
