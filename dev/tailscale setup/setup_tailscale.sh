#!/bin/sh
# Usage: TS_AUTHKEY=tskey-auth-... ./setup_tailscale.sh <host>
# Installs Tailscale on a new OT-2 (or identical machine) via SSH.
# Requires root SSH access and TS_AUTHKEY set in the environment.
# Override the default SSH key with SSH_KEY=/path/to/key.
set -e

HOST="${1:?Usage: TS_AUTHKEY=<key> $0 <host>}"
: "${TS_AUTHKEY:?TS_AUTHKEY environment variable must be set}"

TAILSCALE_VERSION="1.82.0"
TARBALL="tailscale_${TAILSCALE_VERSION}_arm.tgz"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/ot2_ssh_key}"

ssh_cmd() { ssh -i "$SSH_KEY" "root@${HOST}" "$@"; }
scp_cmd() { scp -O -i "$SSH_KEY" "$1" "root@${HOST}:$2"; }

# ── Step 0: fetch binary if not present ───────────────────────────────────────

if [ ! -f "$SCRIPT_DIR/$TARBALL" ]; then
    echo "Downloading $TARBALL ..."
    curl -L -o "$SCRIPT_DIR/$TARBALL" \
        "https://pkgs.tailscale.com/stable/$TARBALL"
fi

# ── Step 1: unlock read-only root filesystem ──────────────────────────────────

echo "Remounting / read-write on $HOST ..."
ssh_cmd 'mount -o remount,rw /'

# ── Step 2: upload and extract tailscale binary ───────────────────────────────

echo "Uploading $TARBALL ..."
scp_cmd "$SCRIPT_DIR/$TARBALL" /data/
ssh_cmd "cd /data && tar xzf $TARBALL"

# ── Step 3: write auth key ────────────────────────────────────────────────────

echo "Writing auth key to /data/tskey.txt ..."
printf '%s' "$TS_AUTHKEY" | ssh -i "$SSH_KEY" "root@${HOST}" 'cat > /data/tskey.txt && chmod 600 /data/tskey.txt'

# ── Step 4: upload start script ───────────────────────────────────────────────

echo "Uploading start_tailscale.sh ..."
scp_cmd "$REPO_ROOT/scripts/start_tailscale.sh" /data/start_tailscale.sh
ssh_cmd 'chmod +x /data/start_tailscale.sh'

# ── Step 5: install systemd service ───────────────────────────────────────────

echo "Installing start-tailscale systemd service ..."
ssh_cmd '
set -e
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

# ── Step 6: verify ────────────────────────────────────────────────────────────

echo "Verifying Tailscale status ..."
ssh_cmd "/data/tailscale_${TAILSCALE_VERSION}_arm/tailscale status"
