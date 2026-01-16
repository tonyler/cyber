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

# Sync project files (excluding unnecessary stuff)
echo "[1/4] Syncing files to server..."
rsync -avz --delete \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude 'venv' \
    --exclude 'deploy' \
    --exclude '*.log' \
    "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

# Copy .env if it exists locally (won't overwrite if exists remotely)
if [[ -f "$LOCAL_DIR/.env" ]]; then
    echo "[2/4] Copying .env (if not exists on server)..."
    ssh "$SERVER" "test -f $REMOTE_DIR/.env || echo 'needs_env'" | grep -q 'needs_env' && \
        scp "$LOCAL_DIR/.env" "$SERVER:$REMOTE_DIR/.env" || \
        echo "  .env already exists on server, skipping"
else
    echo "[2/4] No local .env, skipping..."
fi

# Install dependencies and setup on server
echo "[3/4] Installing dependencies on server..."
ssh "$SERVER" "cd $REMOTE_DIR && pip3 install -r requirements.txt --quiet"

# Copy and enable systemd service
echo "[4/4] Setting up systemd service..."
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
