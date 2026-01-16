#!/usr/bin/env bash
set -euo pipefail

# Cybernetics Dashboard Deployment Script
# Deploys dashboard3 to tonyler.is-not-a.dev

SERVER="root@37.27.15.9"
REMOTE_DIR="/opt/cyber-dashboard"
LOCAL_DIR="$(dirname "$0")/.."

echo "=== Cybernetics Dashboard Deployment ==="
echo "Server: $SERVER"
echo "Remote: $REMOTE_DIR"
echo ""

# Create remote directory
echo "[1/5] Creating remote directory..."
ssh "$SERVER" "mkdir -p $REMOTE_DIR"

# Sync project files (excluding unnecessary stuff)
echo "[2/5] Syncing files to server..."
rsync -avz --delete \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude 'venv' \
    --exclude 'register' \
    --exclude '*.log' \
    "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

# Copy .env if it exists locally
if [[ -f "$LOCAL_DIR/.env" ]]; then
    if ssh "$SERVER" "test -f $REMOTE_DIR/.env"; then
        echo "[3/5] .env already exists on server, skipping (delete remote .env to overwrite)"
    else
        echo "[3/5] Copying .env to server..."
        scp "$LOCAL_DIR/.env" "$SERVER:$REMOTE_DIR/.env"
    fi
else
    echo "[3/5] WARNING: No local .env file! Create one on server at $REMOTE_DIR/.env"
fi

# Install dependencies and setup on server
echo "[4/5] Setting up venv and installing dependencies..."
ssh "$SERVER" "cd $REMOTE_DIR && \
    python3 -m venv venv && \
    ./venv/bin/pip install -r requirements.txt --quiet"

# Copy and enable systemd service
echo "[5/5] Setting up systemd service..."
ssh "$SERVER" "cp $REMOTE_DIR/deploy/cyber-dashboard.service /etc/systemd/system/ && \
    systemctl daemon-reload && \
    systemctl enable cyber-dashboard && \
    systemctl restart cyber-dashboard"

echo ""
echo "=== Deployment Complete ==="
echo "Dashboard running at: https://tonyler.is-not-a.dev"
echo ""
echo "Useful commands:"
echo "  ssh $SERVER 'systemctl status cyber-dashboard'"
echo "  ssh $SERVER 'journalctl -u cyber-dashboard -f'"
