#!/bin/sh
# Manage the SiLA2 OT-2 connector service.
# Usage: ssh root@<host> "sh /data/start_connector.sh [start|stop|restart|status]"
# Default action is restart.
#
# The systemd service (installed by install_connector_service.sh) runs the connector
# binary directly. This script is the manual management helper: it kills any rogue
# connector processes not tracked by systemd before delegating to systemctl.
set -e

ACTION="${1:-restart}"

# Kill any connector process running outside of systemd (e.g. from a previous crashed
# or manually started run) so GPIO lines are freed before systemctl takes over.
pkill -f 'connector start' 2>/dev/null || true

systemctl reset-failed sila2-connector 2>/dev/null || true
systemctl "$ACTION" sila2-connector
