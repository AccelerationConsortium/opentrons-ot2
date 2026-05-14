#!/bin/sh
# Switch the OT-2 between Opentrons robot server and the SiLA2 connector.
# Stops the current mode first to release GPIO lines and the serial port
# (/dev/ttyAMA0 to the Smoothie motion controller), then starts the target.
#
# Usage: sh scripts/switch_mode.sh <host> <connector|opentrons>
set -e

HOST="${1:?Usage: $0 <host> <connector|opentrons>}"
MODE="${2:?Usage: $0 <host> <connector|opentrons>}"

case "$MODE" in
    connector|opentrons) ;;
    *) echo "ERROR: mode must be 'connector' or 'opentrons'"; exit 1 ;;
esac

ssh "root@${HOST}" sh << EOF
set -e

if systemctl is-active --quiet sila2-connector 2>/dev/null; then
    CURRENT=connector
elif systemctl is-active --quiet opentrons-robot-server 2>/dev/null; then
    CURRENT=opentrons
else
    CURRENT=none
fi

echo "Current: \$CURRENT  ->  Target: $MODE"

if [ "\$CURRENT" = "$MODE" ]; then
    echo "Already in $MODE mode."
    exit 0
fi

# Stop current mode first — GPIO lines and /dev/ttyAMA0 must be free before starting the next.
echo ""
echo "Stopping \$CURRENT..."
case "\$CURRENT" in
    connector)
        systemctl stop sila2-connector
        ;;
    opentrons)
        systemctl stop opentrons-robot-server || true
        systemctl stop opentrons-status-leds  || true
        systemctl stop opentrons-gpio-setup   || true
        ;;
esac

# Verify /dev/ttyAMA0 is free before proceeding.
# Checks /proc/*/fd rather than trying to open the port — serial ports on Linux
# do not use mandatory locking, so a successful open does not mean the port is free.
i=15
while ! python3 -c "
import os, sys
target = os.path.realpath('/dev/ttyAMA0')
for pid in os.listdir('/proc'):
    if not pid.isdigit():
        continue
    try:
        for fd in os.listdir('/proc/' + pid + '/fd'):
            if os.path.realpath('/proc/' + pid + '/fd/' + fd) == target:
                sys.exit(1)
    except (PermissionError, FileNotFoundError):
        pass
sys.exit(0)
" 2>/dev/null; do
    i=\$((i - 1))
    if [ \$i -le 0 ]; then
        echo "ERROR: /dev/ttyAMA0 still held after stop — cannot start next service"
        exit 1
    fi
    sleep 1
done
echo "Stopped. Serial port free."

# Start target mode and verify.
echo ""
echo "Starting $MODE..."
case "$MODE" in
    connector)
        systemctl reset-failed sila2-connector 2>/dev/null || true
        systemctl start sila2-connector
        echo "Waiting for connector on port 50051 (up to 5 minutes on first start)..."
        i=300
        while ! python3 -c "
import socket
s = socket.socket()
s.settimeout(1)
s.connect(('127.0.0.1', 50051))
s.close()
" 2>/dev/null; do
            i=\$((i - 2))
            if [ \$i -le 0 ]; then
                echo "ERROR: timed out waiting for port 50051"
                systemctl status sila2-connector --no-pager
                exit 1
            fi
            printf '.'
            sleep 2
        done
        echo " up."
        echo ""
        systemctl status sila2-connector --no-pager
        ;;
    opentrons)
        systemctl start opentrons-gpio-setup   || true
        systemctl start opentrons-status-leds  || true
        systemctl start opentrons-robot-server
        echo "Waiting for opentrons-robot-server to become active..."
        i=120
        while ! systemctl is-active --quiet opentrons-robot-server 2>/dev/null; do
            i=\$((i - 2))
            if [ \$i -le 0 ]; then
                echo "ERROR: timed out waiting for opentrons-robot-server"
                systemctl status opentrons-robot-server --no-pager
                exit 1
            fi
            printf '.'
            sleep 2
        done
        echo " up."
        echo ""
        systemctl status opentrons-robot-server --no-pager
        ;;
esac
EOF
