# Operational Verification Checklist

**Date**: 2026-01-30
**Status**: Ready for deployment verification
**Code Status**: All features implemented, operational checks pending

---

## Overview

This document provides step-by-step operational verification for the claudecode-telegram bridge deployment. The code is feature-complete; these checks verify the deployment environment and live integration.

**Key Features to Verify**:

1. DM allowlist (restricts private messages to specific user)
2. Telegram webhook integration (end-to-end message flow)
3. HTTPS/Caddy reverse proxy (secure webhook delivery)
4. Docker deployment (stack health and configuration)

---

## Prerequisites

### Local Environment Setup

```bash
# Verify dependencies are installed
which docker docker-compose tmux curl pytest

# Verify Python environment
source .venv/bin/activate
python --version  # Should be Python 3.8+

# Verify test dependencies
pip list | grep pytest
```

### Environment Variables Checklist

Create/verify `.env` file with required variables:

```bash
# Required
TELEGRAM_BOT_TOKEN=<your_bot_token>
TELEGRAM_WEBHOOK_SECRET=<your_webhook_secret>
WEBHOOK_DOMAIN=coder.luandro.com

# DM Allowlist (CRITICAL: Set to 244055394)
DM_ALLOWED_USER_ID=244055394

# Optional (for group/channel control)
ALLOWED_TELEGRAM_USER_IDS=

# Webhook Path (auto-generated if empty)
WEBHOOK_PATH=

# Caddy Ports (rootless Docker defaults)
CADDY_HTTP_PORT=8081
CADDY_HTTPS_PORT=8443
```

**Verify environment is loaded**:

```bash
source .env
echo "Bot Token: ${TELEGRAM_BOT_TOKEN:0:10}..."
echo "DM Allowed User: $DM_ALLOWED_USER_ID"
echo "Webhook Secret: ${TELEGRAM_WEBHOOK_SECRET:0:10}..."
```

---

## Verification Tasks

### ✅ Task 1: DM Allowlist QA

**Purpose**: Verify that only user ID 244055394 can interact via private messages.

**Code Reference**: `bridge.py` lines 41-48, 247-268

#### Test Plan

**1.1 Verify Configuration**

```bash
# Check DM_ALLOWED_USER_ID is set correctly
grep "DM_ALLOWED_USER_ID" .env
# Expected: DM_ALLOWED_USER_ID=244055394

# Verify it's loaded in the environment
echo $DM_ALLOWED_USER_ID
# Expected: 244055394
```

**1.2 Test Allowed User (ID: 244055394)**

Manual test steps:

1. Send a direct message to the bot from user ID 244055394
2. Verify message is processed and forwarded to Claude
3. Check logs for successful message reception

```bash
# Monitor logs during test
docker compose logs -f bridge | grep -i "MSG_RECEIVED\|AUTH_FAILED"
```

**Expected Output**:

```
[MSG_RECEIVED] length=<message_length>
```

**Evidence to Collect**:

- Screenshot of DM being sent
- Bot response received in Telegram
- Log output showing `[MSG_RECEIVED]`

**1.3 Test Unauthorized User (Any Other User ID)**

Manual test steps:

1. Send a direct message to the bot from a different user (not ID 244055394)
2. Verify message is silently ignored (no response)
3. Check logs confirm no processing occurred

```bash
# Monitor logs during test
docker compose logs -f bridge | grep -i "MSG_RECEIVED\|AUTH_FAILED"
```

**Expected Output**:

- No `[MSG_RECEIVED]` log entry
- No bot response in Telegram
- HTTP 200 OK returned to Telegram (silent rejection)

**Evidence to Collect**:

- Screenshot of DM being sent from unauthorized user
- Confirmation no response received
- Log output showing no message processing

**1.4 Test Group/Channel Behavior (Optional)**

If `ALLOWED_TELEGRAM_USER_IDS` is set:

1. Send message in group from allowed user → should process
2. Send message in group from unauthorized user → should ignore

If `ALLOWED_TELEGRAM_USER_IDS` is empty:

1. All users can interact in groups (default open behavior)

---

### ✅ Task 2: Telegram End-to-End Integration

**Purpose**: Verify complete message flow: Telegram → Bridge → tmux (Claude) → Response → Telegram

**Code Reference**: `bridge.py` webhook handling, `hooks/send-to-telegram.sh`

#### Test Plan

**2.1 Verify tmux Session Exists**

```bash
# Check tmux session is running
tmux has-session -t claude && echo "✓ tmux session 'claude' exists" || echo "✗ Session not found"

# Attach to verify Claude is running (detach with Ctrl+b d)
tmux attach -t claude
```

**2.2 Verify Webhook is Set**

```bash
# Using built-in CLI (recommended)
docker compose exec bridge claudecode-telegram get-webhook-info

# Or manually with curl
docker compose exec bridge curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | python -m json.tool
```

**Expected Output**:

```json
{
  "ok": true,
  "result": {
    "url": "https://coder.luandro.com/<WEBHOOK_PATH>",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "max_connections": 40
  }
}
```

**If webhook is not set**:

```bash
# Set webhook
docker compose exec bridge claudecode-telegram set-webhook --domain coder.luandro.com

# Verify with explicit check
docker compose exec bridge claudecode-telegram verify-webhook
```

**2.3 End-to-End Message Flow Test**

**Test Steps**:

1. Open tmux session in one terminal: `tmux attach -t claude`
2. Monitor bridge logs in another: `docker compose logs -f bridge`
3. Send DM to bot from user ID 244055394: "Hello, Claude!"
4. Observe message flow:
   - Bridge receives webhook → logs `[MSG_RECEIVED]`
   - Message injected into tmux (visible in tmux pane)
   - Claude processes and responds
   - Stop hook triggers, sends response to Telegram
5. Verify response received in Telegram

**Evidence to Collect**:

- Screenshot of message sent in Telegram
- Bridge log showing `[MSG_RECEIVED]`
- tmux pane showing message input and Claude response
- Screenshot of bot response in Telegram
- Hook execution logs (if available)

**2.4 Test Webhook Secret Validation**

```bash
# Send invalid webhook request (should be rejected with 401)
curl -X POST -H "Content-Type: application/json" \
     -H "X-Telegram-Bot-Api-Secret-Token: invalid_secret" \
     -d '{"message": {"text": "test"}}' \
     https://coder.luandro.com/${WEBHOOK_PATH}

# Expected: 401 Unauthorized
# Check logs for AUTH_FAILED message
docker compose logs bridge | grep -i "AUTH_FAILED"
```

**Expected Log Output**:

```
[AUTH_FAILED] Invalid secret token from <IP_ADDRESS>
```

---

### ✅ Task 3: Deployment Checks

**Purpose**: Verify DNS, HTTPS, and stack health on production server.

**Code Reference**: `tests/test_https_connectivity.py`, `docker-compose.yml`, `Caddyfile`

#### Test Plan

**3.1 DNS Resolution**

```bash
# Verify domain resolves to server IP
nslookup coder.luandro.com

# Or with dig
dig +short coder.luandro.com

# Expected: Server IPv4 address (e.g., 123.45.67.89)
```

**Evidence to Collect**:

```
Command: dig +short coder.luandro.com
Output: <SERVER_IP_ADDRESS>
```

**3.2 Docker Stack Health**

```bash
# Start stack
docker compose up -d

# Verify containers are running
docker compose ps

# Check health status
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Health}}"
```

**Expected Output**:

```
NAME                              STATUS          HEALTH
claudecode-telegram-bridge        Up X minutes    healthy
claudecode-telegram-caddy         Up X minutes    N/A
```

**Check logs for errors**:

```bash
# Bridge logs
docker compose logs bridge | tail -50

# Caddy logs
docker compose logs caddy | tail -50

# Look for errors or warnings
docker compose logs | grep -i "error\|warning\|failed"
```

**3.3 HTTPS Connectivity Tests**

**Run automated test suite**:

```bash
# Local tests (Caddyfile config, port checks)
pytest tests/test_https_connectivity.py -v

# Full deployment tests (DNS, SSL, HTTPS)
RUN_DEPLOYMENT_CHECKS=1 pytest tests/test_https_connectivity.py -m integration -v
```

**Expected Output**:

```
tests/test_https_connectivity.py::test_caddyfile_https_config PASSED
tests/test_https_connectivity.py::test_local_https_ports PASSED
tests/test_https_connectivity.py::test_dns_resolution PASSED
tests/test_https_connectivity.py::test_ssl_handshake PASSED
tests/test_https_connectivity.py::test_https_connectivity_curl PASSED

✓ All tests passed
```

**Manual HTTPS verification**:

```bash
# Test HTTPS endpoint is accessible
curl -I https://coder.luandro.com

# Expected: HTTP/2 200 or 301/302
```

**Test SSL certificate**:

```bash
# Check SSL certificate details
openssl s_client -connect coder.luandro.com:443 -servername coder.luandro.com < /dev/null 2>/dev/null | openssl x509 -noout -dates -subject

# Expected output includes:
# - notBefore: <cert start date>
# - notAfter: <cert expiry date>
# - subject: CN=coder.luandro.com
```

**3.4 Webhook Status Verification**

```bash
# Verify webhook is properly configured and receiving updates
docker compose exec bridge claudecode-telegram verify-webhook

# Check webhook info details
docker compose exec bridge claudecode-telegram get-webhook-info | python -m json.tool
```

**Expected Output**:

```
Webhook OK: https://coder.luandro.com/<WEBHOOK_PATH>

{
  "ok": true,
  "result": {
    "url": "https://coder.luandro.com/<WEBHOOK_PATH>",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "last_error_date": 0,
    "last_error_message": "",
    "max_connections": 40
  }
}
```

**Warning Signs**:

- `pending_update_count > 0`: Webhook delivery issues
- `last_error_date` recent (< 1 hour ago): Connection problems
- `last_error_message` present: Review error details

**3.5 Port Accessibility Check**

```bash
# Verify Caddy ports are accessible from server
nc -zv localhost 8081  # HTTP
nc -zv localhost 8443  # HTTPS

# Expected: Connection succeeded for both ports
```

**If using rootful Docker** (ports 80/443):

```bash
nc -zv localhost 80   # HTTP
nc -zv localhost 443  # HTTPS
```

---

## Integration Test Matrix

| Test Case              | User Type          | Chat Type | Expected Behavior                                | Verified |
| ---------------------- | ------------------ | --------- | ------------------------------------------------ | -------- |
| DM from 244055394      | Allowed DM user    | Private   | ✅ Accepted, processed                           | ⬜       |
| DM from other user     | Unauthorized       | Private   | ❌ Silently ignored                              | ⬜       |
| Group msg from allowed | Allowed group user | Group     | ✅ Accepted (if `ALLOWED_TELEGRAM_USER_IDS` set) | ⬜       |
| Group msg from other   | Unauthorized       | Group     | Behavior depends on config                       | ⬜       |
| Webhook secret valid   | Telegram           | Any       | ✅ Accepted                                      | ⬜       |
| Webhook secret invalid | Attacker           | Any       | ❌ 401 Unauthorized                              | ⬜       |
| HTTPS request          | Browser            | N/A       | ✅ Valid SSL cert                                | ⬜       |
| DNS resolution         | System             | N/A       | ✅ Resolves to server IP                         | ⬜       |

---

## Troubleshooting

### Issue: Webhook not receiving updates

**Symptoms**: Messages sent to bot, but no logs in bridge

**Debug Steps**:

```bash
# 1. Verify webhook is set
docker compose exec bridge claudecode-telegram get-webhook-info

# 2. Check pending updates count
# If pending_update_count > 0, webhook delivery is failing

# 3. Test webhook URL is accessible
curl -I https://coder.luandro.com/${WEBHOOK_PATH}
# Should return 200 OK (GET request)

# 4. Check Caddy logs for errors
docker compose logs caddy | grep -i error

# 5. Test webhook with manual POST (simulate Telegram)
curl -X POST -H "Content-Type: application/json" \
     -H "X-Telegram-Bot-Api-Secret-Token: ${TELEGRAM_WEBHOOK_SECRET}" \
     -d '{"message": {"chat": {"id": 244055394, "type": "private"}, "from": {"id": 244055394}, "text": "test", "message_id": 1}}' \
     https://coder.luandro.com/${WEBHOOK_PATH}
```

### Issue: DM allowlist not working

**Symptoms**: Unauthorized users can send DMs, or authorized user is blocked

**Debug Steps**:

```bash
# 1. Verify environment variable is set
docker compose exec bridge printenv | grep DM_ALLOWED_USER_ID
# Expected: DM_ALLOWED_USER_ID=244055394

# 2. Check bridge logs for user ID in requests
docker compose logs bridge | grep -i "MSG_RECEIVED\|AUTH"

# 3. Verify user ID is correct
# Get user ID from @userinfobot on Telegram

# 4. Restart bridge after env changes
docker compose restart bridge
```

### Issue: SSL certificate errors

**Symptoms**: HTTPS tests fail with SSL verification errors

**Debug Steps**:

```bash
# 1. Check Caddy logs for ACME challenge errors
docker compose logs caddy | grep -i "acme\|certificate\|tls"

# 2. Verify domain DNS points to correct server
dig +short coder.luandro.com

# 3. Check Let's Encrypt rate limits
# https://letsencrypt.org/docs/rate-limits/

# 4. Force certificate renewal
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile

# 5. Check Caddy storage for certificates
docker compose exec caddy ls -la /data/caddy/certificates/
```

### Issue: Bridge container unhealthy

**Symptoms**: `docker compose ps` shows bridge as unhealthy

**Debug Steps**:

```bash
# 1. Check health check logs
docker compose logs bridge | grep -i health

# 2. Test health check manually
docker compose exec bridge curl -f http://localhost:8080/${WEBHOOK_PATH}
# Should return 200 OK

# 3. Check if port is listening
docker compose exec bridge netstat -tlnp | grep 8080

# 4. Review bridge startup logs
docker compose logs bridge | head -50
```

---

## Evidence Collection Template

Use this template to document verification results:

```markdown
### Verification Run: [DATE]

**Environment**:

- Domain: coder.luandro.com
- DM Allowed User ID: 244055394
- Webhook Secret: [CONFIGURED ✓/NOT SET ✗]

**Task 1: DM Allowlist QA**

- [ ] Configuration verified
- [ ] Allowed user test: PASS/FAIL
  - Evidence: [screenshot/logs]
- [ ] Unauthorized user test: PASS/FAIL
  - Evidence: [screenshot/logs]

**Task 2: Telegram End-to-End**

- [ ] tmux session active: YES/NO
- [ ] Webhook configured: YES/NO
  - URL: https://coder.luandro.com/[WEBHOOK_PATH]
- [ ] End-to-end flow: PASS/FAIL
  - Message sent: [screenshot]
  - Bridge logs: [excerpt]
  - Bot response: [screenshot]
- [ ] Webhook secret validation: PASS/FAIL

**Task 3: Deployment Checks**

- [ ] DNS resolution: PASS/FAIL
  - IP: [SERVER_IP]
- [ ] Docker stack health: PASS/FAIL
  - Bridge: UP/DOWN
  - Caddy: UP/DOWN
- [ ] HTTPS tests: PASS/FAIL
  - Local tests: [X passed, Y failed]
  - Deployment tests: [X passed, Y failed]
- [ ] Webhook status: HEALTHY/ISSUES
  - Pending updates: [COUNT]
  - Last error: [TIMESTAMP/NONE]

**Issues Encountered**: [NONE/LIST ISSUES]

**Resolution**: [COMPLETED/IN PROGRESS/BLOCKED]
```

---

## Pre-Production Checklist

Before declaring deployment production-ready:

- [ ] All 3 verification tasks completed successfully
- [ ] DM allowlist tested with both allowed and unauthorized users
- [ ] End-to-end message flow working reliably
- [ ] HTTPS tests passing (DNS, SSL, connectivity)
- [ ] Webhook status shows no errors or pending updates
- [ ] Docker stack shows all containers healthy
- [ ] Environment variables documented and backed up
- [ ] Logs reviewed for any warnings or errors
- [ ] Rollback plan documented (how to revert deployment)

---

## Next Steps After Verification

1. **If all tests pass**:
   - Document successful deployment in project notes
   - Set up monitoring/alerting for webhook failures
   - Schedule periodic health checks (weekly)

2. **If issues found**:
   - Document issue details and error messages
   - Consult troubleshooting section
   - File bug report if code defect discovered
   - Update this checklist with lessons learned

3. **Ongoing maintenance**:
   - Monitor Let's Encrypt certificate renewal (90-day cycle)
   - Review logs weekly for unusual activity
   - Test failover scenarios (tmux session crash, bridge restart)
   - Keep dependencies updated (Docker images, Python packages)
