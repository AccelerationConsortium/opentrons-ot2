#!/bin/sh
# Start the SiLA2 OT-2 connector on the robot.
# Usage: ssh root@<host> "sh /root/start_connector.sh"
# Or deploy this file to the robot and run it directly.
set -e

VENV=/var/sila2_ot2
CONFIG=$VENV/config.json

exec env \
    PYTHONUNBUFFERED=1 \
    RUNNING_ON_PI=true \
    OT_SMOOTHIE_ID=AMA \
    "$VENV/bin/connector" start \
    --app unitelabs.opentrons_ot2:create_app \
    --config-path "$CONFIG"
