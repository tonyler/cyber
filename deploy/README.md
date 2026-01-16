# Cybernetics Dashboard Deployment

Deploy dashboard3 to **https://tonyler.is-not-a.dev/cyber**

## Files

| File | Purpose |
|------|---------|
| `deploy.sh` | Main deploy script - syncs code and restarts service |
| `setup-server.sh` | One-time server setup (run on fresh server) |
| `cyber-dashboard.service` | Systemd service for auto-start |
| `nginx-cyber.conf` | Nginx reverse proxy config |

## Quick Deploy

```bash
./deploy.sh
```

## First-Time Server Setup

SSH into the server and run:

```bash
# Install dependencies
apt update && apt install -y python3 python3-pip nginx certbot python3-certbot-nginx

# Create project dir
mkdir -p /opt/cyber-dashboard

# Get SSL cert
certbot --nginx -d tonyler.is-not-a.dev

# Setup nginx
cp /opt/cyber-dashboard/deploy/nginx-cyber.conf /etc/nginx/sites-available/cyber-dashboard
ln -s /etc/nginx/sites-available/cyber-dashboard /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

Then run `./deploy.sh` from your local machine.

## Useful Commands

```bash
# Check status
ssh root@37.27.15.9 'systemctl status cyber-dashboard'

# View logs
ssh root@37.27.15.9 'journalctl -u cyber-dashboard -f'

# Restart service
ssh root@37.27.15.9 'systemctl restart cyber-dashboard'
```

## DNS

Domain config is in `~/Desktop/cyber/register/domains/tonyler.is-not-a.dev.json`

To update DNS, push changes and create a PR to [open-domains/register](https://github.com/open-domains/register).
