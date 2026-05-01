#!/bin/sh
# Usage: ./scripts/install_tailscale_service.sh <host>
# Example: ./scripts/install_tailscale_service.sh 192.168.1.19
set -e

HOST="${1:?Usage: $0 <host>}"

ssh "root@${HOST}" '
set -e
mount -o remount,rw /

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
systemctl start start-tailscale
systemctl status start-tailscale --no-pager
'
