"""Tests for TelegramClient class."""

import json
import time
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from claudecode_telegram.telegram import TelegramClient, TypingIndicator


class TestTelegramClientInit:
    """Test TelegramClient initialization."""

    def test_init_with_valid_token(self):
        """Test initialization with valid bot token."""
        client = TelegramClient("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
        assert client._bot_token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        assert client._api_base == "https://api.telegram.org/bot123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    def test_init_with_empty_token(self):
        """Test initialization with empty token raises ValueError."""
        with pytest.raises(ValueError, match="bot_token cannot be empty"):
            TelegramClient("")


class TestRedactSensitiveData:
    """Test sensitive data redaction."""

    def test_redact_simple_dict(self):
        """Test redaction of simple dictionary."""
        data = {
            "text": "secret message",
            "chat_id": 12345,
            "safe_field": "visible"
        }
        redacted = TelegramClient._redact_sensitive_data(data)
        assert "text" not in redacted
        assert "chat_id" not in redacted
        assert redacted["safe_field"] == "visible"

    def test_redact_nested_dict(self):
        """Test redaction of nested dictionary."""
        data = {
            "message": {
                "text": "secret",
                "chat": {
                    "chat_id": 123,
                    "type": "private"
                }
            },
            "ok": True
        }
        redacted = TelegramClient._redact_sensitive_data(data)
        assert "text" not in redacted["message"]
        assert "chat_id" not in redacted["message"]["chat"]
        assert redacted["message"]["chat"]["type"] == "private"
        assert redacted["ok"] is True

    def test_redact_list_of_dicts(self):
        """Test redaction of list containing dictionaries."""
        data = {
            "updates": [
                {"message_id": 1, "text": "msg1"},
                {"message_id": 2, "text": "msg2"}
            ]
        }
        redacted = TelegramClient._redact_sensitive_data(data)
        for update in redacted["updates"]:
            assert "message_id" not in update
            assert "text" not in update

    def test_redact_all_sensitive_keys(self):
        """Test all sensitive keys are redacted."""
        data = {
            "text": "secret",
            "caption": "caption",
            "chat_id": 123,
            "message_id": 456,
            "callback_data": "data",
            "url": "https://example.com",
            "secret_token": "token"
        }
        redacted = TelegramClient._redact_sensitive_data(data)
        assert redacted == {}

    def test_redact_non_dict_returns_unchanged(self):
        """Test non-dict input returns unchanged."""
        assert TelegramClient._redact_sensitive_data("string") == "string"
        assert TelegramClient._redact_sensitive_data(123) == 123
        assert TelegramClient._redact_sensitive_data(None) is None


class TestApiCall:
    """Test api_call method."""

    @patch('urllib.request.urlopen')
    def test_successful_api_call(self, mock_urlopen):
        """Test successful API call."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"ok": True, "result": "success"}).encode()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        client = TelegramClient("test_token")
        result = client.api_call("testMethod", {"param": "value"})

        assert result == {"ok": True, "result": "success"}
        assert mock_urlopen.called

    @patch('urllib.request.urlopen')
    def test_api_call_timeout(self, mock_urlopen):
        """Test API call with timeout."""
        mock_urlopen.side_effect = urllib.error.URLError("timeout")

        client = TelegramClient("test_token")
        result = client.api_call("testMethod", {"param": "value"})

        assert result is None

    @patch('urllib.request.urlopen')
    @patch('builtins.print')
    def test_api_call_redacts_token_in_error(self, mock_print, mock_urlopen):
        """Test API call redacts bot token in error messages."""
        mock_urlopen.side_effect = Exception("Error with test_token in message")

        client = TelegramClient("test_token")
        result = client.api_call("testMethod", {"param": "value"})

        assert result is None
        # Verify token was redacted in error message
        call_args = str(mock_print.call_args)
        assert "test_token" not in call_args
        assert "<BOT_TOKEN>" in call_args

    @patch('urllib.request.urlopen')
    @patch('builtins.print')
    def test_api_call_redacts_sensitive_data_in_error(self, mock_print, mock_urlopen):
        """Test API call redacts sensitive data in error logs."""
        mock_urlopen.side_effect = Exception("API error")

        client = TelegramClient("test_token")
        result = client.api_call("sendMessage", {
            "chat_id": 12345,
            "text": "secret message"
        })

        assert result is None
        # Verify sensitive data was redacted
        call_args = str(mock_print.call_args)
        assert "12345" not in call_args
        assert "secret message" not in call_args


class TestSendMessage:
    """Test send_message method."""

    @patch.object(TelegramClient, 'api_call')
    def test_send_message_simple(self, mock_api_call):
        """Test sending simple message."""
        mock_api_call.return_value = {"ok": True, "result": {"message_id": 1}}

        client = TelegramClient("test_token")
        result = client.send_message(12345, "Hello, World!")

        mock_api_call.assert_called_once_with(
            "sendMessage",
            {"chat_id": 12345, "text": "Hello, World!"}
        )
        assert result == {"ok": True, "result": {"message_id": 1}}

    @patch.object(TelegramClient, 'api_call')
    def test_send_message_with_reply_markup(self, mock_api_call):
        """Test sending message with reply markup."""
        mock_api_call.return_value = {"ok": True}

        client = TelegramClient("test_token")
        reply_markup = {"inline_keyboard": [[{"text": "Button", "callback_data": "btn1"}]]}
        client.send_message(12345, "Choose:", reply_markup)

        mock_api_call.assert_called_once_with(
            "sendMessage",
            {
                "chat_id": 12345,
                "text": "Choose:",
                "reply_markup": reply_markup
            }
        )


class TestSetReaction:
    """Test set_reaction method."""

    @patch.object(TelegramClient, 'api_call')
    def test_set_reaction_success(self, mock_api_call):
        """Test successful reaction setting."""
        mock_api_call.return_value = {"ok": True}

        client = TelegramClient("test_token")
        result = client.set_reaction(12345, 67890, "👍")

        mock_api_call.assert_called_once_with(
            "setMessageReaction",
            {
                "chat_id": 12345,
                "message_id": 67890,
                "reaction": [{"type": "emoji", "emoji": "👍"}]
            }
        )
        assert result is True

    @patch.object(TelegramClient, 'api_call')
    def test_set_reaction_failure(self, mock_api_call):
        """Test reaction setting failure."""
        mock_api_call.return_value = None

        client = TelegramClient("test_token")
        result = client.set_reaction(12345, 67890, "👍")

        assert result is False


class TestSendTyping:
    """Test send_typing method."""

    @patch.object(TelegramClient, 'api_call')
    def test_send_typing_success(self, mock_api_call):
        """Test successful typing indicator."""
        mock_api_call.return_value = {"ok": True}

        client = TelegramClient("test_token")
        result = client.send_typing(12345)

        mock_api_call.assert_called_once_with(
            "sendChatAction",
            {"chat_id": 12345, "action": "typing"}
        )
        assert result is True

    @patch.object(TelegramClient, 'api_call')
    def test_send_typing_failure(self, mock_api_call):
        """Test typing indicator failure."""
        mock_api_call.return_value = {"ok": False}

        client = TelegramClient("test_token")
        result = client.send_typing(12345)

        assert result is False


class TestAnswerCallback:
    """Test answer_callback method."""

    @patch.object(TelegramClient, 'api_call')
    def test_answer_callback_success(self, mock_api_call):
        """Test successful callback answer."""
        mock_api_call.return_value = {"ok": True}

        client = TelegramClient("test_token")
        result = client.answer_callback("callback_query_123")

        mock_api_call.assert_called_once_with(
            "answerCallbackQuery",
            {"callback_query_id": "callback_query_123"}
        )
        assert result is True

    @patch.object(TelegramClient, 'api_call')
    def test_answer_callback_failure(self, mock_api_call):
        """Test callback answer failure."""
        mock_api_call.return_value = None

        client = TelegramClient("test_token")
        result = client.answer_callback("callback_query_123")

        assert result is False


class TestSetWebhook:
    """Test set_webhook method."""

    @patch.object(TelegramClient, 'api_call')
    @patch('builtins.print')
    def test_set_webhook_success(self, mock_print, mock_api_call):
        """Test successful webhook configuration."""
        mock_api_call.return_value = {"ok": True}

        client = TelegramClient("test_token")
        result = client.set_webhook("https://example.com/webhook")

        mock_api_call.assert_called_once_with(
            "setWebhook",
            {
                "url": "https://example.com/webhook",
                "max_connections": 100,
                "drop_pending_updates": False
            }
        )
        assert result is True
        assert any("Webhook configured" in str(call) for call in mock_print.call_args_list)

    @patch.object(TelegramClient, 'api_call')
    @patch('builtins.print')
    def test_set_webhook_with_secret(self, mock_print, mock_api_call):
        """Test webhook configuration with secret token."""
        mock_api_call.return_value = {"ok": True}

        client = TelegramClient("test_token")
        result = client.set_webhook(
            "https://example.com/webhook",
            secret="my_secret_token",
            max_connections=50
        )

        mock_api_call.assert_called_once_with(
            "setWebhook",
            {
                "url": "https://example.com/webhook",
                "max_connections": 50,
                "drop_pending_updates": False,
                "secret_token": "my_secret_token"
            }
        )
        assert result is True
        assert any("Secret token: configured" in str(call) for call in mock_print.call_args_list)

    @patch.object(TelegramClient, 'api_call')
    @patch('builtins.print')
    def test_set_webhook_failure(self, mock_print, mock_api_call):
        """Test webhook configuration failure."""
        mock_api_call.return_value = {"ok": False, "description": "Invalid URL"}

        client = TelegramClient("test_token")
        result = client.set_webhook("https://example.com/webhook")

        assert result is False
        assert any("Failed to set webhook" in str(call) and "Invalid URL" in str(call)
                   for call in mock_print.call_args_list)


class TestGetWebhookInfo:
    """Test get_webhook_info method."""

    @patch.object(TelegramClient, 'api_call')
    def test_get_webhook_info_success(self, mock_api_call):
        """Test successful webhook info retrieval."""
        webhook_data = {
            "url": "https://example.com/webhook",
            "has_custom_certificate": False,
            "pending_update_count": 0
        }
        mock_api_call.return_value = {"ok": True, "result": webhook_data}

        client = TelegramClient("test_token")
        result = client.get_webhook_info()

        mock_api_call.assert_called_once_with("getWebhookInfo", {})
        assert result == webhook_data

    @patch.object(TelegramClient, 'api_call')
    @patch('builtins.print')
    def test_get_webhook_info_failure(self, mock_print, mock_api_call):
        """Test webhook info retrieval failure."""
        mock_api_call.return_value = None

        client = TelegramClient("test_token")
        result = client.get_webhook_info()

        assert result == {}
        assert any("Failed to get webhook info" in str(call) for call in mock_print.call_args_list)


class TestDeleteWebhook:
    """Test delete_webhook method."""

    @patch.object(TelegramClient, 'api_call')
    @patch('builtins.print')
    def test_delete_webhook_success(self, mock_print, mock_api_call):
        """Test successful webhook deletion."""
        mock_api_call.return_value = {"ok": True}

        client = TelegramClient("test_token")
        result = client.delete_webhook()

        mock_api_call.assert_called_once_with(
            "deleteWebhook",
            {"drop_pending_updates": True}
        )
        assert result is True
        assert any("Webhook deleted successfully" in str(call) for call in mock_print.call_args_list)

    @patch.object(TelegramClient, 'api_call')
    def test_delete_webhook_no_drop_pending(self, mock_api_call):
        """Test webhook deletion without dropping pending updates."""
        mock_api_call.return_value = {"ok": True}

        client = TelegramClient("test_token")
        client.delete_webhook(drop_pending=False)

        mock_api_call.assert_called_once_with(
            "deleteWebhook",
            {"drop_pending_updates": False}
        )

    @patch.object(TelegramClient, 'api_call')
    @patch('builtins.print')
    def test_delete_webhook_failure(self, mock_print, mock_api_call):
        """Test webhook deletion failure."""
        mock_api_call.return_value = {"ok": False, "description": "Not found"}

        client = TelegramClient("test_token")
        result = client.delete_webhook()

        assert result is False
        assert any("Failed to delete webhook" in str(call) and "Not found" in str(call)
                   for call in mock_print.call_args_list)


class TestSetCommands:
    """Test set_commands method."""

    @patch.object(TelegramClient, 'api_call')
    @patch('builtins.print')
    def test_set_commands_success(self, mock_print, mock_api_call):
        """Test successful commands registration."""
        mock_api_call.return_value = {"ok": True}

        commands = [
            {"command": "start", "description": "Start the bot"},
            {"command": "help", "description": "Show help"}
        ]

        client = TelegramClient("test_token")
        result = client.set_commands(commands)

        mock_api_call.assert_called_once_with(
            "setMyCommands",
            {"commands": commands}
        )
        assert result is True
        assert any("Bot commands registered" in str(call) for call in mock_print.call_args_list)

    @patch.object(TelegramClient, 'api_call')
    def test_set_commands_failure(self, mock_api_call):
        """Test commands registration failure."""
        mock_api_call.return_value = {"ok": False}

        client = TelegramClient("test_token")
        result = client.set_commands([])

        assert result is False


class TestStartTypingLoop:
    """Test start_typing_loop method."""

    @patch.object(TelegramClient, 'send_typing')
    def test_start_typing_loop_runs_until_flag_exists(self, mock_send_typing, tmp_path):
        """Test typing loop runs until stop flag file exists."""
        stop_flag = tmp_path / "stop_flag"
        mock_send_typing.return_value = True

        client = TelegramClient("test_token")
        thread = client.start_typing_loop(12345, stop_flag)

        # Let it run for a bit
        time.sleep(0.1)

        # Verify typing was sent at least once
        assert mock_send_typing.call_count >= 1
        assert mock_send_typing.call_args[0] == (12345,)

        # Create stop flag and wait for thread to finish
        stop_flag.touch()
        thread.join(timeout=5.0)
        assert not thread.is_alive()

    @patch.object(TelegramClient, 'send_typing')
    def test_start_typing_loop_stops_immediately_if_flag_exists(self, mock_send_typing, tmp_path):
        """Test typing loop stops immediately if flag already exists."""
        stop_flag = tmp_path / "stop_flag"
        stop_flag.touch()  # Create flag before starting
        mock_send_typing.return_value = True

        client = TelegramClient("test_token")
        thread = client.start_typing_loop(12345, stop_flag)

        # Wait briefly and verify thread completes
        thread.join(timeout=1.0)
        assert not thread.is_alive()

    @patch.object(TelegramClient, 'send_typing')
    def test_start_typing_loop_is_daemon_thread(self, mock_send_typing, tmp_path):
        """Test typing loop thread is daemon so it won't block program exit."""
        stop_flag = tmp_path / "stop_flag"
        mock_send_typing.return_value = True

        client = TelegramClient("test_token")
        thread = client.start_typing_loop(12345, stop_flag)

        assert thread.daemon is True

        # Cleanup
        stop_flag.touch()
        thread.join(timeout=1.0)


class TestTypingIndicator:
    """Test TypingIndicator context manager."""

    @patch.object(TelegramClient, 'send_typing')
    def test_typing_indicator_starts_and_stops(self, mock_send_typing):
        """Test typing indicator starts on enter and stops on exit."""
        mock_send_typing.return_value = True
        client = TelegramClient("test_token")

        with TypingIndicator(client, 12345):
            # Should be sending typing indicators
            time.sleep(0.1)
            assert mock_send_typing.call_count >= 1

        # After context exit, thread should stop
        time.sleep(0.2)
        call_count_after_exit = mock_send_typing.call_count
        time.sleep(0.5)

        # Should not increase (or increase by at most 1 if timing is unlucky)
        assert mock_send_typing.call_count <= call_count_after_exit + 1

    @patch.object(TelegramClient, 'send_typing')
    def test_typing_indicator_with_custom_interval(self, mock_send_typing):
        """Test typing indicator with custom interval."""
        mock_send_typing.return_value = True
        client = TelegramClient("test_token")

        with TypingIndicator(client, 12345, interval=0.1):
            time.sleep(0.35)
            # With 0.1s interval, should have ~3 calls in 0.35s
            assert mock_send_typing.call_count >= 2

    @patch.object(TelegramClient, 'send_typing')
    def test_typing_indicator_sends_to_correct_chat(self, mock_send_typing):
        """Test typing indicator sends to correct chat ID."""
        mock_send_typing.return_value = True
        client = TelegramClient("test_token")

        with TypingIndicator(client, 67890):
            time.sleep(0.1)

        # Verify all calls were to the correct chat ID
        for call_args in mock_send_typing.call_args_list:
            assert call_args[0][0] == 67890

    @patch.object(TelegramClient, 'send_typing')
    def test_typing_indicator_exception_handling(self, mock_send_typing):
        """Test typing indicator stops even when exception occurs."""
        mock_send_typing.return_value = True
        client = TelegramClient("test_token")

        try:
            with TypingIndicator(client, 12345):
                time.sleep(0.1)
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Thread should still stop cleanly
        time.sleep(0.2)
        call_count_after_exit = mock_send_typing.call_count
        time.sleep(0.5)

        # Should not increase (or increase by at most 1)
        assert mock_send_typing.call_count <= call_count_after_exit + 1

    @patch.object(TelegramClient, 'send_typing')
    def test_typing_indicator_thread_cleanup(self, mock_send_typing):
        """Test typing indicator thread is properly cleaned up."""
        mock_send_typing.return_value = True
        client = TelegramClient("test_token")

        indicator = TypingIndicator(client, 12345)
        indicator.__enter__()

        # Verify thread is running
        assert indicator._thread is not None
        assert indicator._thread.is_alive()

        indicator.__exit__(None, None, None)

        # Verify thread stops within timeout
        time.sleep(0.2)
        assert not indicator._thread.is_alive()

    @patch.object(TelegramClient, 'send_typing')
    def test_typing_indicator_quick_exit(self, mock_send_typing):
        """Test typing indicator handles quick context exit."""
        mock_send_typing.return_value = True
        client = TelegramClient("test_token")

        with TypingIndicator(client, 12345):
            pass  # Exit immediately

        # Should handle quick exit without errors
        time.sleep(0.1)
