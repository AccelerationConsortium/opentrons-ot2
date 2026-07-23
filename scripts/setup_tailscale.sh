#!/bin/sh
# One-time Tailscale provisioning for a brand-new OT-2 (or identical machine).
# Already-provisioned robots don't need this — see scripts/README.md.
# Usage: TS_AUTHKEY=tskey-auth-... ./scripts/setup_tailscale.sh <host>
set -e

HOST="${1:?Usage: TS_AUTHKEY=<key> $0 <host>}"
: "${TS_AUTHKEY:?TS_AUTHKEY environment variable must be set}"

TAILSCALE_VERSION="1.82.0"
TARBALL="tailscale_${TAILSCALE_VERSION}_arm.tgz"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$SCRIPT_DIR/$TARBALL" ]; then
    echo "Downloading $TARBALL ..."
    curl -L -o "$SCRIPT_DIR/$TARBALL" "https://pkgs.tailscale.com/stable/$TARBALL"
fi

echo "Uploading and extracting Tailscale binary on $HOST ..."
ssh "root@$HOST" 'mount -o remount,rw /'
scp -O "$SCRIPT_DIR/$TARBALL" "root@$HOST:/data/"
ssh "root@$HOST" "cd /data && tar xzf $TARBALL"

echo "Writing auth key ..."
printf '%s' "$TS_AUTHKEY" | ssh "root@$HOST" 'cat > /data/tskey.txt && chmod 600 /data/tskey.txt'

echo "Installing Tailscale systemd service ..."
sh "$SCRIPT_DIR/install_tailscale_service.sh" "$HOST"

echo "Verifying ..."
ssh "root@$HOST" "/data/tailscale_${TAILSCALE_VERSION}_arm/tailscale status"
