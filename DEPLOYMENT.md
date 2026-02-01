# Deployment Guide

This guide covers deploying the Claude-Telegram Bridge in two modes:

1. **Tunnel Mode** (Local Development) - Uses Cloudflare Tunnel, no public IP needed
2. **Production Mode** (Public Server) - Direct access with Caddy reverse proxy

## Docker Compose Compatibility

**All commands in this guide support both:**

- `docker compose` (Docker Compose V2, included with Docker Desktop)
- `docker compose` (Docker Compose V1, standalone plugin)

The scripts automatically detect which version is available. Examples use `docker compose` (V2) syntax, but `docker compose` (V1) works identically.

---

## Tunnel Mode (Recommended for Local Development)

### Overview

- ✅ No public IP or domain required
- ✅ No port forwarding needed
- ✅ Works behind NAT/firewall
- ✅ Automatic HTTPS via Cloudflare
- ✅ Free and instant setup

### Architecture

```
Telegram → Cloudflare Tunnel → cloudflared (Docker) → bridge (Docker) → tmux → Claude Code
```

### Quick Start

```bash
# 1. Start services
./start-tunnel.sh

# 2. The script will automatically:
#    - Start cloudflared and bridge containers
#    - Detect the tunnel URL (e.g., https://random-name.trycloudflare.com)
#    - Configure the Telegram webhook
```

### Manual Setup

```bash
# 1. Start containers
docker compose --profile tunnel up -d

# 2. Get tunnel URL from logs
docker compose logs cloudflared | grep trycloudflare.com

# Example output:
# +--------------------------------------------------------------------------------------------+
# |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable): |
# |  https://abc-def-ghi.trycloudflare.com                                                    |
# +--------------------------------------------------------------------------------------------+

# 3. Set webhook (replace with your tunnel URL)
docker compose exec bridge python bridge.py set-webhook --domain abc-def-ghi.trycloudflare.com

# 4. Verify
docker compose exec bridge python bridge.py verify-webhook
```

### Important Notes

#### Tunnel URL Changes

- Quick tunnels generate a **random URL each time** you restart
- The URL changes on every restart: `docker compose restart cloudflared` = new URL
- You **must update** the Telegram webhook after each restart:

  ```bash
  # Get new URL
  NEW_URL=$(docker compose logs cloudflared 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)

  # Update webhook
  docker compose exec bridge python bridge.py set-webhook --domain "${NEW_URL#https://}"
  ```

#### Persistent Tunnel (Optional)

For a **permanent URL** that doesn't change on restart:

1. Create a Cloudflare account at https://dash.cloudflare.com
2. Install cloudflared locally: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
3. Create a named tunnel:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create claude-telegram
   ```
4. Update `docker compose.yml`:
   ```yaml
   cloudflared:
     image: cloudflare/cloudflared:latest
     command: tunnel --no-autoupdate run --token YOUR_TUNNEL_TOKEN
     # Get token from: cloudflared tunnel token claude-telegram
   ```

### Troubleshooting

**Tunnel URL not appearing:**

```bash
docker compose logs cloudflared
# Look for connection errors or startup issues
```

**Webhook set but messages not received:**

```bash
# Check if tunnel URL changed
docker compose logs cloudflared | grep trycloudflare.com

# Verify webhook
docker compose exec bridge python bridge.py get-webhook-info
```

**Container keeps restarting:**

```bash
docker compose logs bridge
# Check for Python errors or missing environment variables
```

---

## Production Mode (Public Server)

### Overview

- Requires public IP address
- Requires domain name (DNS configured)
- Direct port exposure (80/443)
- Full SSL/TLS via Caddy

### Architecture

```
Telegram → Your Domain (DNS) → Caddy (Docker :80/:443) → bridge (Docker) → tmux → Claude Code
```

### Prerequisites

1. **Public IP address**
2. **Domain name** pointing to your IP (A record)
   - Example: `coder.luandro.com` → `203.0.113.10`
3. **Ports 80 and 443** accessible (firewall/router configured)

### Quick Start

```bash
# 1. Configure .env
nano .env

# Set your domain:
WEBHOOK_DOMAIN=coder.luandro.com

# For rootless Docker, use unprivileged ports:
CADDY_HTTP_PORT=8081
CADDY_HTTPS_PORT=8443

# OR configure system for privileged ports (80/443):
echo "net.ipv4.ip_unprivileged_port_start=80" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
# Then set:
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443

# 2. Start services
./start-production.sh
```

### Manual Setup

```bash
# 1. Update Caddyfile with your domain
nano Caddyfile
# Change "coder.luandro.com" to your domain

# 2. Start containers
docker compose --profile production up -d

# 3. Set webhook
docker compose exec bridge python bridge.py set-webhook --domain your-domain.com

# 4. Verify
docker compose exec bridge python bridge.py verify-webhook
```

### Port Configuration

#### Option A: Privileged Ports (80/443) - Recommended for Production

```bash
# Allow rootless Docker to bind to ports 80+
echo "net.ipv4.ip_unprivileged_port_start=80" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# In .env:
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443
```

#### Option B: Unprivileged Ports (8081/8443) - No sudo needed

```bash
# In .env:
CADDY_HTTP_PORT=8081
CADDY_HTTPS_PORT=8443

# Then configure port forwarding on your router/firewall:
# External 80 → Internal 8081
# External 443 → Internal 8443
```

### DNS Configuration

Ensure your domain's A record points to your public IP:

```bash
# Check DNS
dig +short coder.luandro.com

# Should return your public IP
# Example: 203.0.113.10
```

### Troubleshooting

**Caddy fails to start (port binding error):**

```bash
# Check if ports are available
sudo netstat -tlnp | grep -E ':(80|443)'

# For rootless Docker with ports 80/443
sysctl net.ipv4.ip_unprivileged_port_start
# Should be 80 or less
```

**SSL certificate fails:**

```bash
# Check Caddy logs
docker compose logs caddy

# Verify DNS resolves correctly
dig +short your-domain.com

# Ensure ports 80/443 are accessible from internet
curl -v http://your-domain.com
```

**Webhook verification fails:**

```bash
# Check if domain is accessible
curl https://your-domain.com/health

# Check Telegram webhook info
docker compose exec bridge python bridge.py get-webhook-info
```

---

## Switching Between Modes

### From Tunnel to Production

```bash
# 1. Stop tunnel mode
docker compose --profile tunnel down

# 2. Update .env with your domain
nano .env
# Set: WEBHOOK_DOMAIN=your-domain.com

# 3. Start production mode
./start-production.sh
```

### From Production to Tunnel

```bash
# 1. Stop production mode
docker compose --profile production down

# 2. Start tunnel mode
./start-tunnel.sh
```

---

## Monitoring

### View Logs

```bash
# Tunnel mode
docker compose logs -f bridge cloudflared

# Production mode
docker compose logs -f bridge caddy

# Just bridge
docker compose logs -f bridge
```

### Check Container Status

```bash
docker compose ps

# Should show:
# - bridge: Up (healthy)
# - cloudflared: Up (tunnel mode only)
# - caddy: Up (production mode only)
```

### Test Webhook

```bash
# Get webhook info
docker compose exec bridge python bridge.py get-webhook-info

# Verify webhook status
docker compose exec bridge python bridge.py verify-webhook

# Check health endpoint
curl -f http://localhost:8080/health
```

---

## Security Recommendations

### Both Modes

1. **Set webhook secret** in `.env`:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   # Add to .env: TELEGRAM_WEBHOOK_SECRET=<generated-secret>
   ```

2. **Restrict DM access** to your user ID:

   ```env
   DM_ALLOWED_USER_ID=your_telegram_user_id
   ```

3. **Keep webhook path secure**:
   - Never commit `.env` to version control
   - Use the generated random path
   - Don't share webhook URLs publicly

### Production Mode Only

4. **Configure firewall**:

   ```bash
   # Allow only necessary ports
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

5. **Enable auto-updates** for Docker images:
   ```bash
   # Use Watchtower or similar
   docker run -d \
     --name watchtower \
     -v /var/run/docker.sock:/var/run/docker.sock \
     containrrr/watchtower
   ```

---

## Common Issues

### Issue: "Cannot expose privileged port 80"

**Solution for tunnel mode:** Use tunnel mode instead (no need for port 80)

**Solution for production mode:**

```bash
echo "net.ipv4.ip_unprivileged_port_start=80" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
docker compose restart
```

### Issue: Tunnel URL keeps changing

**Solution:** Use a named tunnel (see Persistent Tunnel section above)

### Issue: Messages sent but no response

**Checklist:**

1. Check bridge logs: `docker compose logs bridge`
2. Verify webhook: `docker compose exec bridge python bridge.py get-webhook-info`
3. Check state files: `ls -la ~/.claude/telegram_*`
4. Verify hook: `ls -la ~/.claude/hooks/send-to-telegram.sh`
5. Test tmux: `tmux attach -t claude`

### Issue: Hook not executing

**Solution:**

```bash
# 1. Verify hook installed in container
docker compose exec bridge ls -la /claude/hooks/

# 2. Check Claude settings
cat ~/.claude/settings.json | jq '.hooks'

# 3. Manually test hook
echo '{"transcript_path":"~/.claude/test.jsonl"}' | ~/.claude/hooks/send-to-telegram.sh
```

---

## Next Steps

After successful deployment:

1. **Test the bot**:
   - Send `/status` to verify tmux connection
   - Send a regular message
   - Verify Claude responds via Telegram

2. **Set up monitoring**:

   ```bash
   # Watch logs in real-time
   docker compose logs -f bridge

   # Monitor resource usage
   docker stats
   ```

3. **Configure auto-start** (production only):

   ```bash
   # Docker service starts on boot
   sudo systemctl enable docker

   # Add restart policy (already in docker compose.yml)
   # restart: unless-stopped
   ```

4. **Backup configuration**:

   ```bash
   # Save your .env (excluding sensitive tokens)
   cp .env .env.backup

   # Backup Claude config
   tar -czf claude-config-backup.tar.gz ~/.claude
   ```

---

## Quick Reference

### Tunnel Mode Commands

```bash
# Start
./start-tunnel.sh

# Get tunnel URL
docker compose logs cloudflared | grep trycloudflare.com

# Update webhook after restart
NEW_URL=$(docker compose logs cloudflared 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)
docker compose exec bridge python bridge.py set-webhook --domain "${NEW_URL#https://}"

# Stop
docker compose --profile tunnel down
```

### Production Mode Commands

```bash
# Start
./start-production.sh

# Verify webhook
docker compose exec bridge python bridge.py verify-webhook

# Restart services
docker compose --profile production restart

# Stop
docker compose --profile production down
```

### Useful Commands (Both Modes)

```bash
# View logs
docker compose logs -f bridge

# Check status
docker compose ps

# Restart bridge only
docker compose restart bridge

# Execute commands in bridge
docker compose exec bridge python bridge.py --help

# Access tmux session
tmux attach -t claude
```
