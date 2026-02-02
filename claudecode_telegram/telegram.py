"""Telegram Bot API client with centralized error handling and logging."""

import json
import urllib.request
from typing import Any


class TelegramClient:
    """Centralized Telegram Bot API client.

    Wraps all Telegram API interactions with consistent error handling,
    logging, and sensitive data redaction.
    """

    def __init__(self, bot_token: str):
        """Initialize the Telegram client.

        Args:
            bot_token: Telegram Bot API token
        """
        if not bot_token:
            raise ValueError("bot_token cannot be empty")
        self._bot_token = bot_token
        self._api_base = f"https://api.telegram.org/bot{bot_token}"

    @staticmethod
    def _redact_sensitive_data(data: dict) -> dict:
        """Deep redact sensitive fields from API data.

        Args:
            data: Dictionary potentially containing sensitive data

        Returns:
            Dictionary with sensitive fields removed
        """
        # Fields that should never appear in logs
        SENSITIVE_KEYS = {
            "text", "caption", "chat_id", "message_id",
            "callback_data", "url", "secret_token"
        }

        def _redact(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {
                    k: _redact(v)
                    for k, v in obj.items()
                    if k not in SENSITIVE_KEYS
                }
            elif isinstance(obj, list):
                return [_redact(item) for item in obj]
            return obj

        return _redact(data) if isinstance(data, dict) else data

    def api_call(
        self,
        method: str,
        data: dict,
        timeout: int = 10
    ) -> dict | None:
        """Make a Telegram Bot API call.

        Args:
            method: API method name (e.g., 'sendMessage', 'getWebhookInfo')
            data: Request payload dictionary
            timeout: Request timeout in seconds

        Returns:
            API response dictionary on success, None on failure
        """
        url = f"{self._api_base}/{method}"
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read())
        except Exception as e:
            # Sanitize exception message to hide bot token
            error_msg = str(e).replace(
                self._bot_token, "<BOT_TOKEN>"
            ) if self._bot_token in str(e) else str(e)

            # Deep redact sensitive fields from data
            safe_data = self._redact_sensitive_data(data)
            print(f"Telegram API error ({method}): {error_msg} | data={safe_data}")
            return None

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None
    ) -> dict | None:
        """Send a text message.

        Args:
            chat_id: Target chat ID
            text: Message text
            reply_markup: Optional inline keyboard or reply markup

        Returns:
            API response on success, None on failure
        """
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text
        }
        if reply_markup:
            data["reply_markup"] = reply_markup

        return self.api_call("sendMessage", data)

    def set_reaction(
        self,
        chat_id: int,
        message_id: int,
        emoji: str
    ) -> bool:
        """Set a reaction on a message.

        Args:
            chat_id: Chat containing the message
            message_id: Message to react to
            emoji: Emoji reaction (e.g., '👍')

        Returns:
            True if successful, False otherwise
        """
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": emoji}]
        }

        result = self.api_call("setMessageReaction", data)
        return bool(result and result.get("ok"))

    def send_typing(self, chat_id: int) -> bool:
        """Send typing action indicator.

        Args:
            chat_id: Target chat ID

        Returns:
            True if successful, False otherwise
        """
        data = {
            "chat_id": chat_id,
            "action": "typing"
        }

        result = self.api_call("sendChatAction", data)
        return bool(result and result.get("ok"))

    def answer_callback(self, callback_id: str) -> bool:
        """Answer a callback query.

        Args:
            callback_id: Callback query ID from Telegram

        Returns:
            True if successful, False otherwise
        """
        data = {"callback_query_id": callback_id}

        result = self.api_call("answerCallbackQuery", data)
        return bool(result and result.get("ok"))

    def set_webhook(
        self,
        url: str,
        secret: str | None = None,
        max_connections: int = 100
    ) -> bool:
        """Configure the webhook URL.

        Args:
            url: Full webhook URL (must be HTTPS)
            secret: Optional secret token for request validation
            max_connections: Maximum allowed webhook connections (1-100)

        Returns:
            True if successful, False otherwise
        """
        data: dict[str, Any] = {
            "url": url,
            "max_connections": max_connections,
            "drop_pending_updates": False
        }

        if secret:
            data["secret_token"] = secret

        result = self.api_call("setWebhook", data)
        if result and result.get("ok"):
            print(f"Webhook configured: {url}", flush=True)
            if secret:
                print("Secret token: configured", flush=True)
            return True

        error_desc = result.get("description", "Unknown error") if result else "No response"
        print(f"Failed to set webhook: {error_desc}", flush=True)
        return False

    def get_webhook_info(self) -> dict:
        """Get current webhook configuration.

        Returns:
            Dictionary with webhook info, empty dict on failure
        """
        result = self.api_call("getWebhookInfo", {})
        if result and result.get("ok"):
            return result.get("result", {})

        print("Failed to get webhook info")
        return {}

    def delete_webhook(self, drop_pending: bool = True) -> bool:
        """Delete the current webhook.

        Args:
            drop_pending: Whether to drop pending updates

        Returns:
            True if successful, False otherwise
        """
        data = {"drop_pending_updates": drop_pending}

        result = self.api_call("deleteWebhook", data)
        if result and result.get("ok"):
            print("Webhook deleted successfully")
            return True

        error_desc = result.get("description", "Unknown error") if result else "No response"
        print(f"Failed to delete webhook: {error_desc}")
        return False

    def set_commands(self, commands: list[dict]) -> bool:
        """Register bot commands menu.

        Args:
            commands: List of command dicts with 'command' and 'description' keys

        Returns:
            True if successful, False otherwise
        """
        data = {"commands": commands}

        result = self.api_call("setMyCommands", data)
        if result and result.get("ok"):
            print("Bot commands registered")
            return True

        return False
