# Deployment Verification Guide

Quick verification guide for production deployment.

## Prerequisites

**Environment Variables** (`.env`):

```bash
TELEGRAM_BOT_TOKEN=<bot_token>
DEPLOYMENT_MODE=production  # or tunnel for local dev
WEBHOOK_DOMAIN=coder.luandro.com  # production only
TELEGRAM_WEBHOOK_SECRET=<secret>  # generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
DM_ALLOWED_USER_ID=244055394  # restricts DMs to this user only
```

**Server Requirements**:

- Docker & Docker Compose installed
- tmux session running Claude Code: `tmux new -s claude`, then `claude --dangerously-skip-permissions`
- DNS pointing to server IP (production mode)

---

## Quick Start Verification

### 1. Deploy Stack

```bash
# Production mode with Caddy HTTPS
./start-production.sh

# Or tunnel mode for local development
./start-tunnel.sh
```

**Webhook auto-configures on startup.** Check logs:

```bash
docker compose logs bridge | grep -i "webhook\|deployment"
# Expected: "Auto-setup webhook for deployment mode: production"
# Expected: "Webhook configured: https://coder.luandro.com/..."
```

### 2. Verify Health

```bash
# Check containers
docker compose ps

# Expected output:
# NAME                           STATUS          HEALTH
# claudecode-telegram-bridge     Up X minutes    healthy
# claudecode-telegram-caddy      Up X minutes    N/A

# Check webhook status
curl -s http://localhost:8080/health | jq '.'
# Expected: {"status": "healthy", "webhook_configured": true, ...}
```

### 3. Test DM Allowlist

**Allowed user (244055394):**

- Send DM to bot: "Hello"
- Check logs: `docker compose logs bridge | grep MSG_RECEIVED`
- Verify: Bot responds in Telegram

**Unauthorized user:**

- Send DM from different user
- Verify: No logs, no response (silently ignored)

### 4. End-to-End Flow

```bash
# Terminal 1: Monitor bridge
docker compose logs -f bridge

# Terminal 2: Send Telegram message from user 244055394
# "What is 2+2?"

# Verify:
# ✅ Bridge logs [MSG_RECEIVED]
# ✅ Message appears in tmux session
# ✅ Claude processes and responds
# ✅ Response delivered to Telegram
```

---

## Troubleshooting

### Webhook Not Configured

**Check deployment mode:**

```bash
docker compose exec bridge printenv | grep DEPLOYMENT_MODE
# Must be: production or tunnel
```

**Production mode requires domain:**

```bash
docker compose exec bridge printenv | grep WEBHOOK_DOMAIN
# Must be set for production mode
```

**Check webhook status:**

```bash
# Query actual Telegram webhook
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | jq '.result.url'
```

**Manual override (if auto-setup fails):**

```bash
# Disable auto-setup
export WEBHOOK_AUTO_SETUP=false
docker compose restart bridge

# Set manually
docker compose exec bridge python bridge.py set-webhook --domain coder.luandro.com
```

### DM Allowlist Not Working

**Verify user ID:**

```bash
docker compose exec bridge printenv | grep DM_ALLOWED_USER_ID
# Expected: DM_ALLOWED_USER_ID=244055394
```

**Check logs for auth failures:**

```bash
docker compose logs bridge | grep -i "user_id\|allowed"
```

**Restart after env changes:**

```bash
docker compose restart bridge
```

### SSL/HTTPS Issues (Production Mode)

**Verify DNS resolution:**

```bash
dig +short coder.luandro.com
# Should return your server's public IP
```

**Check Caddy logs:**

```bash
docker compose logs caddy | grep -i "certificate\|acme\|error"
```

**Test HTTPS:**

```bash
curl -I https://coder.luandro.com
# Expected: HTTP/2 200 or 301
```

### Bridge Unhealthy

**Check health endpoint:**

```bash
curl -f http://localhost:8080/health || echo "Health check failed"
```

**Review startup logs:**

```bash
docker compose logs bridge | head -50
```

**Verify port listening:**

```bash
docker compose exec bridge netstat -tlnp | grep 8080
```

---

## Production Readiness Checklist

Before going live:

- [ ] `.env` configured with all required variables
- [ ] DNS resolves to server IP (production mode)
- [ ] Docker stack healthy: `docker compose ps`
- [ ] Webhook auto-configured: Check logs
- [ ] Health check returns `"webhook_configured": true`
- [ ] DM allowlist tested with both allowed/unauthorized users
- [ ] End-to-end message flow working
- [ ] HTTPS certificate valid (production mode): `curl -I https://domain`
- [ ] No errors in logs: `docker compose logs | grep -i error`

---

## Deployment Modes Reference

### Production Mode (`DEPLOYMENT_MODE=production`)

**Requirements:**

- `WEBHOOK_DOMAIN` must be set
- Valid DNS pointing to server
- Caddy handles HTTPS with Let's Encrypt

**Auto-setup:**

- Webhook URL: `https://${WEBHOOK_DOMAIN}/${WEBHOOK_PATH}`
- Validates domain format
- Exits with error if domain missing

### Tunnel Mode (`DEPLOYMENT_MODE=tunnel`)

**Requirements:**

- Cloudflared container running
- No public IP needed

**Auto-setup:**

- Waits up to 60s for cloudflared tunnel URL
- Webhook URL: `https://<random>.trycloudflare.com/${WEBHOOK_PATH}`
- Degraded mode if tunnel unavailable

---

## Quick Commands

```bash
# Check deployment mode
echo $DEPLOYMENT_MODE

# View webhook status
curl -s http://localhost:8080/health | jq '.webhook_configured'

# Monitor bridge logs
docker compose logs -f bridge

# Restart bridge
docker compose restart bridge

# Check actual Telegram webhook
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | jq '.'

# Run HTTPS tests (production)
RUN_DEPLOYMENT_CHECKS=1 pytest tests/test_https_connectivity.py -m integration -v
```
