#!/bin/sh
# Switch the OT-2 between two operating modes.
#
# Usage:
#   sh scripts/switch_mode.sh <host> <connector|opentrons>
#
# Modes
# -----
#   connector  (recommended)
#       Runs the SiLA2 connector, which owns the hardware exclusively.
#       The connector starts the opentrons HTTP robot-server IN-PROCESS,
#       sharing one HardwareControlAPI so there is no serial port conflict.
#       Both interfaces are available simultaneously after switching:
#         - SiLA2 gRPC:             port 50051
#         - opentrons HTTP API:     port 31950  (nginx -> /run/aiohttp.sock)
#       All standard opentrons HTTP endpoints (/health, /pipettes, /runs, etc.)
#       work exactly as they do under the original robot-server, because our
#       connector injects the shared hardware into the robot-server app state
#       before uvicorn starts.  The opentrons-robot-server systemd service is
#       intentionally disabled in this mode; the sila2-connector service owns
#       the hardware.
#
#   opentrons
#       Runs only the original opentrons-robot-server (standalone).
#       No SiLA2 interface is available.  Use this when you need direct access
#       via the Opentrons app or other opentrons-native tooling without the
#       SiLA2 layer.
#
# Persistence
# -----------
#   The switch enables/disables the relevant systemd units so the selected
#   mode survives a reboot.  The OT-2 root filesystem is read-only; this
#   script remounts it read-write before writing systemd enable/disable
#   symlinks (the same pattern used by install_connector_service.sh).
#
# Hardware ownership
# ------------------
#   Both modes need exclusive access to:
#     - /dev/ttyAMA0  (Smoothie motion controller)
#     - GPIO lines    (owned via opentrons-gpio-setup / opentrons-status-leds)
#   The script stops the current mode and waits for the serial port to be
#   released before starting the next one.

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

# Remount root read-write so systemd enable/disable can write symlinks.
mount -o remount,rw /

# Stop current mode first — GPIO lines and /dev/ttyAMA0 must be free before
# starting the next.
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

# Enable the target set and disable the outgoing set so the choice survives reboot.
echo ""
echo "Persisting mode selection..."
case "$MODE" in
    connector)
        systemctl enable sila2-connector
        for svc in opentrons-robot-server opentrons-status-leds opentrons-gpio-setup; do
            systemctl disable "\$svc" 2>/dev/null || true
        done
        ;;
    opentrons)
        systemctl disable sila2-connector 2>/dev/null || true
        for svc in opentrons-gpio-setup opentrons-status-leds opentrons-robot-server; do
            systemctl enable "\$svc" 2>/dev/null || true
        done
        ;;
esac

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
        echo "SiLA2 gRPC:         port 50051"
        echo "opentrons HTTP API: port 31950 (via nginx -> /run/aiohttp.sock)"
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
        echo "opentrons HTTP API: port 31950"
        echo ""
        systemctl status opentrons-robot-server --no-pager
        ;;
esac
EOF
