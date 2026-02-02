"""
Tests for the StateManager class.
"""
import time
from pathlib import Path

import pytest

from claudecode_telegram.state import StateManager


@pytest.fixture
def temp_claude_dir(tmp_path):
    """Create a temporary Claude directory for testing."""
    return tmp_path / ".claude"


@pytest.fixture
def state_manager(temp_claude_dir):
    """Create a StateManager instance with a temporary directory."""
    return StateManager(temp_claude_dir)


class TestStateManagerInit:
    """Tests for StateManager initialization."""

    def test_init_creates_path_object(self, temp_claude_dir):
        """Test that __init__ converts string path to Path object."""
        manager = StateManager(str(temp_claude_dir))
        assert isinstance(manager.claude_dir, Path)
        assert manager.claude_dir == temp_claude_dir

    def test_init_with_path_object(self, temp_claude_dir):
        """Test that __init__ accepts Path objects."""
        manager = StateManager(temp_claude_dir)
        assert isinstance(manager.claude_dir, Path)
        assert manager.claude_dir == temp_claude_dir


class TestStateManagerProperties:
    """Tests for StateManager file path properties."""

    def test_chat_id_file_path(self, state_manager, temp_claude_dir):
        """Test chat_id_file property returns correct path."""
        expected = temp_claude_dir / "telegram_chat_id"
        assert state_manager.chat_id_file == expected

    def test_pending_file_path(self, state_manager, temp_claude_dir):
        """Test pending_file property returns correct path."""
        expected = temp_claude_dir / "telegram_pending"
        assert state_manager.pending_file == expected

    def test_webhook_state_file_path(self, state_manager, temp_claude_dir):
        """Test webhook_state_file property returns correct path."""
        expected = temp_claude_dir / "telegram_webhook_url"
        assert state_manager.webhook_state_file == expected

    def test_tunnel_url_file_path(self, state_manager, temp_claude_dir):
        """Test tunnel_url_file property returns correct path."""
        expected = temp_claude_dir / "cloudflared_tunnel_url"
        assert state_manager.tunnel_url_file == expected

    def test_history_file_path(self, state_manager, temp_claude_dir):
        """Test history_file property returns correct path."""
        expected = temp_claude_dir / "history.jsonl"
        assert state_manager.history_file == expected


class TestChatIdOperations:
    """Tests for chat ID state operations."""

    def test_get_chat_id_returns_none_when_file_missing(self, state_manager):
        """Test get_chat_id returns None when file doesn't exist."""
        assert state_manager.get_chat_id() is None

    def test_set_and_get_chat_id(self, state_manager):
        """Test setting and retrieving chat ID."""
        chat_id = 123456789
        state_manager.set_chat_id(chat_id)
        assert state_manager.get_chat_id() == chat_id

    def test_set_chat_id_creates_directory(self, state_manager, temp_claude_dir):
        """Test set_chat_id creates parent directory if it doesn't exist."""
        assert not temp_claude_dir.exists()
        state_manager.set_chat_id(123456789)
        assert temp_claude_dir.exists()
        assert state_manager.chat_id_file.exists()

    def test_get_chat_id_handles_invalid_format(self, state_manager):
        """Test get_chat_id returns None for non-integer content."""
        state_manager.chat_id_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.chat_id_file.write_text("not_a_number")
        assert state_manager.get_chat_id() is None

    def test_get_chat_id_handles_empty_file(self, state_manager):
        """Test get_chat_id returns None for empty file."""
        state_manager.chat_id_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.chat_id_file.write_text("")
        assert state_manager.get_chat_id() is None

    def test_get_chat_id_strips_whitespace(self, state_manager):
        """Test get_chat_id strips whitespace from file content."""
        state_manager.chat_id_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.chat_id_file.write_text("  987654321  \n")
        assert state_manager.get_chat_id() == 987654321


class TestPendingOperations:
    """Tests for pending message state operations."""

    def test_is_pending_returns_false_when_file_missing(self, state_manager):
        """Test is_pending returns False when file doesn't exist."""
        assert state_manager.is_pending() is False

    def test_set_and_is_pending(self, state_manager):
        """Test setting pending flag and checking it."""
        state_manager.set_pending()
        assert state_manager.is_pending() is True

    def test_is_pending_respects_max_age(self, state_manager):
        """Test is_pending respects max_age_seconds parameter."""
        # Write an old timestamp
        old_timestamp = int(time.time()) - 700  # 700 seconds ago
        state_manager.pending_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.pending_file.write_text(str(old_timestamp))

        # Should be expired with default 600 seconds
        assert state_manager.is_pending(max_age_seconds=600) is False

        # Should be valid with 800 seconds
        assert state_manager.is_pending(max_age_seconds=800) is True

    def test_clear_pending_removes_file(self, state_manager):
        """Test clear_pending removes the pending file."""
        state_manager.set_pending()
        assert state_manager.pending_file.exists()

        state_manager.clear_pending()
        assert not state_manager.pending_file.exists()

    def test_clear_pending_when_file_missing(self, state_manager):
        """Test clear_pending doesn't raise error when file doesn't exist."""
        state_manager.clear_pending()  # Should not raise

    def test_is_pending_handles_invalid_format(self, state_manager):
        """Test is_pending returns False for non-integer timestamp."""
        state_manager.pending_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.pending_file.write_text("not_a_timestamp")
        assert state_manager.is_pending() is False

    def test_set_pending_creates_directory(self, state_manager, temp_claude_dir):
        """Test set_pending creates parent directory if it doesn't exist."""
        assert not temp_claude_dir.exists()
        state_manager.set_pending()
        assert temp_claude_dir.exists()
        assert state_manager.pending_file.exists()


class TestWebhookUrlOperations:
    """Tests for webhook URL state operations."""

    def test_get_webhook_url_returns_none_when_file_missing(self, state_manager):
        """Test get_webhook_url returns None when file doesn't exist."""
        assert state_manager.get_webhook_url() is None

    def test_set_and_get_webhook_url(self, state_manager):
        """Test setting and retrieving webhook URL."""
        url = "https://example.com/webhook"
        state_manager.set_webhook_url(url)
        assert state_manager.get_webhook_url() == url

    def test_clear_webhook_url_removes_file(self, state_manager):
        """Test clear_webhook_url removes the webhook URL file."""
        state_manager.set_webhook_url("https://example.com/webhook")
        assert state_manager.webhook_state_file.exists()

        state_manager.clear_webhook_url()
        assert not state_manager.webhook_state_file.exists()

    def test_clear_webhook_url_when_file_missing(self, state_manager):
        """Test clear_webhook_url doesn't raise error when file doesn't exist."""
        state_manager.clear_webhook_url()  # Should not raise

    def test_set_webhook_url_creates_directory(self, state_manager, temp_claude_dir):
        """Test set_webhook_url creates parent directory if it doesn't exist."""
        assert not temp_claude_dir.exists()
        state_manager.set_webhook_url("https://example.com/webhook")
        assert temp_claude_dir.exists()
        assert state_manager.webhook_state_file.exists()

    def test_get_webhook_url_strips_whitespace(self, state_manager):
        """Test get_webhook_url strips whitespace from file content."""
        state_manager.webhook_state_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.webhook_state_file.write_text("  https://example.com/webhook  \n")
        assert state_manager.get_webhook_url() == "https://example.com/webhook"

    def test_get_webhook_url_handles_empty_file(self, state_manager):
        """Test get_webhook_url returns None for empty file."""
        state_manager.webhook_state_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.webhook_state_file.write_text("")
        assert state_manager.get_webhook_url() is None


class TestTunnelUrlOperations:
    """Tests for tunnel URL state operations."""

    def test_get_tunnel_url_returns_none_when_file_missing(self, state_manager):
        """Test get_tunnel_url returns None when file doesn't exist."""
        assert state_manager.get_tunnel_url() is None

    def test_get_tunnel_url_reads_file(self, state_manager):
        """Test get_tunnel_url reads the tunnel URL file."""
        url = "https://example.trycloudflare.com"
        state_manager.tunnel_url_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.tunnel_url_file.write_text(url)
        assert state_manager.get_tunnel_url() == url

    def test_get_tunnel_url_strips_whitespace(self, state_manager):
        """Test get_tunnel_url strips whitespace from file content."""
        state_manager.tunnel_url_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.tunnel_url_file.write_text("  https://example.trycloudflare.com  \n")
        assert state_manager.get_tunnel_url() == "https://example.trycloudflare.com"

    def test_get_tunnel_url_handles_empty_file(self, state_manager):
        """Test get_tunnel_url returns None for empty file."""
        state_manager.tunnel_url_file.parent.mkdir(parents=True, exist_ok=True)
        state_manager.tunnel_url_file.write_text("")
        assert state_manager.get_tunnel_url() is None


class TestPrivateMethods:
    """Tests for private helper methods."""

    def test_read_text_file_nonexistent(self, state_manager, temp_claude_dir):
        """Test _read_text_file returns None for nonexistent file."""
        nonexistent = temp_claude_dir / "nonexistent.txt"
        assert state_manager._read_text_file(nonexistent) is None

    def test_write_text_file_creates_parent_dirs(self, state_manager, temp_claude_dir):
        """Test _write_text_file creates parent directories."""
        nested_file = temp_claude_dir / "subdir" / "test.txt"
        assert state_manager._write_text_file(nested_file, "test content")
        assert nested_file.exists()
        assert nested_file.read_text() == "test content"

    def test_write_text_file_returns_true_on_success(self, state_manager, temp_claude_dir):
        """Test _write_text_file returns True on success."""
        test_file = temp_claude_dir / "test.txt"
        result = state_manager._write_text_file(test_file, "content")
        assert result is True

    def test_delete_file_removes_existing_file(self, state_manager, temp_claude_dir):
        """Test _delete_file removes an existing file."""
        test_file = temp_claude_dir / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("content")

        state_manager._delete_file(test_file)
        assert not test_file.exists()

    def test_delete_file_handles_nonexistent_file(self, state_manager, temp_claude_dir):
        """Test _delete_file doesn't raise error for nonexistent file."""
        nonexistent = temp_claude_dir / "nonexistent.txt"
        state_manager._delete_file(nonexistent)  # Should not raise


class TestIntegration:
    """Integration tests for StateManager."""

    def test_full_workflow(self, state_manager):
        """Test a complete workflow with multiple state operations."""
        # Set chat ID
        chat_id = 123456789
        state_manager.set_chat_id(chat_id)
        assert state_manager.get_chat_id() == chat_id

        # Set pending
        state_manager.set_pending()
        assert state_manager.is_pending() is True

        # Set webhook URL
        webhook_url = "https://example.com/webhook"
        state_manager.set_webhook_url(webhook_url)
        assert state_manager.get_webhook_url() == webhook_url

        # Clear pending
        state_manager.clear_pending()
        assert state_manager.is_pending() is False

        # Clear webhook
        state_manager.clear_webhook_url()
        assert state_manager.get_webhook_url() is None

        # Chat ID should still be there
        assert state_manager.get_chat_id() == chat_id

    def test_multiple_instances_share_state(self, temp_claude_dir):
        """Test that multiple StateManager instances share the same state."""
        manager1 = StateManager(temp_claude_dir)
        manager2 = StateManager(temp_claude_dir)

        # Set chat ID with manager1
        manager1.set_chat_id(123456789)

        # Read with manager2
        assert manager2.get_chat_id() == 123456789
