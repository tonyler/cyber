#!/usr/bin/env bash
set -euo pipefail

# Cybernetics Dashboard Deployment Script
# Deploys entire /cyber dir to tonyler.is-not-a.dev/cyber

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_DIR="$(dirname "$SCRIPT_DIR")"
REMOTE_DIR="/opt/cyber-dashboard"

# Load credentials
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    source "$SCRIPT_DIR/.env"
else
    echo "ERROR: $SCRIPT_DIR/.env not found!"
    exit 1
fi

SERVER="${HETZNER_USER}@${HETZNER_HOST}"
export SSHPASS="$HETZNER_PASS"

echo "=== Cybernetics Dashboard Deployment ==="
echo "Server: $SERVER"
echo "Remote: $REMOTE_DIR"
echo ""

# Check sshpass is installed
if ! command -v sshpass &> /dev/null; then
    echo "Installing sshpass..."
    sudo apt install -y sshpass
fi

# Create remote directory
echo "[1/4] Creating remote directory..."
sshpass -e ssh -o StrictHostKeyChecking=no "$SERVER" "mkdir -p $REMOTE_DIR"

# Sync ALL project files (only exclude pycache, venv, .git, register)
echo "[2/4] Syncing all files to server (including .env and credentials)..."
sshpass -e rsync -avz --delete \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'venv' \
    --exclude '.git' \
    --exclude 'register' \
    --exclude 'deploy' \
    -e "ssh -o StrictHostKeyChecking=no" \
    "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

# Also copy deploy folder (for service file)
sshpass -e rsync -avz \
    --exclude '__pycache__' \
    --exclude '.env' \
    -e "ssh -o StrictHostKeyChecking=no" \
    "$SCRIPT_DIR/" "$SERVER:$REMOTE_DIR/deploy/"

# Install dependencies in venv
echo "[3/4] Setting up venv and installing dependencies..."
sshpass -e ssh -o StrictHostKeyChecking=no "$SERVER" "cd $REMOTE_DIR && \
    python3 -m venv venv && \
    ./venv/bin/pip install --upgrade pip --quiet && \
    ./venv/bin/pip install -r requirements.txt --quiet"

# Setup and restart systemd service
echo "[4/4] Setting up systemd service..."
sshpass -e ssh -o StrictHostKeyChecking=no "$SERVER" "
    cp $REMOTE_DIR/deploy/cyber-dashboard.service /etc/systemd/system/ && \
    systemctl daemon-reload && \
    systemctl enable cyber-dashboard && \
    systemctl restart cyber-dashboard"

echo ""
echo "=== Deployment Complete ==="
echo "Dashboard: https://tonyler.is-not-a.dev/cyber"
echo ""
echo "Useful commands:"
echo "  sshpass -e ssh $SERVER 'systemctl status cyber-dashboard'"
echo "  sshpass -e ssh $SERVER 'journalctl -u cyber-dashboard -f'"
