#!/bin/bash
# Deploy and run OT-2 SiLA2 Connector on robot
# Usage: ./deploy.sh [hostname] [--simulate] [--no-run] [--cleanup]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist_minimal"
TARBALL="$SCRIPT_DIR/ot2_connector.tar.gz"
HOST="${1:-ot2cep20240218r04.local}"
REMOTE_DIR="~/ot2_sila2"
SIMULATE=""
NO_RUN=""
CLEANUP=""

# Parse args
for arg in "$@"; do
    case $arg in
        --simulate) SIMULATE="--simulate" ;;
        --no-run) NO_RUN="true" ;;
        --cleanup) CLEANUP="true" ;;
        --*) ;;
        *) HOST="$arg" ;;
    esac
done

# Cleanup function
cleanup_remote() {
    echo ""
    echo "=== Cleaning up remote ==="
    ssh "root@$HOST" "pkill -f ot2_connector.py 2>/dev/null || true"
    ssh "root@$HOST" "rm -rf $REMOTE_DIR"
    echo "Removed $REMOTE_DIR from $HOST"
}

# If --cleanup flag, just cleanup and exit
if [ -n "$CLEANUP" ]; then
    cleanup_remote
    exit 0
fi

echo "=== OT-2 SiLA2 Connector Deploy ==="
echo "Host: $HOST"
echo "Source: $DIST_DIR"
[ -n "$SIMULATE" ] && echo "Mode: Simulator"

# Create tarball
echo ""
echo "Creating distribution tarball..."
cd "$DIST_DIR"
tar czf "$TARBALL" ot2_connector.py requirements.txt
echo "Created: $TARBALL ($(du -h "$TARBALL" | cut -f1))"

# Test SSH connection
echo ""
echo "Testing SSH connection..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "root@$HOST" "echo ok" 2>/dev/null; then
    echo "ERROR: Cannot connect to root@$HOST"
    echo "Make sure the OT-2 is powered on and connected to the network."
    exit 1
fi

# Transfer using cat (scp not available on OT-2)
echo ""
echo "Transferring to $HOST..."
cat "$TARBALL" | ssh "root@$HOST" "mkdir -p $REMOTE_DIR && cat > $REMOTE_DIR/ot2_connector.tar.gz"

# Extract on remote
echo "Extracting on remote..."
ssh "root@$HOST" "cd $REMOTE_DIR && tar xzf ot2_connector.tar.gz && rm ot2_connector.tar.gz"

# Check if pip/python available and install deps
echo ""
echo "Checking Python environment..."
ssh "root@$HOST" "cd $REMOTE_DIR && python3 --version"

echo ""
echo "Creating virtual environment..."
ssh "root@$HOST" "cd $REMOTE_DIR && python3 -m venv .venv"

echo ""
echo "Installing dependencies (this may take a while)..."
ssh "root@$HOST" "cd $REMOTE_DIR && .venv/bin/pip install -r requirements.txt" || {
    echo "WARNING: pip install failed. Dependencies may need manual installation."
}

# Verify deployment
echo ""
echo "Verifying deployment..."
ssh "root@$HOST" "ls -la $REMOTE_DIR/"

# Cleanup local tarball
rm -f "$TARBALL"

echo ""
echo "=== Deployment complete ==="

# Run connector unless --no-run specified
if [ -z "$NO_RUN" ]; then
    echo ""
    echo "Starting connector on $HOST in background..."
    ssh "root@$HOST" "cd $REMOTE_DIR && nohup .venv/bin/python ot2_connector.py $SIMULATE > connector.log 2>&1 &"
    sleep 2

    # Check if running
    if ssh "root@$HOST" "pgrep -f ot2_connector.py" > /dev/null; then
        echo "Connector started successfully (PID: $(ssh "root@$HOST" "pgrep -f ot2_connector.py"))"
        echo "Logs: ssh root@$HOST 'tail -f $REMOTE_DIR/connector.log'"
        echo ""
        echo "SiLA2 server running at $HOST:50052"
        echo ""
        echo "Press Enter to stop and cleanup, or Ctrl+C to leave running..."
        read -r
        cleanup_remote
    else
        echo "ERROR: Connector failed to start"
        echo "Check logs: ssh root@$HOST 'cat $REMOTE_DIR/connector.log'"
        cleanup_remote
        exit 1
    fi
else
    echo ""
    echo "To run the connector manually:"
    echo "  ssh root@$HOST"
    echo "  cd $REMOTE_DIR"
    echo "  .venv/bin/python ot2_connector.py $SIMULATE"
    echo ""
    echo "To cleanup: ./deploy.sh $HOST --cleanup"
fi
