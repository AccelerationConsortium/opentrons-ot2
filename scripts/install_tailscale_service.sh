#!/bin/sh
# Install and start the Tailscale systemd service on the OT-2.
# Assumes the Tailscale binary and auth key are already on the robot at /data
# (run ./scripts/setup_tailscale.sh first to provision a brand-new robot).
# Usage: ./scripts/install_tailscale_service.sh <host>
set -e

HOST="${1:?Usage: $0 <host>}"
SCRIPT_DIR="$(dirname "$0")"

echo "Copying start_tailscale.sh to robot..."
scp -O "$SCRIPT_DIR/start_tailscale.sh" "root@$HOST:/data/start_tailscale.sh"

ssh "root@${HOST}" '
set -e
mount -o remount,rw /
chmod +x /data/start_tailscale.sh

cat > /etc/systemd/system/start-tailscale.service << EOF
[Unit]
Description=Start Tailscale
After=network.target

[Service]
Type=oneshot
ExecStart=/bin/sh /data/start_tailscale.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable start-tailscale
systemctl restart start-tailscale
systemctl status start-tailscale --no-pager
'
