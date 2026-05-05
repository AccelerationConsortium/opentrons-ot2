#!/bin/sh
# Manage the SiLA2 OT-2 connector service.
# Usage: ssh root@<host> "sh /data/start_connector.sh [start|stop|restart|status]"
# Default action is restart.
set -e

ACTION="${1:-restart}"

systemctl "$ACTION" sila2-connector
