"""Integration tests for TelegramClient with bridge.py compatibility."""

from unittest.mock import patch, MagicMock

import pytest

from claudecode_telegram.telegram import TelegramClient


class TestTelegramClientIntegration:
    """Integration tests to verify TelegramClient matches bridge.py behavior."""

    @pytest.fixture
    def client(self):
        """Create a TelegramClient instance for testing."""
        return TelegramClient("test_bot_token_123")

    def test_client_mimics_bridge_telegram_api_structure(self, client):
        """Verify client has same API structure as bridge.py telegram_api function."""
        # The old telegram_api function had these characteristics:
        # 1. Returns None on missing token - client raises ValueError instead (better)
        # 2. Makes POST request to Telegram API
        # 3. Redacts sensitive data in errors
        # 4. Returns parsed JSON response

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"ok": true, "result": {}}'
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.api_call("testMethod", {"test": "data"})

            assert result == {"ok": True, "result": {}}
            assert mock_urlopen.called

    def test_send_message_replaces_bridge_pattern(self, client):
        """Verify send_message can replace bridge.py's inline telegram_api calls."""
        # Bridge.py pattern:
        # telegram_api("sendMessage", {"chat_id": chat_id, "text": text})

        with patch.object(client, 'api_call') as mock_api:
            mock_api.return_value = {"ok": True}

            client.send_message(12345, "Test message")

            mock_api.assert_called_once()
            call_args = mock_api.call_args[0]
            assert call_args[0] == "sendMessage"
            assert call_args[1]["chat_id"] == 12345
            assert call_args[1]["text"] == "Test message"

    def test_set_reaction_replaces_bridge_pattern(self, client):
        """Verify set_reaction can replace bridge.py's inline reaction calls."""
        # Bridge.py pattern:
        # telegram_api("setMessageReaction", {
        #     "chat_id": chat_id,
        #     "message_id": msg_id,
        #     "reaction": [{"type": "emoji", "emoji": REACTION_EMOJI}]
        # })

        with patch.object(client, 'api_call') as mock_api:
            mock_api.return_value = {"ok": True}

            result = client.set_reaction(12345, 67890, "👍")

            assert result is True
            mock_api.assert_called_once()
            call_args = mock_api.call_args[0]
            assert call_args[0] == "setMessageReaction"
            assert call_args[1]["chat_id"] == 12345
            assert call_args[1]["message_id"] == 67890
            assert call_args[1]["reaction"] == [{"type": "emoji", "emoji": "👍"}]

    def test_webhook_methods_replace_bridge_functions(self, client):
        """Verify webhook methods can replace bridge.py's webhook functions."""
        # Bridge.py has these functions:
        # - set_webhook(domain) -> calls _set_webhook_internal
        # - get_webhook_info()
        # - delete_webhook()
        # - verify_webhook()

        with patch.object(client, 'api_call') as mock_api:
            # Test set_webhook
            mock_api.return_value = {"ok": True}
            result = client.set_webhook("https://example.com/webhook")
            assert result is True

            # Test get_webhook_info
            mock_api.return_value = {"ok": True, "result": {"url": "https://example.com"}}
            info = client.get_webhook_info()
            assert info["url"] == "https://example.com"

            # Test delete_webhook
            mock_api.return_value = {"ok": True}
            result = client.delete_webhook()
            assert result is True

    def test_error_handling_maintains_bridge_behavior(self, client):
        """Verify error handling matches bridge.py's pattern."""
        # Bridge.py returns None on errors and prints sanitized messages

        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = Exception("Network error with test_bot_token_123")

            with patch('builtins.print') as mock_print:
                result = client.api_call("testMethod", {"data": "value"})

                # Should return None like bridge.py
                assert result is None

                # Should have printed error with redacted token
                assert mock_print.called
                error_msg = str(mock_print.call_args)
                assert "<BOT_TOKEN>" in error_msg
                assert "test_bot_token_123" not in error_msg

    def test_redaction_maintains_bridge_security(self, client):
        """Verify sensitive data redaction matches bridge.py's _redact_sensitive_data."""
        # Bridge.py redacts: text, caption, chat_id, message_id, callback_data, url

        test_data = {
            "text": "secret",
            "chat_id": 123,
            "ok": True,
            "nested": {
                "message_id": 456,
                "safe": "visible"
            }
        }

        redacted = TelegramClient._redact_sensitive_data(test_data)

        # Sensitive fields should be gone
        assert "text" not in redacted
        assert "chat_id" not in redacted
        assert "message_id" not in redacted["nested"]

        # Safe fields should remain
        assert redacted["ok"] is True
        assert redacted["nested"]["safe"] == "visible"

    @patch('builtins.print')
    def test_initialization_requires_token(self, mock_print):
        """Verify client properly validates token (improvement over bridge.py)."""
        # Bridge.py's telegram_api returns None if no token
        # TelegramClient raises ValueError (better for early error detection)

        with pytest.raises(ValueError, match="bot_token cannot be empty"):
            TelegramClient("")
