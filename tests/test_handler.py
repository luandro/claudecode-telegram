"""Tests for TelegramWebhookHandler."""

import json
import time
from io import BytesIO
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from claudecode_telegram.handler import TelegramWebhookHandler, create_handler_factory
from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.tmux import TmuxController
from claudecode_telegram.state import StateManager
from claudecode_telegram.webhook import WebhookManager, WebhookStatusCache
from claudecode_telegram.commands.registry import CommandRegistry


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock(spec=BridgeConfig)
    config.webhook_path = "test_webhook_path"
    config.telegram_webhook_secret = "test_secret"
    config.allowed_user_ids = {123456, 789012}
    config.dm_allowed_user_id = 999999
    config.deployment_mode = "production"
    return config


@pytest.fixture
def mock_telegram():
    """Create a mock Telegram client."""
    return MagicMock(spec=TelegramClient)


@pytest.fixture
def mock_tmux():
    """Create a mock Tmux controller."""
    return MagicMock(spec=TmuxController)


@pytest.fixture
def mock_state():
    """Create a mock State manager."""
    state = MagicMock(spec=StateManager)
    state.get_webhook_url.return_value = "https://example.com/webhook"
    return state


@pytest.fixture
def mock_webhook():
    """Create a mock Webhook manager."""
    webhook = MagicMock(spec=WebhookManager)
    webhook.get_cached_status.return_value = WebhookStatusCache(
        configured=True,
        url="https://example.com/webhook",
        last_check=int(time.time()),
        last_error=None
    )
    return webhook


@pytest.fixture
def mock_commands():
    """Create a mock Command registry."""
    return MagicMock(spec=CommandRegistry)


@pytest.fixture
def handler_class(mock_config, mock_telegram, mock_tmux, mock_state, mock_webhook, mock_commands):
    """Create a handler class with mocked dependencies."""
    return create_handler_factory(
        config=mock_config,
        telegram=mock_telegram,
        tmux=mock_tmux,
        state=mock_state,
        webhook=mock_webhook,
        commands=mock_commands
    )


@pytest.fixture
def handler_instance(handler_class):
    """Create a handler instance for testing.

    We need to properly initialize the BaseHTTPRequestHandler with mock objects.
    """
    # Create mock request, client_address, and server
    mock_request = MagicMock()
    mock_request.makefile = MagicMock(side_effect=lambda *args: BytesIO())
    mock_client_address = ("127.0.0.1", 12345)
    mock_server = MagicMock()

    # Create handler instance
    handler = handler_class(mock_request, mock_client_address, mock_server)

    # Mock the wfile and rfile for testing
    handler.wfile = BytesIO()
    handler.rfile = BytesIO()

    return handler


class TestHandlerFactory:
    """Tests for create_handler_factory function."""

    def test_factory_creates_handler_class(self, handler_class):
        """Test that factory creates a valid handler class."""
        assert issubclass(handler_class, TelegramWebhookHandler)
        assert handler_class.config is not None
        assert handler_class.telegram is not None
        assert handler_class.tmux is not None
        assert handler_class.state is not None
        assert handler_class.webhook is not None
        assert handler_class.commands is not None

    def test_factory_sets_dependencies(self, mock_config, mock_telegram, mock_tmux,
                                      mock_state, mock_webhook, mock_commands):
        """Test that factory correctly sets all dependencies."""
        handler_class = create_handler_factory(
            config=mock_config,
            telegram=mock_telegram,
            tmux=mock_tmux,
            state=mock_state,
            webhook=mock_webhook,
            commands=mock_commands
        )

        assert handler_class.config is mock_config
        assert handler_class.telegram is mock_telegram
        assert handler_class.tmux is mock_tmux
        assert handler_class.state is mock_state
        assert handler_class.webhook is mock_webhook
        assert handler_class.commands is mock_commands


class TestPathValidation:
    """Tests for _validate_path method."""

    def test_validate_path_success(self, handler_instance):
        """Test path validation with correct path."""
        handler_instance.path = "/test_webhook_path"
        assert handler_instance._validate_path() is True

    def test_validate_path_with_leading_slash(self, handler_instance):
        """Test path validation handles leading slashes."""
        handler_instance.path = "test_webhook_path"
        assert handler_instance._validate_path() is True

    def test_validate_path_failure(self, handler_instance):
        """Test path validation with incorrect path."""
        handler_instance.path = "/wrong_path"
        assert handler_instance._validate_path() is False

    def test_validate_path_empty(self, handler_instance):
        """Test path validation with empty path."""
        handler_instance.path = "/"
        assert handler_instance._validate_path() is False


class TestSecretValidation:
    """Tests for _validate_secret method."""

    def test_validate_secret_success(self, handler_instance):
        """Test secret validation with correct secret."""
        handler_instance.headers = {"X-Telegram-Bot-Api-Secret-Token": "test_secret"}
        assert handler_instance._validate_secret() is True

    def test_validate_secret_failure(self, handler_instance):
        """Test secret validation with incorrect secret."""
        handler_instance.headers = {"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}
        assert handler_instance._validate_secret() is False

    def test_validate_secret_missing_header(self, handler_instance):
        """Test secret validation with missing header."""
        handler_instance.headers = {}
        assert handler_instance._validate_secret() is False

    def test_validate_secret_no_config(self, handler_instance, mock_config):
        """Test secret validation when no secret is configured."""
        mock_config.telegram_webhook_secret = ""
        assert handler_instance._validate_secret() is True


class TestUserAuthorization:
    """Tests for _is_user_allowed method."""

    def test_user_allowed_in_group(self, handler_instance):
        """Test that allowed user is authorized in group chat."""
        assert handler_instance._is_user_allowed(123456, "group") is True

    def test_user_not_allowed_in_group(self, handler_instance):
        """Test that unauthorized user is rejected in group chat."""
        assert handler_instance._is_user_allowed(111111, "group") is False

    def test_user_allowed_in_dm(self, handler_instance):
        """Test that configured DM user is authorized."""
        assert handler_instance._is_user_allowed(999999, "private") is True

    def test_user_not_allowed_in_dm(self, handler_instance):
        """Test that unauthorized user is rejected in DM."""
        assert handler_instance._is_user_allowed(123456, "private") is False

    def test_dm_not_configured(self, handler_instance, mock_config):
        """Test that DMs are rejected when no DM user is configured."""
        mock_config.dm_allowed_user_id = 0
        assert handler_instance._is_user_allowed(999999, "private") is False

    def test_no_restrictions_in_group(self, handler_instance, mock_config):
        """Test that all users allowed when no restrictions configured."""
        mock_config.allowed_user_ids = set()
        assert handler_instance._is_user_allowed(111111, "group") is True


class TestGetEndpoint:
    """Tests for do_GET method."""

    def test_health_endpoint_success(self, handler_instance, mock_webhook):
        """Test health check endpoint returns correct status."""
        handler_instance.path = "/health"
        handler_instance.send_response = MagicMock()
        handler_instance.send_header = MagicMock()
        handler_instance.end_headers = MagicMock()

        handler_instance.do_GET()

        handler_instance.send_response.assert_called_once_with(200)
        handler_instance.send_header.assert_called_once_with("Content-Type", "application/json")

        # Parse response
        response_data = json.loads(handler_instance.wfile.getvalue().decode())
        assert response_data["status"] == "healthy"
        assert response_data["operational"] is True
        assert "deployment_mode" in response_data

    def test_health_endpoint_with_error(self, handler_instance, mock_webhook):
        """Test health check endpoint with webhook error."""
        mock_webhook.get_cached_status.return_value = WebhookStatusCache(
            configured=False,
            url=None,
            last_check=int(time.time()),
            last_error="Test error"
        )

        handler_instance.path = "/health"
        handler_instance.send_response = MagicMock()
        handler_instance.send_header = MagicMock()
        handler_instance.end_headers = MagicMock()

        handler_instance.do_GET()

        response_data = json.loads(handler_instance.wfile.getvalue().decode())
        assert "webhook_last_error" in response_data
        assert response_data["webhook_last_error"] == "Test error"

    def test_webhook_endpoint_success(self, handler_instance):
        """Test webhook endpoint GET request."""
        handler_instance.path = "/test_webhook_path"
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        handler_instance.do_GET()

        handler_instance.send_response.assert_called_once_with(200)
        assert handler_instance.wfile.getvalue() == b"Claude-Telegram Bridge"

    def test_invalid_path_returns_404(self, handler_instance):
        """Test that invalid path returns 404."""
        handler_instance.path = "/invalid"
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        handler_instance.do_GET()

        handler_instance.send_response.assert_called_once_with(404)


class TestPostEndpoint:
    """Tests for do_POST method."""

    def test_post_invalid_path(self, handler_instance):
        """Test POST to invalid path returns 404."""
        handler_instance.path = "/invalid"
        handler_instance.headers = {"Content-Length": "0"}
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        handler_instance.do_POST()

        handler_instance.send_response.assert_called_once_with(404)

    def test_post_invalid_secret(self, handler_instance):
        """Test POST with invalid secret returns 401."""
        handler_instance.path = "/test_webhook_path"
        handler_instance.headers = {
            "Content-Length": "0",
            "X-Telegram-Bot-Api-Secret-Token": "wrong_secret"
        }
        handler_instance.client_address = ("127.0.0.1", 12345)
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        handler_instance.do_POST()

        handler_instance.send_response.assert_called_once_with(401)

    def test_post_callback_query(self, handler_instance, mock_telegram):
        """Test POST with callback_query update."""
        callback_data = {
            "callback_query": {
                "id": "callback123",
                "from": {"id": 123456},
                "message": {
                    "chat": {"id": 789, "type": "group"}
                },
                "data": "test_callback"
            }
        }

        handler_instance.path = "/test_webhook_path"
        handler_instance.headers = {
            "Content-Length": str(len(json.dumps(callback_data))),
            "X-Telegram-Bot-Api-Secret-Token": "test_secret"
        }
        handler_instance.rfile = BytesIO(json.dumps(callback_data).encode())
        handler_instance.client_address = ("127.0.0.1", 12345)
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        handler_instance.do_POST()

        # Should answer callback query
        mock_telegram.answer_callback.assert_called_once_with("callback123")
        # Should return 200 OK
        handler_instance.send_response.assert_called_once_with(200)

    def test_post_message(self, handler_instance):
        """Test POST with message update."""
        message_data = {
            "message": {
                "message_id": 1,
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"},
                "text": "Hello bot"
            }
        }

        handler_instance.path = "/test_webhook_path"
        handler_instance.headers = {
            "Content-Length": str(len(json.dumps(message_data))),
            "X-Telegram-Bot-Api-Secret-Token": "test_secret"
        }
        handler_instance.rfile = BytesIO(json.dumps(message_data).encode())
        handler_instance.client_address = ("127.0.0.1", 12345)
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        handler_instance.do_POST()

        # Should return 200 OK
        handler_instance.send_response.assert_called_once_with(200)

    def test_post_unauthorized_user(self, handler_instance, mock_telegram):
        """Test POST from unauthorized user is ignored."""
        message_data = {
            "message": {
                "message_id": 1,
                "from": {"id": 111111},  # Unauthorized user
                "chat": {"id": 789, "type": "group"},
                "text": "Hello bot"
            }
        }

        handler_instance.path = "/test_webhook_path"
        handler_instance.headers = {
            "Content-Length": str(len(json.dumps(message_data))),
            "X-Telegram-Bot-Api-Secret-Token": "test_secret"
        }
        handler_instance.rfile = BytesIO(json.dumps(message_data).encode())
        handler_instance.client_address = ("127.0.0.1", 12345)
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        with patch('builtins.print') as mock_print:
            handler_instance.do_POST()

            # Should log auth failure
            auth_fail_logged = any(
                "[AUTH_FAIL]" in str(call_args)
                for call_args in mock_print.call_args_list
            )
            assert auth_fail_logged

    def test_post_invalid_json(self, handler_instance):
        """Test POST with invalid JSON is handled gracefully."""
        handler_instance.path = "/test_webhook_path"
        handler_instance.headers = {
            "Content-Length": "10",
            "X-Telegram-Bot-Api-Secret-Token": "test_secret"
        }
        handler_instance.rfile = BytesIO(b"not json!")
        handler_instance.client_address = ("127.0.0.1", 12345)
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        with patch('builtins.print') as mock_print:
            handler_instance.do_POST()

            # Should log JSON error
            json_error_logged = any(
                "[JSON_ERROR]" in str(call_args)
                for call_args in mock_print.call_args_list
            )
            assert json_error_logged

        # Should still return 200 OK
        handler_instance.send_response.assert_called_once_with(200)

    def test_post_unknown_update_type(self, handler_instance):
        """Test POST with unknown update type is logged."""
        unknown_update = {
            "some_unknown_field": {"data": "value"}
        }

        handler_instance.path = "/test_webhook_path"
        handler_instance.headers = {
            "Content-Length": str(len(json.dumps(unknown_update))),
            "X-Telegram-Bot-Api-Secret-Token": "test_secret"
        }
        handler_instance.rfile = BytesIO(json.dumps(unknown_update).encode())
        handler_instance.client_address = ("127.0.0.1", 12345)
        handler_instance.send_response = MagicMock()
        handler_instance.end_headers = MagicMock()

        with patch('builtins.print') as mock_print:
            handler_instance.do_POST()

            # Should log unknown update
            unknown_logged = any(
                "[UNKNOWN_UPDATE]" in str(call_args)
                for call_args in mock_print.call_args_list
            )
            assert unknown_logged


class TestCallbackHandling:
    """Tests for handle_callback method."""

    def test_callback_without_user_id(self, handler_instance, mock_telegram):
        """Test callback query without user ID."""
        callback_query = {
            "id": "callback123",
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "test"
        }

        handler_instance.handle_callback(callback_query)

        # Should still answer callback
        mock_telegram.answer_callback.assert_called_once_with("callback123")

    def test_callback_without_callback_id(self, handler_instance, mock_telegram):
        """Test callback query without callback ID."""
        callback_query = {
            "from": {"id": 123456},
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "test"
        }

        handler_instance.handle_callback(callback_query)

        # Should not attempt to answer callback
        mock_telegram.answer_callback.assert_not_called()

    def test_callback_resume_session(self, handler_instance, mock_tmux, mock_telegram):
        """Test callback for resuming a specific session."""
        callback_query = {
            "id": "callback123",
            "from": {"id": 123456},
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "resume:abc123def456"
        }

        # Mock tmux exists
        mock_tmux.exists.return_value = True

        handler_instance.handle_callback(callback_query)

        # Should answer callback
        mock_telegram.answer_callback.assert_called_once_with("callback123")

        # Should exit and run resume command
        mock_tmux.exit_and_run.assert_called_once_with(
            "claude --resume abc123def456 --dangerously-skip-permissions"
        )

        # Should send confirmation message
        mock_telegram.send_message.assert_called_once()
        assert "Resuming" in mock_telegram.send_message.call_args[0][1]

    def test_callback_continue_recent(self, handler_instance, mock_tmux, mock_telegram):
        """Test callback for continuing most recent session."""
        callback_query = {
            "id": "callback123",
            "from": {"id": 123456},
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "continue_recent"
        }

        # Mock tmux exists
        mock_tmux.exists.return_value = True

        handler_instance.handle_callback(callback_query)

        # Should answer callback
        mock_telegram.answer_callback.assert_called_once_with("callback123")

        # Should exit and run continue command
        mock_tmux.exit_and_run.assert_called_once_with(
            "claude --continue --dangerously-skip-permissions"
        )

        # Should send confirmation message
        mock_telegram.send_message.assert_called_once()
        assert "Continuing" in mock_telegram.send_message.call_args[0][1]

    def test_callback_no_tmux_sends_error(self, handler_instance, mock_tmux, mock_telegram):
        """Test callback sends error when tmux not available."""
        callback_query = {
            "id": "callback123",
            "from": {"id": 123456},
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "continue_recent"
        }

        # Mock tmux does not exist
        mock_tmux.exists.return_value = False

        handler_instance.handle_callback(callback_query)

        # Should answer callback
        mock_telegram.answer_callback.assert_called_once_with("callback123")

        # Should send error message
        mock_telegram.send_message.assert_called_once_with(789, "tmux session not found")

    def test_callback_tmux_error_sends_message(self, handler_instance, mock_tmux, mock_telegram):
        """Test that tmux error in callback sends error message."""
        callback_query = {
            "id": "callback123",
            "from": {"id": 123456},
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "resume:abc123"
        }

        # Mock tmux exists but exit_and_run raises error
        mock_tmux.exists.return_value = True
        mock_tmux.exit_and_run.side_effect = RuntimeError("Session exit failed")

        handler_instance.handle_callback(callback_query)

        # Should send error message
        mock_telegram.send_message.assert_called_once()
        assert "Error resuming session" in mock_telegram.send_message.call_args[0][1]

    def test_callback_invalid_resume_format(self, handler_instance, mock_telegram):
        """Test callback with invalid resume format."""
        callback_query = {
            "id": "callback123",
            "from": {"id": 123456},
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "resume:"  # Missing session ID
        }

        with patch('builtins.print') as mock_print:
            handler_instance.handle_callback(callback_query)

            # Should log error
            error_logged = any(
                "[CALLBACK_ERROR]" in str(call_args)
                for call_args in mock_print.call_args_list
            )
            assert error_logged

    def test_callback_unknown_data(self, handler_instance, mock_telegram):
        """Test callback with unknown data pattern."""
        callback_query = {
            "id": "callback123",
            "from": {"id": 123456},
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "unknown_action"
        }

        # Mock tmux exists
        handler_instance.tmux.exists.return_value = True

        with patch('builtins.print') as mock_print:
            handler_instance.handle_callback(callback_query)

            # Should log unknown callback
            unknown_logged = any(
                "[CALLBACK_UNKNOWN]" in str(call_args)
                for call_args in mock_print.call_args_list
            )
            assert unknown_logged

    def test_callback_unauthorized_user(self, handler_instance, mock_telegram):
        """Test that unauthorized user callback is silently ignored."""
        callback_query = {
            "id": "callback123",
            "from": {"id": 111111},  # Unauthorized user
            "message": {"chat": {"id": 789, "type": "group"}},
            "data": "continue_recent"
        }

        handler_instance.handle_callback(callback_query)

        # Should answer callback
        mock_telegram.answer_callback.assert_called_once_with("callback123")

        # Should not send message or interact with tmux
        assert mock_telegram.send_message.call_count == 0

    def test_callback_without_chat_id(self, handler_instance, mock_telegram):
        """Test callback without chat ID is handled gracefully."""
        callback_query = {
            "id": "callback123",
            "from": {"id": 123456},
            "message": {"chat": {}},
            "data": "continue_recent"
        }

        with patch('builtins.print') as mock_print:
            handler_instance.handle_callback(callback_query)

            # Should answer callback
            mock_telegram.answer_callback.assert_called_once_with("callback123")

            # Should log error
            error_logged = any(
                "[CALLBACK_ERROR]" in str(call_args) and "Missing chat_id" in str(call_args)
                for call_args in mock_print.call_args_list
            )
            assert error_logged


class TestMessageHandling:
    """Tests for handle_message method."""

    def test_message_without_text(self, handler_instance):
        """Test message without text is ignored."""
        update = {
            "message": {
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"}
            }
        }

        with patch('builtins.print') as mock_print:
            handler_instance.handle_message(update)

            # Should log MESSAGE but return early (no state or telegram calls)
            message_logged = any(
                "[MESSAGE]" in str(call_args)
                for call_args in mock_print.call_args_list
            )
            assert message_logged

    def test_message_without_chat_id(self, handler_instance):
        """Test message without chat ID is ignored."""
        update = {
            "message": {
                "from": {"id": 123456},
                "text": "Hello",
                "chat": {}
            }
        }

        # Should not raise exception
        handler_instance.handle_message(update)

    def test_message_saves_chat_id(self, handler_instance, mock_state, mock_telegram):
        """Test that message handling saves chat_id to state."""
        update = {
            "message": {
                "message_id": 1,
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"},
                "text": "Hello"
            }
        }

        handler_instance.handle_message(update)

        # Should save chat_id to state
        mock_state.set_chat_id.assert_called_once_with(789)

    def test_message_sets_reaction(self, handler_instance, mock_telegram):
        """Test that message handling sets reaction emoji."""
        update = {
            "message": {
                "message_id": 1,
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"},
                "text": "Hello"
            }
        }

        handler_instance.handle_message(update)

        # Should set reaction
        mock_telegram.set_reaction.assert_called_once_with(789, 1, "👀")

    def test_command_message_dispatches_to_registry(self, handler_instance, mock_commands, mock_telegram):
        """Test that command message is dispatched to command registry."""
        update = {
            "message": {
                "message_id": 1,
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"},
                "text": "/start"
            }
        }

        # Mock command execution to return a reply
        mock_commands.execute.return_value = "Welcome!"

        handler_instance.handle_message(update)

        # Should execute command through registry
        mock_commands.execute.assert_called_once()
        call_args = mock_commands.execute.call_args
        assert call_args[0][0] == "/start"  # Command name
        assert call_args[0][1].chat_id == 789  # CommandContext

        # Should send reply
        mock_telegram.send_message.assert_called_once_with(789, "Welcome!")

    def test_command_blocked_sends_error(self, handler_instance, mock_commands, mock_telegram):
        """Test that blocked command sends error message."""
        update = {
            "message": {
                "message_id": 1,
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"},
                "text": "/mcp"
            }
        }

        # Mock command execution to raise ValueError
        mock_commands.execute.side_effect = ValueError("Command '/mcp' is blocked (interactive only)")

        handler_instance.handle_message(update)

        # Should send error message
        mock_telegram.send_message.assert_called_once()
        assert "Error:" in mock_telegram.send_message.call_args[0][1]
        assert "blocked" in mock_telegram.send_message.call_args[0][1]

    def test_non_command_sends_to_tmux(self, handler_instance, mock_tmux, mock_state):
        """Test that non-command message is sent to tmux."""
        update = {
            "message": {
                "message_id": 1,
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"},
                "text": "Hello Claude"
            }
        }

        # Mock tmux exists
        mock_tmux.exists.return_value = True

        handler_instance.handle_message(update)

        # Should set pending flag
        mock_state.set_pending.assert_called_once()

        # Should send to tmux
        mock_tmux.send_text.assert_called_once_with("Hello Claude", press_enter=True)

    def test_non_command_no_tmux_sends_error(self, handler_instance, mock_tmux, mock_telegram):
        """Test that non-command message sends error when tmux not available."""
        update = {
            "message": {
                "message_id": 1,
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"},
                "text": "Hello Claude"
            }
        }

        # Mock tmux does not exist
        mock_tmux.exists.return_value = False

        handler_instance.handle_message(update)

        # Should send error message
        mock_telegram.send_message.assert_called_once_with(789, "tmux session not found")

    def test_non_command_tmux_error_sends_message(self, handler_instance, mock_tmux, mock_telegram):
        """Test that tmux error sends error message to user."""
        update = {
            "message": {
                "message_id": 1,
                "from": {"id": 123456},
                "chat": {"id": 789, "type": "group"},
                "text": "Hello Claude"
            }
        }

        # Mock tmux exists but send_text raises error
        mock_tmux.exists.return_value = True
        mock_tmux.send_text.side_effect = RuntimeError("Connection failed")

        handler_instance.handle_message(update)

        # Should send error message
        mock_telegram.send_message.assert_called_once()
        assert "Error sending to Claude" in mock_telegram.send_message.call_args[0][1]

    def test_unauthorized_user_message(self, handler_instance, mock_state, mock_telegram):
        """Test that unauthorized user message is silently ignored."""
        update = {
            "message": {
                "message_id": 1,
                "from": {"id": 111111},  # Unauthorized user
                "chat": {"id": 789, "type": "group"},
                "text": "Hello"
            }
        }

        handler_instance.handle_message(update)

        # Should not save chat_id
        mock_state.set_chat_id.assert_not_called()

        # Should not set reaction
        mock_telegram.set_reaction.assert_not_called()
