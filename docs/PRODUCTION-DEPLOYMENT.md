# Production Deployment Guide

This guide documents the complete production deployment process and common issues.

## Pre-Deployment Checklist

### 1. Environment Configuration (.env)

**Required settings for production:**

```bash
# MUST be set - prevents random path generation on each process start
WEBHOOK_PATH=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# MUST be set for production
DEPLOYMENT_MODE=production

# Your domain
WEBHOOK_DOMAIN=your-domain.com

# Your bot token
TELEGRAM_BOT_TOKEN=your_bot_token

# User access control
DM_ALLOWED_USER_ID=your_telegram_user_id
```

**Why WEBHOOK_PATH matters:**
If not set, a random path is generated each time a Python process starts. This causes:

- Running server: listens on path A
- CLI commands (set-webhook): use different path B
- Result: 404 errors on all webhook requests

### 2. Bot Token for Hook

The Stop hook needs the bot token to send responses back to Telegram.

```bash
# Create token file (on server)
echo "YOUR_BOT_TOKEN" > ~/.claude/telegram_bot_token
```

### 3. Claude Code Hook Configuration

**Correct format for ~/.claude/settings.json:**

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/send-to-telegram.sh"
          }
        ]
      }
    ]
  }
}
```

**Common mistakes:**

- ❌ Adding `"matcher": {}` - Stop hooks don't support matchers
- ❌ Flat structure without nested `hooks` array
- ❌ Using PostToolUse format with tool matchers

**After changing settings.json, restart Claude Code** - it doesn't hot-reload settings.

## Deployment Steps

### 1. Configure Environment

```bash
cd ~/claudecode-telegram

# Generate stable webhook path
WEBHOOK_PATH=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "WEBHOOK_PATH=$WEBHOOK_PATH" >> .env

# Set deployment mode
echo "DEPLOYMENT_MODE=production" >> .env

# Verify .env
grep -E "WEBHOOK_PATH|DEPLOYMENT_MODE|WEBHOOK_DOMAIN" .env
```

### 2. Create Bot Token File

```bash
# Extract token from .env and save for hook
grep TELEGRAM_BOT_TOKEN .env | cut -d= -f2 > ~/.claude/telegram_bot_token
```

### 3. Configure Hook

```bash
# Verify hook is installed
ls -la ~/.claude/hooks/send-to-telegram.sh

# Verify settings.json has correct format
cat ~/.claude/settings.json | jq '.hooks'
```

### 4. Start Services

```bash
# Start tmux session with Claude Code
tmux new-session -d -s claude 'cd /your/project && claude --dangerously-skip-permissions'

# Start Docker containers
./start-production.sh

# Or manually:
docker compose --profile production up -d
```

### 5. Verify Deployment

```bash
# Check container status
docker compose ps

# Verify webhook
docker compose exec bridge python bridge.py get-webhook-info

# Check health
docker compose exec bridge curl -s http://localhost:8080/health | jq .

# Verify tmux connection from container
docker compose exec bridge tmux -S /tmux-socket has-session -t claude
```

## Troubleshooting

### Issue: 404 errors on webhook

**Symptoms:** Bridge logs show `POST /xxx HTTP/1.1" 404`

**Cause:** Webhook path mismatch between Telegram and running server

**Solution:**

1. Set stable `WEBHOOK_PATH` in .env
2. Restart bridge: `docker compose restart bridge`
3. Webhook auto-configures on startup

### Issue: Messages reach Claude but no response on Telegram

**Symptoms:** Emoji reaction appears, Claude responds in tmux, but no Telegram reply

**Possible causes:**

1. **Hook not configured:**

   ```bash
   cat ~/.claude/settings.json | jq '.hooks'
   ```

2. **Wrong hook format:**
   - Check format matches the correct structure above
   - Restart Claude Code after fixing

3. **Missing bot token file:**

   ```bash
   cat ~/.claude/telegram_bot_token
   ```

4. **Claude Code not restarted after settings change:**

   ```bash
   # Kill and restart Claude
   pkill -f "claude --dangerously"
   tmux send-keys -t claude 'claude --dangerously-skip-permissions' Enter
   ```

5. **Stale tmux socket mount:**

   ```bash
   # Check socket date inside container
   docker compose exec bridge ls -la /tmux-socket

   # If old date, restart container
   docker compose restart bridge
   ```

### Issue: "Settings Error" on Claude startup

**Symptoms:** Claude shows settings error about hooks format

**Solution:** Fix settings.json format - Stop hooks need nested `hooks` array, no matcher.

### Issue: Hook runs but no message sent

**Debug with logging hook:**

```bash
# Check debug log after sending message
cat /tmp/telegram-hook-debug.log
```

**Common issues in debug log:**

- "No pending file" - Message wasn't from Telegram
- "Token not found" - Create ~/.claude/telegram_bot_token
- "Chat ID or transcript check failed" - Files missing

## Post-Restart Checklist

After any server restart:

1. **Start tmux with Claude:**

   ```bash
   tmux new-session -d -s claude 'cd /project && claude --dangerously-skip-permissions'
   ```

2. **Restart Docker containers** (to remount socket):

   ```bash
   docker compose restart bridge
   ```

3. **Verify connection:**
   ```bash
   docker compose exec bridge tmux -S /tmux-socket has-session -t claude
   ```

## File Locations

| File                                  | Purpose                                     |
| ------------------------------------- | ------------------------------------------- |
| `~/.claude/settings.json`             | Hook configuration                          |
| `~/.claude/hooks/send-to-telegram.sh` | Response hook script                        |
| `~/.claude/telegram_bot_token`        | Bot token for hook                          |
| `~/.claude/telegram_chat_id`          | Current chat ID (auto-created)              |
| `~/.claude/telegram_pending`          | Pending message flag (auto-created/deleted) |
| `/tmp/tmux-1000/default`              | Tmux socket (mounted to container)          |
