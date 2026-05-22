#!/bin/sh
# Usage: install.sh [venv_path] [--system-site-packages]
#
# --system-site-packages: pass through to python -m venv. Use for py312 robots
#   where opentrons, numpy, gpiod, etc. are inherited from the system Python.
set -e
cd "$(dirname "$0")"

VENV_PATH="${1:-/var/sila2_ot2}"
CONFIG_DEST="$VENV_PATH/config.json"
VENV_OPTS=""

if [ "$2" = "--system-site-packages" ]; then
    VENV_OPTS="--system-site-packages"
fi

echo "Installing to $VENV_PATH ($VENV_OPTS)..."
python3 -m venv $VENV_OPTS "$VENV_PATH"
# --root / overrides /etc/pip.conf's "root = /var/user-packages" (which would
# otherwise redirect installs away from the venv's own site-packages)
"$VENV_PATH/bin/pip" install --root / --no-index --no-deps *.whl

if [ -f ot2_config.json ]; then
    cp ot2_config.json "$CONFIG_DEST"
    echo "Config installed to $CONFIG_DEST"
fi

echo "Done. Run with: $VENV_PATH/bin/python -m unitelabs.opentrons_ot2 --config-path $CONFIG_DEST"
