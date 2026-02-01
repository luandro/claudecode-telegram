#!/usr/bin/env python3
"""Claude Code <-> Telegram Bridge"""

import os
import json
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

TMUX_SESSION = os.environ.get("TMUX_SESSION", "claude")
# Claude directory for state files (default to ~/.claude, overridden by env var)
CLAUDE_DIR = os.environ.get("CLAUDE_DIR", os.path.expanduser("~/.claude"))

CHAT_ID_FILE = os.path.join(CLAUDE_DIR, "telegram_chat_id")
PENDING_FILE = os.path.join(CLAUDE_DIR, "telegram_pending")
HISTORY_FILE = os.path.join(CLAUDE_DIR, "history.jsonl")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))
# Default to localhost-only for security. Use 0.0.0.0 to bind all interfaces.
HOST = os.environ.get("HOST", "127.0.0.1")
# Generate a long random webhook path for security if not provided or empty
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "").strip()
if not WEBHOOK_PATH:
    WEBHOOK_PATH = secrets.token_hex(32)
# Secret token to validate requests are from Telegram (optional but recommended)
# Set this in Telegram Bot API when setting webhook: ?secret_token=<YOUR_SECRET>
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
# Comma-separated list of allowed Telegram user IDs. If empty, all users are allowed.
# Get your user ID from @userinfobot on Telegram. Example: "123456789,987654321"
# This applies to non-DM chats (groups/channels). DMs are restricted to DM_ALLOWED_USER_ID.
ALLOWED_TELEGRAM_USER_IDS = set()
_allowed_ids = os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "").strip()
if _allowed_ids:
    try:
        ALLOWED_TELEGRAM_USER_IDS = set(int(uid.strip()) for uid in _allowed_ids.split(",") if uid.strip())
    except ValueError:
        print(f"Warning: Invalid ALLOWED_TELEGRAM_USER_IDS format: {_allowed_ids}")

# Single user ID allowed to send DM updates. Only this user can interact via private messages.
# Get your user ID from @userinfobot on Telegram. Example: "123456789"
# If empty or 0, DM updates are not allowed from anyone.
DM_ALLOWED_USER_ID = 0
_dm_allowed = os.environ.get("DM_ALLOWED_USER_ID", "").strip()
if _dm_allowed:
    try:
        DM_ALLOWED_USER_ID = int(_dm_allowed)
    except ValueError:
        print(f"Warning: Invalid DM_ALLOWED_USER_ID format: {_dm_allowed}")

# Configure reaction emoji with validation
_REACTION_EMOJI_RAW = os.environ.get("TELEGRAM_REACTION_EMOJI", "").strip()
if not _REACTION_EMOJI_RAW:
    REACTION_EMOJI = "\U0001f44d"  # Default: 👍
elif _REACTION_EMOJI_RAW.lower() in ("none", "false", "0"):
    REACTION_EMOJI = None
else:
    # Basic validation: emoji should be reasonable length (1-10 chars) to prevent abuse
    REACTION_EMOJI = _REACTION_EMOJI_RAW if len(_REACTION_EMOJI_RAW) <= 10 else None

# Optional tmux socket path (useful when running in Docker with mounted socket)
TMUX_SOCKET_PATH = os.environ.get("TMUX_SOCKET_PATH", "")

# Webhook status cache for fast health checks (avoid external API calls)
# Updated by the recovery loop, read by health check endpoint
_webhook_status_cache = {
    "configured": False,
    "url": None,
    "last_check": 0,
    "last_error": None,
}
_webhook_status_lock = threading.Lock()

BOT_COMMANDS = [
    {"command": "clear", "description": "Clear conversation"},
    {"command": "resume", "description": "Resume session (shows picker)"},
    {"command": "continue_", "description": "Continue most recent session"},
    {"command": "loop", "description": "Ralph Loop: /loop <prompt>"},
    {"command": "stop", "description": "Interrupt Claude (Escape)"},
    {"command": "status", "description": "Check tmux status"},
]

BLOCKED_COMMANDS = [
    "/mcp", "/help", "/settings", "/config", "/model", "/compact", "/cost",
    "/doctor", "/init", "/login", "/logout", "/memory", "/permissions",
    "/pr", "/review", "/terminal", "/vim", "/approved-tools", "/listen"
]


def _redact_sensitive_data(data):
    """Deep redact sensitive fields from API data."""
    # Fields that should never appear in logs
    SENSITIVE_KEYS = {"text", "caption", "chat_id", "message_id", "callback_data", "url"}

    def _redact(obj):
        if isinstance(obj, dict):
            return {k: _redact(v) for k, v in obj.items() if k not in SENSITIVE_KEYS}
        elif isinstance(obj, list):
            return [_redact(item) for item in obj]
        return obj

    return _redact(data) if isinstance(data, dict) else data

def telegram_api(method, data):
    if not BOT_TOKEN:
        return None
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        # Sanitize exception message to hide bot token
        error_msg = str(e).replace(BOT_TOKEN, "<BOT_TOKEN>") if BOT_TOKEN in str(e) else str(e)
        # Deep redact sensitive fields from data
        safe_data = _redact_sensitive_data(data)
        print(f"Telegram API error ({method}): {error_msg} | data={safe_data}")
        return None


def setup_bot_commands():
    result = telegram_api("setMyCommands", {"commands": BOT_COMMANDS})
    if result and result.get("ok"):
        print("Bot commands registered")


def set_webhook(domain: str) -> bool:
    """Set the Telegram webhook URL with current configuration."""
    webhook_url = f"https://{domain}/{WEBHOOK_PATH}"
    return _set_webhook_internal(webhook_url)


def get_webhook_info() -> dict:
    """Get current webhook information from Telegram."""
    result = telegram_api("getWebhookInfo", {})
    if result and result.get("ok"):
        return result.get("result", {})
    print("Failed to get webhook info")
    return {}


def _get_current_telegram_webhook() -> str | None:
    """Get currently configured webhook URL from Telegram.

    Returns:
        Current webhook URL string, or None if no webhook is set or on error
    """
    result = telegram_api("getWebhookInfo", {})
    if not result or not result.get("ok"):
        print("Warning: Failed to query Telegram webhook status", flush=True)
        return None

    info = result.get("result", {})
    url = info.get("url", "").strip()

    # Check for webhook errors
    if info.get("last_error_date"):
        last_error_msg = info.get("last_error_message", "Unknown error")
        error_age = int(time.time()) - info.get("last_error_date", 0)
        if error_age < 3600:  # Recent error (within last hour)
            print(f"Warning: Recent webhook error ({error_age}s ago): {last_error_msg}", flush=True)

    return url if url else None


def delete_webhook() -> bool:
    """Delete the current webhook."""
    result = telegram_api("deleteWebhook", {"drop_pending_updates": True})
    if result and result.get("ok"):
        print("Webhook deleted successfully")
        _delete_file(_webhook_state_file())
        return True
    error_desc = result.get("description", "Unknown error") if result else "No response"
    print(f"Failed to delete webhook: {error_desc}")
    return False


def verify_webhook() -> bool:
    """Verify that the webhook is properly configured and reports OK status."""
    result = telegram_api("getWebhookInfo", {})
    if not result:
        print("Failed to get webhook info: No response from Telegram API")
        return False

    if not result.get("ok"):
        error_desc = result.get("description", "Unknown error")
        print(f"Failed to get webhook info: {error_desc}")
        return False

    info = result.get("result", {})
    url = info.get("url", "")
    pending_count = info.get("pending_update_count", 0)
    last_error = info.get("last_error_date", 0)

    # Check if webhook URL is set
    if not url:
        print("Webhook not configured: No URL set")
        return False

    # Check for pending updates (may indicate delivery issues)
    if pending_count > 0:
        print(f"Warning: {pending_count} pending updates")

    # Check for recent errors
    if last_error:
        error_age = int(time.time()) - last_error
        if error_age < 3600:  # Error in the last hour
            print(f"Warning: Recent webhook error ({error_age} seconds ago)")

    print(f"Webhook OK: {url}")
    return True


def _webhook_state_file() -> Path:
    return Path(CLAUDE_DIR) / "telegram_webhook_url"


def _tunnel_url_file() -> Path:
    return Path(CLAUDE_DIR) / "cloudflared_tunnel_url"


def _read_text_file(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        value = path.read_text().strip()
        return value if value else None
    except Exception:
        return None


def _write_text_file(path: Path, text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return True
    except Exception:
        return False


def _delete_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _is_valid_domain(domain: str) -> bool:
    """Basic domain name validation.

    Args:
        domain: Domain name to validate (e.g., 'example.com', 'sub.example.com')

    Returns:
        True if domain format is valid, False otherwise
    """
    if not domain or len(domain) > 253:
        return False
    # Basic pattern: alphanumeric + hyphens + dots, proper TLD
    pattern = r'^([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$'
    return bool(re.match(pattern, domain.lower()))


def _get_cloudflared_tunnel_url_from_state(max_wait_seconds=60, poll_interval=2):
    """Get public URL for Cloudflare quick tunnels.

    In Docker deployments, reads from a shared state file that the start script
    writes after extracting the URL from cloudflared logs.

    Args:
        max_wait_seconds: Maximum time to wait for tunnel URL file
        poll_interval: Seconds between file checks

    Returns:
        Tunnel URL string or None if not found within timeout
    """
    deadline = time.time() + max_wait_seconds

    while time.time() < deadline:
        tunnel_url = _read_text_file(_tunnel_url_file())
        if tunnel_url:
            return tunnel_url
        time.sleep(poll_interval)

    return None


def _set_webhook_internal(webhook_url):
    """Internal function to set webhook via Telegram API.

    Args:
        webhook_url: Full webhook URL to register

    Returns:
        True if successful, False otherwise
    """
    params = {
        "url": webhook_url,
        "max_connections": 100,
        "drop_pending_updates": False
    }

    if TELEGRAM_WEBHOOK_SECRET:
        params["secret_token"] = TELEGRAM_WEBHOOK_SECRET

    result = telegram_api("setWebhook", params)
    if result and result.get("ok"):
        print(f"Webhook configured: {webhook_url}", flush=True)
        if TELEGRAM_WEBHOOK_SECRET:
            print("Secret token: configured", flush=True)
        _write_text_file(_webhook_state_file(), webhook_url)
        return True
    else:
        error_desc = result.get("description", "Unknown error") if result else "No response"
        print(f"Failed to set webhook: {error_desc}", flush=True)
        return False


def _auto_setup_webhook():
    """Auto-configure Telegram webhook on startup.

    This function:
    1. Checks if auto-setup is enabled
    2. Validates deployment mode is set and valid
    3. Detects deployment mode (tunnel vs production)
    4. Validates domain format for production mode
    5. Gets the appropriate webhook URL
    6. Validates against actual Telegram webhook status (not just local state)
    7. Only re-registers if URL has changed in Telegram
    8. Stores configured URL in state file

    Returns:
        True if configured, False if attempted but failed, None if disabled
    """
    # Check if auto-setup is enabled
    auto_setup_enabled = os.environ.get("WEBHOOK_AUTO_SETUP", "true").lower() not in ("false", "0", "no")
    if not auto_setup_enabled:
        print("Webhook auto-setup disabled via WEBHOOK_AUTO_SETUP", flush=True)
        return None

    # Validate deployment mode is explicitly set
    deployment_mode = os.environ.get("DEPLOYMENT_MODE", "").lower().strip()

    if not deployment_mode:
        print("ERROR: DEPLOYMENT_MODE not set", flush=True)
        print("Please set DEPLOYMENT_MODE to 'tunnel' or 'production' in your .env file", flush=True)
        print("See .env.example for configuration instructions", flush=True)
        return False

    if deployment_mode not in ("tunnel", "production"):
        print(f"ERROR: Invalid DEPLOYMENT_MODE='{deployment_mode}'", flush=True)
        print("Valid options: 'tunnel' or 'production'", flush=True)
        return False

    print(f"Auto-setup webhook for deployment mode: {deployment_mode}", flush=True)

    # State file to track configured webhook URL
    webhook_state_file = _webhook_state_file()
    last_webhook_url = _read_text_file(webhook_state_file)

    # Determine webhook URL based on deployment mode
    webhook_url = None

    if deployment_mode == "tunnel":
        # Get tunnel URL from cloudflared
        print("Waiting for cloudflared tunnel URL...", flush=True)
        tunnel_url = _get_cloudflared_tunnel_url_from_state(max_wait_seconds=60, poll_interval=2)

        if not tunnel_url:
            print("Failed to get tunnel URL - webhook not configured", flush=True)
            print("You can manually set webhook with: docker compose exec bridge python bridge.py set-webhook --domain <your-domain>", flush=True)
            return False

        webhook_url = f"{tunnel_url}/{WEBHOOK_PATH}"

    else:  # production mode
        domain = os.environ.get("WEBHOOK_DOMAIN", "").strip()

        if not domain:
            print("ERROR: WEBHOOK_DOMAIN not set for production mode", flush=True)
            print("Production mode requires a valid domain name", flush=True)
            print("Example: WEBHOOK_DOMAIN=coder.luandro.com", flush=True)
            print("Alternatively, use DEPLOYMENT_MODE=tunnel for local development", flush=True)
            return False

        # Validate domain format
        if not _is_valid_domain(domain):
            print(f"ERROR: Invalid WEBHOOK_DOMAIN format: {domain}", flush=True)
            print("Domain should be in format: example.com or subdomain.example.com", flush=True)
            return False

        webhook_url = f"https://{domain}/{WEBHOOK_PATH}"

    # Query actual Telegram webhook status (not just local state file)
    current_telegram_webhook = _get_current_telegram_webhook()

    # Clean up stale state file if it doesn't match Telegram reality
    if last_webhook_url and not current_telegram_webhook:
        print("Warning: State file exists but webhook not in Telegram (cleaning stale state)", flush=True)
        _delete_file(webhook_state_file)

    # Check if webhook is already correctly configured in Telegram
    if current_telegram_webhook == webhook_url:
        print(f"Webhook already configured in Telegram: {webhook_url}", flush=True)
        # Update state file to match reality
        _write_text_file(webhook_state_file, webhook_url)
        return True

    # Webhook needs to be set/updated
    if current_telegram_webhook:
        print(f"Webhook URL change detected:", flush=True)
        print(f"  Current: {current_telegram_webhook}", flush=True)
        print(f"  New:     {webhook_url}", flush=True)
    else:
        print(f"No webhook configured in Telegram, setting: {webhook_url}", flush=True)

    # Set webhook
    success = _set_webhook_internal(webhook_url)

    return success


def _update_webhook_status_cache(configured: bool, url: str | None = None, error: str | None = None):
    """Update the webhook status cache (thread-safe).

    Called by the recovery loop to update cached status that the health check reads.
    """
    with _webhook_status_lock:
        _webhook_status_cache["configured"] = configured
        _webhook_status_cache["url"] = url
        _webhook_status_cache["last_check"] = int(time.time())
        if error:
            _webhook_status_cache["last_error"] = error
        elif configured:
            _webhook_status_cache["last_error"] = None


def _verify_and_update_webhook_status() -> bool:
    """Verify webhook status with Telegram and update cache.

    Returns:
        True if webhook is properly configured, False otherwise
    """
    current_url = _get_current_telegram_webhook()
    if current_url:
        _update_webhook_status_cache(configured=True, url=current_url)
        return True
    else:
        _update_webhook_status_cache(configured=False, error="No webhook configured in Telegram")
        return False


def send_typing_loop(chat_id):
    while os.path.exists(PENDING_FILE):
        telegram_api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        time.sleep(4)


def _get_tmux_cmd(args):
    """Construct tmux command with optional socket path."""
    cmd = ["tmux"]
    if TMUX_SOCKET_PATH:
        cmd.extend(["-S", TMUX_SOCKET_PATH])
    cmd.extend(args)
    return cmd


def tmux_exists():
    cmd = _get_tmux_cmd(["has-session", "-t", TMUX_SESSION])
    return subprocess.run(cmd, capture_output=True).returncode == 0


def tmux_send(text, literal=True):
    args = ["send-keys", "-t", TMUX_SESSION]
    if literal:
        args.append("-l")
    args.append(text)
    subprocess.run(_get_tmux_cmd(args))


def tmux_send_enter():
    subprocess.run(_get_tmux_cmd(["send-keys", "-t", TMUX_SESSION, "Enter"]))


def tmux_send_escape():
    subprocess.run(_get_tmux_cmd(["send-keys", "-t", TMUX_SESSION, "Escape"]))


def _setup_hooks():
    """Automatically install the Claude hook if it doesn't exist."""
    hooks_dir = os.path.join(CLAUDE_DIR, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    
    hook_dest = os.path.join(hooks_dir, "send-to-telegram.sh")
    hook_src = os.path.join(os.path.dirname(__file__), "hooks", "send-to-telegram.sh")
    
    # If source exists and destination doesn't, or if we want to ensure it's up to date
    if os.path.exists(hook_src):
        print(f"Installing hook to {hook_dest}", flush=True)
        shutil.copy2(hook_src, hook_dest)
        os.chmod(hook_dest, 0o755)
    else:
        # Fallback if running from installed package where hooks/ might be elsewhere
        print(f"Warning: Could not find hook source at {hook_src}", flush=True)


def get_recent_sessions(limit=5):
    if not os.path.exists(HISTORY_FILE):
        return []
    sessions = []
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                try:
                    sessions.append(json.loads(line.strip()))
                except:
                    continue
    except:
        return []
    sessions.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return sessions[:limit]


def get_session_id(project_path):
    encoded = project_path.replace("/", "-").lstrip("-")
    for prefix in [f"-{encoded}", encoded]:
        project_dir = Path.home() / ".claude" / "projects" / prefix
        if project_dir.exists():
            jsonls = list(project_dir.glob("*.jsonl"))
            if jsonls:
                return max(jsonls, key=lambda p: p.stat().st_mtime).stem
    return None


class Handler(BaseHTTPRequestHandler):
    def _is_user_allowed(self, user_id, chat_type=None):
        """Check if a user ID is allowed to interact with the bot.

        Args:
            user_id: The Telegram user ID to check.
            chat_type: The chat type ('private' for DMs, 'group', 'supergroup', 'channel').

        Returns:
            True if user is allowed, False otherwise.
        """
        # DM (private chat) requires DM_ALLOWED_USER_ID to be set and match
        if chat_type == "private":
            if DM_ALLOWED_USER_ID == 0:
                # No DM user configured, deny all DMs
                return False
            return user_id == DM_ALLOWED_USER_ID

        # Non-DM chats use ALLOWED_TELEGRAM_USER_IDS
        if not ALLOWED_TELEGRAM_USER_IDS:
            # No restriction configured for non-DM chats
            return True
        return user_id in ALLOWED_TELEGRAM_USER_IDS

    def _is_private_chat(self, chat):
        """Check if the chat is a private (DM) chat.

        Args:
            chat: The chat object from Telegram update.

        Returns:
            True if private chat, False otherwise.
        """
        return chat.get("type") == "private"

    def _validate_webhook_path(self):
        """Check if the request path matches the webhook path."""
        # Normalize paths: ensure leading slash for comparison
        request_path = "/" + self.path.lstrip("/")
        webhook_path = "/" + WEBHOOK_PATH.lstrip("/")
        return request_path == webhook_path

    def _validate_webhook_secret(self):
        """Check if the X-Telegram-Bot-Api-Secret-Token header matches the secret."""
        if not TELEGRAM_WEBHOOK_SECRET:
            # If no secret is configured, skip validation (not recommended but allowed)
            return True
        # Get the secret token header from Telegram
        secret_token = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(secret_token, TELEGRAM_WEBHOOK_SECRET)

    def do_POST(self):
        # Validate webhook path for security
        if not self._validate_webhook_path():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        # Validate webhook secret token if configured
        if not self._validate_webhook_secret():
            print(f"[AUTH_FAILED] Invalid secret token from {self.client_address[0]}")
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            update = json.loads(body)
            if "callback_query" in update:
                self.handle_callback(update["callback_query"])
            elif "message" in update:
                self.handle_message(update)
        except Exception as e:
            print(f"Error: {e}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        # Health check endpoint (public, no validation needed)
        # IMPORTANT: This endpoint must be fast and local-only (no external API calls)
        # to avoid Docker health check failures due to network issues
        if self.path == "/health":
            deployment_mode = os.environ.get("DEPLOYMENT_MODE", "unknown")

            # Read from local cache (updated by recovery loop)
            with _webhook_status_lock:
                webhook_configured = _webhook_status_cache["configured"]
                last_check = _webhook_status_cache["last_check"]
                last_error = _webhook_status_cache["last_error"]

            # Also check local state file as fallback
            state_file_url = _read_text_file(_webhook_state_file())
            has_state_file = bool(state_file_url)

            # Determine operational status
            # "operational" means the server is running and ready to receive webhooks
            # "webhook_configured" means we believe the webhook is set in Telegram
            is_operational = True  # Server is always operational if responding

            # Build health status response
            status = {
                "status": "healthy",  # Always healthy if server is responding
                "operational": is_operational,
                "webhook_configured": webhook_configured or has_state_file,
                "deployment_mode": deployment_mode,
                "timestamp": int(time.time()),
            }

            # Add cache age info
            if last_check > 0:
                status["webhook_last_verified"] = last_check
                status["webhook_check_age_seconds"] = int(time.time()) - last_check

            # Add warning if there's a recent error
            if last_error:
                status["webhook_last_error"] = last_error

            # Always return 200 OK - report status in body
            # This prevents Docker health check failures during startup or network issues
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
            return

        # Validate webhook path for security
        if not self._validate_webhook_path():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Claude-Telegram Bridge")

    def handle_callback(self, cb):
        chat = cb.get("message", {}).get("chat", {})
        chat_id = chat.get("id")
        chat_type = chat.get("type")
        user_id = cb.get("from", {}).get("id")
        data = cb.get("data", "")
        
        print(f"[CALLBACK] from={user_id} chat={chat_id} data={data}", flush=True)

        telegram_api("answerCallbackQuery", {"callback_query_id": cb.get("id")})

        # Check if user is allowed (pass chat_type for DM vs non-DM handling)
        # Silently ignore unauthorized users (return 200 OK, no action)
        if user_id and not self._is_user_allowed(user_id, chat_type):
            print(f"[AUTH_FAIL] User {user_id} not allowed in {chat_type}", flush=True)
            return

        if not tmux_exists():
            self.reply(chat_id, "tmux session not found")
            return

        if data.startswith("resume:"):
            session_id = data.split(":", 1)[1]
            tmux_send_escape()
            time.sleep(0.2)
            tmux_send("/exit")
            tmux_send_enter()
            time.sleep(0.5)
            tmux_send(f"claude --resume {session_id} --dangerously-skip-permissions")
            tmux_send_enter()
            self.reply(chat_id, f"Resuming: {session_id[:8]}...")

        elif data == "continue_recent":
            tmux_send_escape()
            time.sleep(0.2)
            tmux_send("/exit")
            tmux_send_enter()
            time.sleep(0.5)
            tmux_send("claude --continue --dangerously-skip-permissions")
            tmux_send_enter()
            self.reply(chat_id, "Continuing most recent...")

    def handle_message(self, update):
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        text, chat_id, msg_id = msg.get("text", ""), chat.get("id"), msg.get("message_id")
        chat_type = chat.get("type")
        user_id = msg.get("from", {}).get("id")
        
        print(f"[MESSAGE] from={user_id} chat={chat_id} type={chat_type}", flush=True)
        
        if not text or not chat_id:
            return

        # Check if user is allowed (pass chat_type for DM vs non-DM handling)
        # Silently ignore unauthorized users (return 200 OK, no action)
        if user_id and not self._is_user_allowed(user_id, chat_type):
            print(f"[AUTH_FAIL] User {user_id} not allowed in {chat_type}", flush=True)
            return

        with open(CHAT_ID_FILE, "w") as f:
            f.write(str(chat_id))

        if text.startswith("/"):
            cmd = text.split()[0].lower()

            if cmd == "/status":
                status = "running" if tmux_exists() else "not found"
                self.reply(chat_id, f"tmux '{TMUX_SESSION}': {status}")
                return

            if cmd == "/stop":
                if tmux_exists():
                    tmux_send_escape()
                if os.path.exists(PENDING_FILE):
                    os.remove(PENDING_FILE)
                self.reply(chat_id, "Interrupted")
                return

            if cmd == "/clear":
                if not tmux_exists():
                    self.reply(chat_id, "tmux not found")
                    return
                tmux_send_escape()
                time.sleep(0.2)
                tmux_send("/clear")
                tmux_send_enter()
                self.reply(chat_id, "Cleared")
                return

            if cmd == "/continue_":
                if not tmux_exists():
                    self.reply(chat_id, "tmux not found")
                    return
                tmux_send_escape()
                time.sleep(0.2)
                tmux_send("/exit")
                tmux_send_enter()
                time.sleep(0.5)
                tmux_send("claude --continue --dangerously-skip-permissions")
                tmux_send_enter()
                self.reply(chat_id, "Continuing...")
                return

            if cmd == "/loop":
                if not tmux_exists():
                    self.reply(chat_id, "tmux not found")
                    return
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    self.reply(chat_id, "Usage: /loop <prompt>")
                    return
                prompt = parts[1].replace('"', '\\"')
                full = f'{prompt} Output <promise>DONE</promise> when complete.'
                with open(PENDING_FILE, "w") as f:
                    f.write(str(int(time.time())))
                threading.Thread(target=send_typing_loop, args=(chat_id,), daemon=True).start()
                tmux_send(f'/ralph-loop:ralph-loop "{full}" --max-iterations 5 --completion-promise "DONE"')
                time.sleep(0.3)
                tmux_send_enter()
                self.reply(chat_id, "Ralph Loop started (max 5 iterations)")
                return

            if cmd == "/resume":
                sessions = get_recent_sessions()
                if not sessions:
                    self.reply(chat_id, "No sessions")
                    return
                kb = [[{"text": "Continue most recent", "callback_data": "continue_recent"}]]
                for s in sessions:
                    sid = get_session_id(s.get("project", ""))
                    if sid:
                        kb.append([{"text": s.get("display", "?")[:40] + "...", "callback_data": f"resume:{sid}"}])
                telegram_api("sendMessage", {"chat_id": chat_id, "text": "Select session:", "reply_markup": {"inline_keyboard": kb}})
                return

            if cmd in BLOCKED_COMMANDS:
                self.reply(chat_id, f"'{cmd}' not supported (interactive)")
                return

        # Regular message
        print(f"[MSG_RECEIVED] length={len(text)}")
        with open(PENDING_FILE, "w") as f:
            f.write(str(int(time.time())))

        if msg_id and REACTION_EMOJI:
            telegram_api(
                "setMessageReaction",
                {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "reaction": [{"type": "emoji", "emoji": REACTION_EMOJI}],
                },
            )

        if not tmux_exists():
            self.reply(chat_id, "tmux not found")
            os.remove(PENDING_FILE)
            return

        threading.Thread(target=send_typing_loop, args=(chat_id,), daemon=True).start()
        tmux_send(text)
        tmux_send_enter()

    def reply(self, chat_id, text):
        telegram_api("sendMessage", {"chat_id": chat_id, "text": text})


def main():
    import argparse
    import sys

    # Default webhook domain from environment or fallback
    default_domain = os.environ.get("WEBHOOK_DOMAIN", "coder.luandro.com")

    parser = argparse.ArgumentParser(description="Claude Code <-> Telegram Bridge")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Set webhook command
    webhook_parser = subparsers.add_parser("set-webhook", help="Set Telegram webhook")
    webhook_parser.add_argument(
        "--domain",
        default=default_domain,
        help=f"Webhook domain (default: {default_domain})"
    )

    # Get webhook info command
    subparsers.add_parser("get-webhook-info", help="Get current webhook info")

    # Verify webhook command
    subparsers.add_parser("verify-webhook", help="Verify webhook is properly configured")

    # Delete webhook command
    subparsers.add_parser("delete-webhook", help="Delete webhook")

    args = parser.parse_args()

    # Validate bot token exists for all commands
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set", flush=True)
        return 1

    # Execute command
    if args.command == "set-webhook":
        return 0 if set_webhook(args.domain) else 1
    elif args.command == "get-webhook-info":
        info = get_webhook_info()
        print(json.dumps(info, indent=2), flush=True)
        return 0
    elif args.command == "verify-webhook":
        return 0 if verify_webhook() else 1
    elif args.command == "delete-webhook":
        return 0 if delete_webhook() else 1
    else:
        # Default: run server (backward compatible)
        _setup_hooks()
        setup_bot_commands()

        print(f"Bridge on {HOST}:{PORT}/{WEBHOOK_PATH} | tmux: {TMUX_SESSION}", flush=True)
        server = HTTPServer((HOST, PORT), Handler)

        def _webhook_recovery_loop():
            """Continuous loop that manages webhook configuration and monitors for changes.

            This loop:
            1. Performs initial webhook setup after startup delay
            2. Periodically verifies webhook status with Telegram
            3. Re-configures webhook if tunnel URL changes (for tunnel mode)
            4. Updates the webhook status cache for fast health checks
            """
            raw_delay = os.environ.get("WEBHOOK_STARTUP_DELAY", "5")
            try:
                startup_delay = int(raw_delay)
            except ValueError:
                startup_delay = 5

            if startup_delay > 0:
                print(f"Waiting {startup_delay}s for services to initialize...", flush=True)
                time.sleep(startup_delay)

            # Initial setup
            result = _auto_setup_webhook()
            if result is False:
                print("Warning: Webhook auto-setup failed - may need manual configuration", flush=True)
                print("Manual setup: docker compose exec bridge python bridge.py set-webhook --domain <your-domain>", flush=True)
                _update_webhook_status_cache(configured=False, error="Initial auto-setup failed")
            elif result is True:
                _verify_and_update_webhook_status()

            # Recovery loop settings
            check_interval = 60  # Check every 60 seconds
            max_backoff = 300  # Max 5 minutes between retries on failure
            current_backoff = check_interval
            last_tunnel_url = _read_text_file(_tunnel_url_file())
            deployment_mode = os.environ.get("DEPLOYMENT_MODE", "").lower().strip()

            while True:
                time.sleep(current_backoff)

                try:
                    # Check if tunnel URL changed (tunnel mode only)
                    if deployment_mode == "tunnel":
                        current_tunnel_url = _read_text_file(_tunnel_url_file())
                        if current_tunnel_url and current_tunnel_url != last_tunnel_url:
                            print(f"Tunnel URL changed: {last_tunnel_url} -> {current_tunnel_url}", flush=True)
                            last_tunnel_url = current_tunnel_url
                            # Re-run auto-setup with new URL
                            result = _auto_setup_webhook()
                            if result:
                                _verify_and_update_webhook_status()
                                current_backoff = check_interval  # Reset backoff on success
                            else:
                                current_backoff = min(current_backoff * 2, max_backoff)
                            continue

                    # Periodic verification (all modes)
                    is_configured = _verify_and_update_webhook_status()

                    if not is_configured:
                        # Webhook not configured, try to set it up
                        print("Webhook not configured, attempting recovery...", flush=True)
                        result = _auto_setup_webhook()
                        if result:
                            _verify_and_update_webhook_status()
                            current_backoff = check_interval
                        else:
                            current_backoff = min(current_backoff * 2, max_backoff)
                    else:
                        current_backoff = check_interval  # Reset backoff on success

                except Exception as e:
                    print(f"Error in webhook recovery loop: {e}", flush=True)
                    _update_webhook_status_cache(configured=False, error=str(e))
                    current_backoff = min(current_backoff * 2, max_backoff)

        threading.Thread(target=_webhook_recovery_loop, daemon=True).start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped", flush=True)
        return 0


if __name__ == "__main__":
    main()
