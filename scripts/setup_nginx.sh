#!/bin/bash
# Setup nginx reverse proxy for Cybernetics Dashboard
# Proxies tonyler.is-not-a.dev/cyber -> localhost:5002

set -euo pipefail

DOMAIN="tonyler.is-not-a.dev"
UPSTREAM_PORT=5002
NGINX_CONF="/etc/nginx/sites-available/cyber-dashboard"
NGINX_ENABLED="/etc/nginx/sites-enabled/cyber-dashboard"

# Must run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./setup_nginx.sh)"
    exit 1
fi

echo "========================================"
echo "Nginx Setup for Cybernetics Dashboard"
echo "========================================"

# Install nginx if missing
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    apt update
    apt install -y nginx
fi

# Create nginx config
echo "Creating nginx config..."
cat > "$NGINX_CONF" << 'NGINX_EOF'
# Cybernetics Dashboard - reverse proxy config
# Handles /cyber path on tonyler.is-not-a.dev

server {
    listen 80;
    server_name tonyler.is-not-a.dev;

    # Cybernetics dashboard
    location /cyber {
        proxy_pass http://127.0.0.1:5002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /cyber/static {
        proxy_pass http://127.0.0.1:5002/static;
        proxy_set_header Host $host;
    }

    # Optional: redirect root to /cyber
    location = / {
        return 302 /cyber;
    }
}
NGINX_EOF

# Enable site
if [ ! -L "$NGINX_ENABLED" ]; then
    echo "Enabling site..."
    ln -sf "$NGINX_CONF" "$NGINX_ENABLED"
fi

# Remove default site if it conflicts
if [ -L "/etc/nginx/sites-enabled/default" ]; then
    echo "Removing default site..."
    rm -f /etc/nginx/sites-enabled/default
fi

# Test config
echo "Testing nginx config..."
nginx -t

# Reload nginx
echo "Reloading nginx..."
systemctl reload nginx

echo ""
echo "========================================"
echo "Nginx setup complete!"
echo "========================================"
echo "Dashboard URL: http://$DOMAIN/cyber"
echo ""
echo "For HTTPS, run:"
echo "  apt install certbot python3-certbot-nginx"
echo "  certbot --nginx -d $DOMAIN"
echo "========================================"
