#!/usr/bin/env bash
set -euo pipefail

# One-time server setup script
# Run this ONCE on a fresh server before first deploy

echo "=== Cybernetics Dashboard - Server Setup ==="

# Install required packages
echo "[1/5] Installing system packages..."
apt update
apt install -y python3 python3-pip nginx certbot python3-certbot-nginx

# Create project directory
echo "[2/5] Creating project directory..."
mkdir -p /opt/cyber-dashboard

# Setup firewall (if ufw is available)
echo "[3/5] Configuring firewall..."
if command -v ufw &> /dev/null; then
    ufw allow 'Nginx Full'
    ufw allow ssh
    ufw --force enable
fi

# Get SSL certificate
echo "[4/5] Getting SSL certificate..."
certbot --nginx -d tonyler.is-not-a.dev --non-interactive --agree-tos --email tonyler@pm.me || \
    echo "Certbot failed - you may need to run manually: certbot --nginx -d tonyler.is-not-a.dev"

echo "[5/5] Setup complete!"
echo ""
echo "Next steps:"
echo "1. Run deploy.sh from your local machine"
echo "2. Copy nginx config: cp /opt/cyber-dashboard/deploy/nginx-cyber.conf /etc/nginx/sites-available/cyber-dashboard"
echo "3. Enable nginx site: ln -s /etc/nginx/sites-available/cyber-dashboard /etc/nginx/sites-enabled/"
echo "4. Test and reload: nginx -t && systemctl reload nginx"
