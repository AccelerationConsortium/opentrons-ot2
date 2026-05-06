#!/bin/sh
set -e
cd "$(dirname "$0")"

VENV_PATH="${1:-/var/sila2_ot2}"
CONFIG_DEST="$VENV_PATH/config.json"

echo "Installing to $VENV_PATH..."
python3 -m venv --system-site-packages "$VENV_PATH"
# --root / overrides /etc/pip.conf's "root = /var/user-packages" (which would
# otherwise redirect installs away from the venv's own site-packages)
"$VENV_PATH/bin/pip" install --root / --no-index --no-deps *.whl

if [ -f ot2_config.json ]; then
    cp ot2_config.json "$CONFIG_DEST"
    echo "Config installed to $CONFIG_DEST"
fi

echo "Done. Run with: $VENV_PATH/bin/python -m unitelabs.opentrons_ot2 --config-path $CONFIG_DEST"
