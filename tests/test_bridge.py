"""
Tests for the bridge.py CLI entry point.

Tests argument parsing, subcommand dispatching, and integration with the package.
"""

import json
import sys
from unittest.mock import MagicMock, patch, call
import pytest

# Import the main function from bridge.py
# We need to import from the module directly
sys.path.insert(0, "/home/luandro/Dev/digidem/AI/claudecode-telegram")
import bridge


@pytest.fixture
def minimal_valid_env(monkeypatch):
    """Minimal valid environment configuration."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token_123")
    monkeypatch.setenv("DEPLOYMENT_MODE", "tunnel")
    monkeypatch.setenv("WEBHOOK_DOMAIN", "example.com")
    return monkeypatch


@pytest.fixture
def mock_dependencies():
    """Mock all external dependencies."""
    with patch("bridge.BridgeConfig") as mock_config, \
         patch("bridge.run_server") as mock_run_server, \
         patch("bridge.TelegramClient") as mock_telegram, \
         patch("bridge.WebhookManager") as mock_webhook, \
         patch("bridge.StateManager") as mock_state:

        # Setup mock config
        config_instance = MagicMock()
        config_instance.bot_token = "test_token_123"
        config_instance.webhook_path = "secret_path_abc123"
        config_instance.claude_dir = "/tmp/claude"
        mock_config.from_env.return_value = config_instance

        yield {
            "config": mock_config,
            "config_instance": config_instance,
            "run_server": mock_run_server,
            "telegram": mock_telegram,
            "webhook": mock_webhook,
            "state": mock_state,
        }


class TestBridgeCLI:
    """Test suite for bridge.py CLI interface."""

    def test_no_subcommand_runs_server(self, minimal_valid_env, mock_dependencies):
        """Test that calling with no subcommand runs the server (default behavior)."""
        mock_dependencies["run_server"].return_value = 0

        with patch("sys.argv", ["bridge.py"]):
            result = bridge.main()

        assert result == 0
        mock_dependencies["run_server"].assert_called_once_with(
            mock_dependencies["config_instance"]
        )

    def test_set_webhook_command(self, minimal_valid_env, mock_dependencies):
        """Test set-webhook subcommand."""
        mock_webhook_instance = MagicMock()
        mock_webhook_instance.set_webhook.return_value = True
        mock_dependencies["webhook"].return_value = mock_webhook_instance

        with patch("sys.argv", ["bridge.py", "set-webhook", "--domain", "example.com"]):
            result = bridge.main()

        assert result == 0
        mock_webhook_instance.set_webhook.assert_called_once_with(
            "https://example.com/secret_path_abc123"
        )

    def test_set_webhook_uses_default_domain(self, minimal_valid_env, mock_dependencies):
        """Test set-webhook uses default domain from environment."""
        mock_webhook_instance = MagicMock()
        mock_webhook_instance.set_webhook.return_value = True
        mock_dependencies["webhook"].return_value = mock_webhook_instance

        minimal_valid_env.setenv("WEBHOOK_DOMAIN", "custom.example.com")

        with patch("sys.argv", ["bridge.py", "set-webhook"]):
            result = bridge.main()

        assert result == 0
        # Should use the domain from environment variable
        call_args = mock_webhook_instance.set_webhook.call_args[0][0]
        assert "custom.example.com" in call_args

    def test_set_webhook_failure(self, minimal_valid_env, mock_dependencies):
        """Test set-webhook returns 1 on failure."""
        mock_webhook_instance = MagicMock()
        mock_webhook_instance.set_webhook.return_value = False
        mock_dependencies["webhook"].return_value = mock_webhook_instance

        with patch("sys.argv", ["bridge.py", "set-webhook", "--domain", "example.com"]):
            result = bridge.main()

        assert result == 1

    def test_get_webhook_info_command(self, minimal_valid_env, mock_dependencies, capsys):
        """Test get-webhook-info subcommand."""
        mock_telegram_instance = MagicMock()
        mock_telegram_instance.get_webhook_info.return_value = {
            "url": "https://example.com/webhook",
            "has_custom_certificate": False,
            "pending_update_count": 0
        }
        mock_dependencies["telegram"].return_value = mock_telegram_instance

        with patch("sys.argv", ["bridge.py", "get-webhook-info"]):
            result = bridge.main()

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["url"] == "https://example.com/webhook"
        assert output["pending_update_count"] == 0

    def test_verify_webhook_command_success(self, minimal_valid_env, mock_dependencies):
        """Test verify-webhook subcommand returns 0 on success."""
        mock_webhook_instance = MagicMock()
        mock_webhook_instance.verify.return_value = True
        mock_dependencies["webhook"].return_value = mock_webhook_instance

        with patch("sys.argv", ["bridge.py", "verify-webhook"]):
            result = bridge.main()

        assert result == 0
        mock_webhook_instance.verify.assert_called_once()

    def test_verify_webhook_command_failure(self, minimal_valid_env, mock_dependencies):
        """Test verify-webhook subcommand returns 1 on failure."""
        mock_webhook_instance = MagicMock()
        mock_webhook_instance.verify.return_value = False
        mock_dependencies["webhook"].return_value = mock_webhook_instance

        with patch("sys.argv", ["bridge.py", "verify-webhook"]):
            result = bridge.main()

        assert result == 1

    def test_delete_webhook_command_success(self, minimal_valid_env, mock_dependencies):
        """Test delete-webhook subcommand returns 0 on success."""
        mock_webhook_instance = MagicMock()
        mock_webhook_instance.delete_webhook.return_value = True
        mock_dependencies["webhook"].return_value = mock_webhook_instance

        with patch("sys.argv", ["bridge.py", "delete-webhook"]):
            result = bridge.main()

        assert result == 0
        mock_webhook_instance.delete_webhook.assert_called_once()

    def test_delete_webhook_command_failure(self, minimal_valid_env, mock_dependencies):
        """Test delete-webhook subcommand returns 1 on failure."""
        mock_webhook_instance = MagicMock()
        mock_webhook_instance.delete_webhook.return_value = False
        mock_dependencies["webhook"].return_value = mock_webhook_instance

        with patch("sys.argv", ["bridge.py", "delete-webhook"]):
            result = bridge.main()

        assert result == 1

    def test_missing_bot_token(self, monkeypatch, mock_dependencies):
        """Test that missing bot token returns error code 1."""
        # Remove bot token
        mock_dependencies["config_instance"].bot_token = ""

        with patch("sys.argv", ["bridge.py"]):
            result = bridge.main()

        assert result == 1
        # run_server should not be called
        mock_dependencies["run_server"].assert_not_called()

    def test_minimal_instances_created_for_subcommands(
        self, minimal_valid_env, mock_dependencies
    ):
        """Test that subcommands create minimal instances, not full server."""
        mock_telegram_instance = MagicMock()
        mock_dependencies["telegram"].return_value = mock_telegram_instance
        mock_state_instance = MagicMock()
        mock_dependencies["state"].return_value = mock_state_instance
        mock_webhook_instance = MagicMock()
        mock_webhook_instance.verify.return_value = True
        mock_dependencies["webhook"].return_value = mock_webhook_instance

        with patch("sys.argv", ["bridge.py", "verify-webhook"]):
            result = bridge.main()

        # Should create minimal instances
        mock_dependencies["telegram"].assert_called_once_with("test_token_123")
        mock_dependencies["state"].assert_called_once()
        mock_dependencies["webhook"].assert_called_once()

        # Should NOT run the full server
        mock_dependencies["run_server"].assert_not_called()


class TestBridgeIntegration:
    """Integration tests for bridge.py with real imports (no mocking package internals)."""

    def test_import_bridge_module(self):
        """Test that bridge module can be imported successfully."""
        assert hasattr(bridge, "main")
        assert callable(bridge.main)

    def test_bridge_file_line_count(self):
        """Test that bridge.py is under 100 lines as required."""
        with open("/home/luandro/Dev/digidem/AI/claudecode-telegram/bridge.py") as f:
            lines = f.readlines()

        assert len(lines) < 100, f"bridge.py should be under 100 lines, got {len(lines)}"

    def test_bridge_imports_from_package(self):
        """Test that bridge.py imports from claudecode_telegram package."""
        with open("/home/luandro/Dev/digidem/AI/claudecode-telegram/bridge.py") as f:
            content = f.read()

        # Check for package imports
        assert "from claudecode_telegram.config import BridgeConfig" in content
        assert "from claudecode_telegram.server import run_server" in content
        assert "from claudecode_telegram.telegram import TelegramClient" in content
        assert "from claudecode_telegram.webhook import WebhookManager" in content
        assert "from claudecode_telegram.state import StateManager" in content
