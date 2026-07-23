#!/bin/sh
# Install the SiLA2 connector as a systemd service on the OT-2.
# Disables the Opentrons robot server first so we get exclusive hardware access.
# Usage: ./scripts/install_connector_service.sh <host>
set -e

HOST="${1:?Usage: $0 <host>}"
SCRIPT_DIR="$(dirname "$0")"

echo "Copying start_connector.sh to robot..."
scp -O "$SCRIPT_DIR/start_connector.sh" "root@$HOST:/data/start_connector.sh"

ssh "root@${HOST}" '
set -e
mount -o remount,rw /

echo "Disabling opentrons services that hold GPIO lines..."
for svc in opentrons-robot-server opentrons-status-leds opentrons-gpio-setup; do
    systemctl disable "$svc" || true
    systemctl stop "$svc" || true
done

echo "Installing sila2-connector service..."
cat > /etc/systemd/system/sila2-connector.service << EOF
[Unit]
Description=SiLA2 OT-2 Connector
After=network.target opentrons-init-connections.service
Wants=opentrons-init-connections.service

[Service]
Type=simple
# TMPDIR: PyInstaller onefile mode extracts the whole bundle here on every start.
# /tmp is a small RAM-backed tmpfs (about 450M on this hardware) -- too small for
# this bundle (robot_server plus its full dep set) and shared with anything else
# that uses /tmp. /var/sila2_ot2/tmp is on real storage with room to spare.
ExecStartPre=/bin/mkdir -p /var/sila2_ot2/tmp
ExecStart=/var/sila2_ot2/connector start --app unitelabs.opentrons_ot2:create_app --config-path /var/sila2_ot2/config.json
Environment=RUNNING_ON_PI=true
Environment=OT_SMOOTHIE_ID=AMA
Environment=TMPDIR=/var/sila2_ot2/tmp
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable sila2-connector
systemctl restart sila2-connector
systemctl status sila2-connector --no-pager
'
