"""
Tests for conftest.py fixtures to ensure they work correctly.

Verifies that all pytest fixtures provide the expected structure and behavior.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.tmux import TmuxController
from claudecode_telegram.state import StateManager


class TestConfigFixture:
    """Test the config fixture."""

    def test_config_is_bridge_config(self, config):
        """Config fixture should return a BridgeConfig instance."""
        assert isinstance(config, BridgeConfig)

    def test_config_has_test_values(self, config):
        """Config fixture should have safe test values."""
        assert config.bot_token == "test_bot_token_123"
        assert config.tmux_session == "test-session"
        assert config.claude_dir == Path("/tmp/test-claude")
        assert config.webhook_auto_setup is False
        assert config.allowed_user_ids == {123456789, 987654321}
        assert config.dm_allowed_user_id == 123456789

    def test_config_validates_successfully(self, config):
        """Config fixture should pass validation."""
        errors = config.validate()
        assert errors == []


class TestMockTelegramFixture:
    """Test the mock_telegram fixture."""

    def test_mock_telegram_is_mock(self, mock_telegram):
        """Mock telegram fixture should be a Mock instance."""
        assert isinstance(mock_telegram, Mock)

    def test_mock_telegram_api_call(self, mock_telegram):
        """Mock telegram should have working api_call mock."""
        result = mock_telegram.api_call("test_method", {})
        assert result["ok"] is True
        assert "result" in result

    def test_mock_telegram_send_message(self, mock_telegram):
        """Mock telegram should have working send_message mock."""
        result = mock_telegram.send_message(123456789, "test")
        assert result["ok"] is True
        assert result["result"]["message_id"] == 1

    def test_mock_telegram_set_reaction(self, mock_telegram):
        """Mock telegram should have working set_reaction mock."""
        result = mock_telegram.set_reaction(123456789, 1, "👍")
        assert result is True

    def test_mock_telegram_send_typing(self, mock_telegram):
        """Mock telegram should have working send_typing mock."""
        result = mock_telegram.send_typing(123456789)
        assert result is True

    def test_mock_telegram_answer_callback(self, mock_telegram):
        """Mock telegram should have working answer_callback mock."""
        result = mock_telegram.answer_callback("callback_id")
        assert result is True

    def test_mock_telegram_set_webhook(self, mock_telegram):
        """Mock telegram should have working set_webhook mock."""
        result = mock_telegram.set_webhook("https://example.com/webhook")
        assert result is True

    def test_mock_telegram_get_webhook_info(self, mock_telegram):
        """Mock telegram should have working get_webhook_info mock."""
        result = mock_telegram.get_webhook_info()
        assert "url" in result
        assert "pending_update_count" in result

    def test_mock_telegram_delete_webhook(self, mock_telegram):
        """Mock telegram should have working delete_webhook mock."""
        result = mock_telegram.delete_webhook()
        assert result is True

    def test_mock_telegram_set_commands(self, mock_telegram):
        """Mock telegram should have working set_commands mock."""
        result = mock_telegram.set_commands([])
        assert result is True

    def test_mock_telegram_start_typing_loop(self, mock_telegram):
        """Mock telegram should have working start_typing_loop mock."""
        thread = mock_telegram.start_typing_loop(123456789, Path("/tmp/stop"))
        assert thread.is_alive() is True


class TestMockTmuxFixture:
    """Test the mock_tmux fixture."""

    def test_mock_tmux_is_mock(self, mock_tmux):
        """Mock tmux fixture should be a Mock instance."""
        assert isinstance(mock_tmux, Mock)

    def test_mock_tmux_exists(self, mock_tmux):
        """Mock tmux should have working exists mock."""
        assert mock_tmux.exists() is True

    def test_mock_tmux_send_keys(self, mock_tmux):
        """Mock tmux should have working send_keys mock."""
        result = mock_tmux.send_keys("test text")
        assert result is None

    def test_mock_tmux_send_enter(self, mock_tmux):
        """Mock tmux should have working send_enter mock."""
        result = mock_tmux.send_enter()
        assert result is None

    def test_mock_tmux_send_escape(self, mock_tmux):
        """Mock tmux should have working send_escape mock."""
        result = mock_tmux.send_escape()
        assert result is None

    def test_mock_tmux_send_text(self, mock_tmux):
        """Mock tmux should have working send_text mock."""
        result = mock_tmux.send_text("test text")
        assert result is None

    def test_mock_tmux_interrupt(self, mock_tmux):
        """Mock tmux should have working interrupt mock."""
        result = mock_tmux.interrupt()
        assert result is None

    def test_mock_tmux_interrupt_and_send(self, mock_tmux):
        """Mock tmux should have working interrupt_and_send mock."""
        result = mock_tmux.interrupt_and_send("test text")
        assert result is None

    def test_mock_tmux_exit_and_run(self, mock_tmux):
        """Mock tmux should have working exit_and_run mock."""
        result = mock_tmux.exit_and_run("command")
        assert result is None

    def test_mock_tmux_capture_pane(self, mock_tmux):
        """Mock tmux should have working capture_pane mock."""
        result = mock_tmux.capture_pane()
        assert result == ""

    def test_mock_tmux_extract_response(self, mock_tmux):
        """Mock tmux should have working extract_response mock."""
        result = mock_tmux.extract_response()
        assert result is None


class TestTempStateDirFixture:
    """Test the temp_state_dir fixture."""

    def test_temp_state_dir_is_state_manager(self, temp_state_dir):
        """Temp state dir fixture should return a StateManager instance."""
        assert isinstance(temp_state_dir, StateManager)

    def test_temp_state_dir_is_temporary(self, temp_state_dir):
        """Temp state dir should use a temporary directory."""
        assert temp_state_dir.claude_dir.exists()
        assert "/tmp" in str(temp_state_dir.claude_dir) or "pytest" in str(temp_state_dir.claude_dir)

    def test_temp_state_dir_file_operations(self, temp_state_dir):
        """Temp state dir should support file operations."""
        # Test chat_id operations
        temp_state_dir.set_chat_id(123456789)
        assert temp_state_dir.get_chat_id() == 123456789

        # Test pending operations
        temp_state_dir.set_pending()
        assert temp_state_dir.is_pending() is True

        # Test webhook_url operations
        temp_state_dir.set_webhook_url("https://example.com/webhook")
        assert temp_state_dir.get_webhook_url() == "https://example.com/webhook"


class TestSampleUpdateFixture:
    """Test the sample_update fixture."""

    def test_sample_update_structure(self, sample_update):
        """Sample update should have expected structure."""
        assert "update_id" in sample_update
        assert "message" in sample_update

    def test_sample_update_message_content(self, sample_update):
        """Sample update message should have expected content."""
        message = sample_update["message"]
        assert "message_id" in message
        assert "from" in message
        assert "chat" in message
        assert "text" in message
        assert "date" in message

    def test_sample_update_user_info(self, sample_update):
        """Sample update should have valid user info."""
        user = sample_update["message"]["from"]
        assert user["id"] == 123456789
        assert user["is_bot"] is False
        assert user["first_name"] == "Test"
        assert user["username"] == "testuser"

    def test_sample_update_chat_info(self, sample_update):
        """Sample update should have valid chat info."""
        chat = sample_update["message"]["chat"]
        assert chat["id"] == 123456789
        assert chat["type"] == "private"

    def test_sample_update_text_content(self, sample_update):
        """Sample update should have text content."""
        assert sample_update["message"]["text"] == "Hello, Claude!"


class TestSampleCallbackFixture:
    """Test the sample_callback fixture."""

    def test_sample_callback_structure(self, sample_callback):
        """Sample callback should have expected structure."""
        assert "update_id" in sample_callback
        assert "callback_query" in sample_callback

    def test_sample_callback_query_content(self, sample_callback):
        """Sample callback query should have expected content."""
        callback = sample_callback["callback_query"]
        assert "id" in callback
        assert "from" in callback
        assert "message" in callback
        assert "data" in callback
        assert "chat_instance" in callback

    def test_sample_callback_user_info(self, sample_callback):
        """Sample callback should have valid user info."""
        user = sample_callback["callback_query"]["from"]
        assert user["id"] == 123456789
        assert user["is_bot"] is False
        assert user["first_name"] == "Test"
        assert user["username"] == "testuser"

    def test_sample_callback_message_info(self, sample_callback):
        """Sample callback should have valid message info."""
        message = sample_callback["callback_query"]["message"]
        assert message["message_id"] == 2
        assert "reply_markup" in message
        assert "inline_keyboard" in message["reply_markup"]

    def test_sample_callback_data(self, sample_callback):
        """Sample callback should have callback data."""
        assert sample_callback["callback_query"]["data"] == "option_1"

    def test_sample_callback_id(self, sample_callback):
        """Sample callback should have callback query id."""
        assert sample_callback["callback_query"]["id"] == "callback_id_123"
