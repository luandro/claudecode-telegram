"""
Telegram webhook request handler.

Processes incoming webhook requests from Telegram, validates payloads,
and coordinates message injection into Claude Code via tmux.
"""

import json
import secrets
from http.server import BaseHTTPRequestHandler
from typing import Optional

from .config import BridgeConfig
from .telegram import TelegramClient
from .tmux import TmuxController
from .state import StateManager
from .webhook import WebhookManager
from .commands.registry import CommandRegistry


class TelegramWebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Telegram webhook requests.

    Processes incoming webhook POST requests from Telegram, validates
    authentication, and dispatches to appropriate callback or message handlers.
    Also provides GET endpoint for health checks.

    Class attributes are set by the factory function to share dependencies
    across handler instances without using mutable default arguments.
    """

    # Class attributes - set by factory function
    config: BridgeConfig = None  # type: ignore
    telegram: TelegramClient = None  # type: ignore
    tmux: TmuxController = None  # type: ignore
    state: StateManager = None  # type: ignore
    webhook: WebhookManager = None  # type: ignore
    commands: CommandRegistry = None  # type: ignore

    def _validate_path(self) -> bool:
        """Validate that the request path matches the configured webhook path.

        Returns:
            True if path matches webhook_path, False otherwise
        """
        # Normalize paths: ensure leading slash for comparison
        request_path = "/" + self.path.lstrip("/")
        webhook_path = "/" + self.config.webhook_path.lstrip("/")
        return request_path == webhook_path

    def _validate_secret(self) -> bool:
        """Validate the webhook secret token from Telegram request headers.

        Uses constant-time comparison to prevent timing attacks.

        Returns:
            True if secret matches or no secret configured, False otherwise
        """
        if not self.config.telegram_webhook_secret:
            # If no secret is configured, skip validation (not recommended but allowed)
            return True

        # Get the secret token header from Telegram
        secret_token = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(secret_token, self.config.telegram_webhook_secret)

    def _is_user_allowed(self, user_id: int, chat_type: str) -> bool:
        """Check if a user ID is allowed to interact with the bot.

        Implements different access control rules for private (DM) chats
        versus group/channel chats:
        - Private chats: Only the configured DM_ALLOWED_USER_ID is allowed
        - Other chats: Users in ALLOWED_TELEGRAM_USER_IDS are allowed

        Args:
            user_id: The Telegram user ID to check
            chat_type: The chat type ('private' for DMs, 'group', 'supergroup', 'channel')

        Returns:
            True if user is allowed, False otherwise
        """
        # DM (private chat) requires DM_ALLOWED_USER_ID to be set and match
        if chat_type == "private":
            if self.config.dm_allowed_user_id == 0:
                # No DM user configured, deny all DMs
                return False
            return user_id == self.config.dm_allowed_user_id

        # Non-DM chats use ALLOWED_TELEGRAM_USER_IDS
        if not self.config.allowed_user_ids:
            # No restriction configured for non-DM chats
            return True
        return user_id in self.config.allowed_user_ids

    def do_GET(self) -> None:
        """Handle GET requests.

        Provides two endpoints:
        - /health: Health check with webhook status (fast, local-only)
        - /{webhook_path}: Basic info response
        """
        # Health check endpoint (public, no validation needed)
        # IMPORTANT: This endpoint must be fast and local-only (no external API calls)
        # to avoid Docker health check failures due to network issues
        if self.path == "/health":
            # Read from webhook status cache (updated by recovery loop)
            status_cache = self.webhook.get_cached_status()

            # Also check local state file as fallback
            state_file_url = self.state.get_webhook_url()
            has_state_file = bool(state_file_url)

            # Determine operational status
            # "operational" means the server is running and ready to receive webhooks
            # "webhook_configured" means we believe the webhook is set in Telegram
            is_operational = True  # Server is always operational if responding

            # Build health status response
            status = {
                "status": "healthy",  # Always healthy if server is responding
                "operational": is_operational,
                "webhook_configured": status_cache.configured or has_state_file,
                "deployment_mode": self.config.deployment_mode,
                "timestamp": status_cache.last_check,
            }

            # Add cache age info
            if status_cache.last_check > 0:
                import time
                status["webhook_last_verified"] = status_cache.last_check
                status["webhook_check_age_seconds"] = int(time.time()) - status_cache.last_check

            # Add warning if there's a recent error
            if status_cache.last_error:
                status["webhook_last_error"] = status_cache.last_error

            # Always return 200 OK - report status in body
            # This prevents Docker health check failures during startup or network issues
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
            return

        # Validate webhook path for security
        if not self._validate_path():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        # Basic info response for webhook endpoint
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Claude-Telegram Bridge")

    def do_POST(self) -> None:
        """Handle POST requests (webhook updates from Telegram).

        Validates the request path and secret token, then dispatches
        to callback_query or message handlers based on update type.
        """
        # Validate webhook path for security
        if not self._validate_path():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        # Validate webhook secret token if configured
        if not self._validate_secret():
            print(f"[AUTH_FAILED] Invalid secret token from {self.client_address[0]}")
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        # Read and parse request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            update = json.loads(body)

            # Dispatch based on update type
            if "callback_query" in update:
                self._handle_callback_query(update["callback_query"])
            elif "message" in update:
                self._handle_message(update)
            else:
                print(f"[UNKNOWN_UPDATE] {update}")
        except json.JSONDecodeError as e:
            print(f"[JSON_ERROR] Failed to parse update: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error handling update: {e}")

        # Always return 200 OK to Telegram
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def handle_callback(self, callback: dict) -> None:
        """Handle callback query from inline keyboard button press.

        Extracts callback data, validates user authorization, answers the callback,
        and handles resume: and continue_recent patterns.

        Args:
            callback: The callback_query object from Telegram update
        """
        # Extract callback data
        chat = callback.get("message", {}).get("chat", {})
        chat_id = chat.get("id")
        chat_type = chat.get("type")
        user_id = callback.get("from", {}).get("id")
        data = callback.get("data", "")
        callback_id = callback.get("id")

        print(f"[CALLBACK] from={user_id} chat={chat_id} data={data}", flush=True)

        # Answer callback query immediately (required by Telegram)
        if callback_id:
            self.telegram.answer_callback(callback_id)

        # Check if user is allowed (pass chat_type for DM vs non-DM handling)
        # Silently ignore unauthorized users (return 200 OK, no action)
        if user_id and not self._is_user_allowed(user_id, chat_type):
            print(f"[AUTH_FAIL] User {user_id} not allowed in {chat_type}", flush=True)
            return

        # Validate chat_id for operations
        if not chat_id:
            print("[CALLBACK_ERROR] Missing chat_id", flush=True)
            return

        # Check if tmux session exists
        if not self.tmux.exists():
            self.telegram.send_message(chat_id, "tmux session not found")
            return

        # Handle resume: pattern (resume specific session)
        if data.startswith("resume:"):
            session_id = data.split(":", 1)[1] if ":" in data else ""
            if not session_id:
                print("[CALLBACK_ERROR] Invalid resume data format", flush=True)
                return

            try:
                self.tmux.exit_and_run(
                    f"claude --resume {session_id} --dangerously-skip-permissions"
                )
                self.telegram.send_message(chat_id, f"Resuming: {session_id[:8]}...")
                print(f"[CALLBACK_SUCCESS] Resumed session {session_id}", flush=True)
            except RuntimeError as e:
                print(f"[CALLBACK_ERROR] Failed to resume session: {e}", flush=True)
                self.telegram.send_message(chat_id, f"Error resuming session: {e}")
            return

        # Handle continue_recent pattern (continue most recent session)
        if data == "continue_recent":
            try:
                self.tmux.exit_and_run(
                    "claude --continue --dangerously-skip-permissions"
                )
                self.telegram.send_message(chat_id, "Continuing most recent...")
                print("[CALLBACK_SUCCESS] Continued most recent session", flush=True)
            except RuntimeError as e:
                print(f"[CALLBACK_ERROR] Failed to continue session: {e}", flush=True)
                self.telegram.send_message(chat_id, f"Error continuing session: {e}")
            return

        # Unknown callback data
        print(f"[CALLBACK_UNKNOWN] Unhandled callback data: {data}", flush=True)

    def _handle_callback_query(self, callback_query: dict) -> None:
        """Internal wrapper for handle_callback to maintain backward compatibility.

        Args:
            callback_query: The callback_query object from Telegram update
        """
        self.handle_callback(callback_query)

    def handle_message(self, update: dict) -> None:
        """Handle incoming text message from Telegram.

        Extracts chat_id, user_id, text, message_id; validates user;
        saves chat_id to state; checks if command (starts with /),
        dispatches to registry or sends to tmux; sets reaction;
        starts typing loop.

        Args:
            update: The full update object containing the message
        """
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        text = msg.get("text", "")
        chat_id = chat.get("id")
        message_id = msg.get("message_id")
        chat_type = chat.get("type")
        user_id = msg.get("from", {}).get("id")

        print(f"[MESSAGE] from={user_id} chat={chat_id} type={chat_type}", flush=True)

        # Validate required fields
        if not text or not chat_id:
            return

        # Check if user is allowed (pass chat_type for DM vs non-DM handling)
        # Silently ignore unauthorized users (return 200 OK, no action)
        if user_id and not self._is_user_allowed(user_id, chat_type):
            print(f"[AUTH_FAIL] User {user_id} not allowed in {chat_type}", flush=True)
            return

        # Save chat_id to state for future replies
        self.state.set_chat_id(chat_id)

        # Set reaction to acknowledge message receipt
        if message_id:
            self.telegram.set_reaction(chat_id, message_id, "👀")

        # Check if message is a command (starts with /)
        if text.startswith("/"):
            self._handle_command(chat_id, message_id, user_id, text)
        else:
            self._handle_non_command(chat_id, message_id, text)

    def _handle_command(self, chat_id: int, message_id: int | None, user_id: int | None, text: str) -> None:
        """Handle command message by dispatching to command registry.

        Args:
            chat_id: Chat ID where message was sent
            message_id: Message ID for reactions
            user_id: User ID who sent the message
            text: Full message text
        """
        # Parse command name (first word after /)
        command_name = text.split()[0] if text else ""

        try:
            # Build command context
            from .commands.base import CommandContext
            ctx = CommandContext(
                chat_id=chat_id,
                message_id=message_id,
                user_id=user_id,
                text=text,
                tmux=self.tmux,
                telegram=self.telegram,
                state=self.state,
                config=self.config
            )

            # Execute command through registry
            reply = self.commands.execute(command_name, ctx)

            # Send reply if command returned one
            if reply:
                self.telegram.send_message(chat_id, reply)

            print(f"[COMMAND] Executed {command_name}", flush=True)

        except ValueError as e:
            # Command is blocked or not found
            error_msg = str(e)
            print(f"[COMMAND_ERROR] {error_msg}", flush=True)
            self.telegram.send_message(chat_id, f"Error: {error_msg}")
        except Exception as e:
            # Unexpected error during command execution
            print(f"[COMMAND_ERROR] Unexpected error executing {command_name}: {e}", flush=True)
            self.telegram.send_message(chat_id, f"Error executing command: {e}")

    def _handle_non_command(self, chat_id: int, message_id: int | None, text: str) -> None:
        """Handle non-command message by sending to tmux and starting typing loop.

        Args:
            chat_id: Chat ID where message was sent
            message_id: Message ID for reactions
            text: Message text to send to Claude
        """
        # Check if tmux session exists
        if not self.tmux.exists():
            self.telegram.send_message(chat_id, "tmux session not found")
            return

        # Set pending flag to indicate message originated from Telegram
        self.state.set_pending()

        # Start typing indicator loop in background
        from .telegram import TypingIndicator
        typing = TypingIndicator(self.telegram, chat_id)
        typing.__enter__()

        try:
            # Send message to tmux (Claude Code)
            self.tmux.send_text(text, press_enter=True)
            print(f"[TMUX] Sent message to Claude: {text[:50]}{'...' if len(text) > 50 else ''}", flush=True)
        except RuntimeError as e:
            print(f"[TMUX_ERROR] Failed to send message: {e}", flush=True)
            self.telegram.send_message(chat_id, f"Error sending to Claude: {e}")
        finally:
            # Stop typing indicator
            typing.__exit__(None, None, None)

    def _handle_message(self, update: dict) -> None:
        """Internal wrapper for handle_message to maintain backward compatibility.

        Args:
            update: The full update object containing the message
        """
        self.handle_message(update)


def create_handler_class(
    config: BridgeConfig,
    telegram: TelegramClient,
    tmux: TmuxController,
    state: StateManager,
    webhook: WebhookManager,
    registry: CommandRegistry
) -> type[TelegramWebhookHandler]:
    """Create a handler class with injected dependencies.

    This factory pattern allows us to inject dependencies into the handler
    class without using global variables or mutable default arguments.
    The factory is needed because HTTPServer instantiates the handler class
    directly without allowing us to pass constructor arguments.

    Args:
        config: Bridge configuration
        telegram: Telegram client instance
        tmux: Tmux controller instance
        state: State manager instance
        webhook: Webhook manager instance
        registry: Command registry instance

    Returns:
        TelegramWebhookHandler class with dependencies set as class attributes
    """
    # Create a new class that inherits from TelegramWebhookHandler
    # and set the class attributes
    class Handler(TelegramWebhookHandler):
        pass

    # Set class attributes (shared across all handler instances)
    Handler.config = config
    Handler.telegram = telegram
    Handler.tmux = tmux
    Handler.state = state
    Handler.webhook = webhook
    Handler.commands = registry

    return Handler


def create_handler_factory(
    config: BridgeConfig,
    telegram: TelegramClient,
    tmux: TmuxController,
    state: StateManager,
    webhook: WebhookManager,
    commands: CommandRegistry
) -> type[TelegramWebhookHandler]:
    """Create a handler class with injected dependencies.

    This is an alias for create_handler_class for backward compatibility.

    Args:
        config: Bridge configuration
        telegram: Telegram client instance
        tmux: Tmux controller instance
        state: State manager instance
        webhook: Webhook manager instance
        commands: Command registry instance

    Returns:
        TelegramWebhookHandler class with dependencies set as class attributes
    """
    return create_handler_class(config, telegram, tmux, state, webhook, commands)
