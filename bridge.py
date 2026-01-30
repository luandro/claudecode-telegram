#!/usr/bin/env python3
"""Claude Code <-> Telegram Bridge"""

import os
import json
import secrets
import subprocess
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

TMUX_SESSION = os.environ.get("TMUX_SESSION", "claude")
CHAT_ID_FILE = os.path.expanduser("~/.claude/telegram_chat_id")
PENDING_FILE = os.path.expanduser("~/.claude/telegram_pending")
HISTORY_FILE = os.path.expanduser("~/.claude/history.jsonl")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))
# Default to localhost-only for security. Use 0.0.0.0 to bind all interfaces.
HOST = os.environ.get("HOST", "127.0.0.1")
# Generate a long random webhook path for security (32 bytes = 64 hex chars)
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", secrets.token_hex(32))
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
_REACTION_EMOJI_RAW = os.environ.get("TELEGRAM_REACTION_EMOJI", "\U0001f44d")  # Default: 👍 (thumbs up)
# Strip whitespace first, then allow explicit disable with "none", "false", "0", or empty string
_REACTION_EMOJI_STRIPPED = _REACTION_EMOJI_RAW.strip()
_REACTION_EMOJI_CANDIDATE = None if not _REACTION_EMOJI_STRIPPED or _REACTION_EMOJI_STRIPPED.lower() in ("none", "false", "0") else _REACTION_EMOJI_STRIPPED
# Basic validation: emoji should be reasonable length (1-10 chars) to prevent abuse
REACTION_EMOJI = _REACTION_EMOJI_CANDIDATE if _REACTION_EMOJI_CANDIDATE and len(_REACTION_EMOJI_CANDIDATE) <= 10 else None

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
    params = {"url": webhook_url}

    if TELEGRAM_WEBHOOK_SECRET:
        params["secret_token"] = TELEGRAM_WEBHOOK_SECRET

    result = telegram_api("setWebhook", params)
    if result and result.get("ok"):
        print(f"Webhook set successfully: {webhook_url}")
        if TELEGRAM_WEBHOOK_SECRET:
            print("Secret token: configured")
        else:
            print("Secret token: not configured (recommended)")
        return True
    else:
        error_desc = result.get("description", "Unknown error") if result else "No response"
        print(f"Failed to set webhook: {error_desc}")
        return False


def get_webhook_info() -> dict:
    """Get current webhook information from Telegram."""
    result = telegram_api("getWebhookInfo", {})
    if result and result.get("ok"):
        return result.get("result", {})
    print("Failed to get webhook info")
    return {}


def delete_webhook() -> bool:
    """Delete the current webhook."""
    result = telegram_api("deleteWebhook", {"drop_pending_updates": True})
    if result and result.get("ok"):
        print("Webhook deleted successfully")
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
        import time
        error_age = int(time.time()) - last_error
        if error_age < 3600:  # Error in the last hour
            print(f"Warning: Recent webhook error ({error_age} seconds ago)")

    print(f"Webhook OK: {url}")
    return True


def send_typing_loop(chat_id):
    while os.path.exists(PENDING_FILE):
        telegram_api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        time.sleep(4)


def tmux_exists():
    return subprocess.run(["tmux", "has-session", "-t", TMUX_SESSION], capture_output=True).returncode == 0


def tmux_send(text, literal=True):
    cmd = ["tmux", "send-keys", "-t", TMUX_SESSION]
    if literal:
        cmd.append("-l")
    cmd.append(text)
    subprocess.run(cmd)


def tmux_send_enter():
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "Enter"])


def tmux_send_escape():
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "Escape"])


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
        telegram_api("answerCallbackQuery", {"callback_query_id": cb.get("id")})

        # Check if user is allowed (pass chat_type for DM vs non-DM handling)
        # Silently ignore unauthorized users (return 200 OK, no action)
        if user_id and not self._is_user_allowed(user_id, chat_type):
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
        if not text or not chat_id:
            return

        # Check if user is allowed (pass chat_type for DM vs non-DM handling)
        # Silently ignore unauthorized users (return 200 OK, no action)
        if user_id and not self._is_user_allowed(user_id, chat_type):
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

    def log_message(self, *args):
        pass


def main():
    import argparse

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
        print("Error: TELEGRAM_BOT_TOKEN not set")
        return 1

    # Execute command
    if args.command == "set-webhook":
        return 0 if set_webhook(args.domain) else 1
    elif args.command == "get-webhook-info":
        info = get_webhook_info()
        print(json.dumps(info, indent=2))
        return 0
    elif args.command == "verify-webhook":
        return 0 if verify_webhook() else 1
    elif args.command == "delete-webhook":
        return 0 if delete_webhook() else 1
    else:
        # Default: run server (backward compatible)
        setup_bot_commands()
        print(f"Bridge on {HOST}:{PORT}/{WEBHOOK_PATH} | tmux: {TMUX_SESSION}")
        try:
            HTTPServer((HOST, PORT), Handler).serve_forever()
        except KeyboardInterrupt:
            print("\nStopped")
        return 0


if __name__ == "__main__":
    main()
