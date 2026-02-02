"""Tests for server setup and lifecycle management."""

import shutil
import tempfile
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call
import pytest

from claudecode_telegram.server import setup_hooks, create_server, run_server
from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.webhook import WebhookManager
from claudecode_telegram.commands.registry import CommandRegistry


class TestSetupHooks:
    """Tests for setup_hooks function."""

    def test_setup_hooks_success(self, tmp_path):
        """Test successful hook installation."""
        # Create source directory with hook
        source_dir = tmp_path / "source"
        hooks_src_dir = source_dir / "hooks"
        hooks_src_dir.mkdir(parents=True)
        hook_src = hooks_src_dir / "send-to-telegram.sh"
        hook_src.write_text("#!/bin/bash\necho 'test hook'")

        # Create claude directory
        claude_dir = tmp_path / "claude"

        # Run setup_hooks
        setup_hooks(claude_dir, source_dir)

        # Verify hook was copied
        hook_dest = claude_dir / "hooks" / "send-to-telegram.sh"
        assert hook_dest.exists()
        assert hook_dest.read_text() == "#!/bin/bash\necho 'test hook'"

        # Verify permissions (executable)
        assert hook_dest.stat().st_mode & 0o111  # At least one execute bit set

    def test_setup_hooks_creates_hooks_directory(self, tmp_path):
        """Test that hooks directory is created if it doesn't exist."""
        # Create source directory with hook
        source_dir = tmp_path / "source"
        hooks_src_dir = source_dir / "hooks"
        hooks_src_dir.mkdir(parents=True)
        hook_src = hooks_src_dir / "send-to-telegram.sh"
        hook_src.write_text("#!/bin/bash\necho 'test'")

        # Create claude directory without hooks subdir
        claude_dir = tmp_path / "claude"
        claude_dir.mkdir()

        # Run setup_hooks
        setup_hooks(claude_dir, source_dir)

        # Verify hooks directory was created
        assert (claude_dir / "hooks").exists()
        assert (claude_dir / "hooks").is_dir()

    def test_setup_hooks_missing_source(self, tmp_path):
        """Test that FileNotFoundError is raised when source hook doesn't exist."""
        source_dir = tmp_path / "source"
        claude_dir = tmp_path / "claude"

        with pytest.raises(FileNotFoundError) as exc_info:
            setup_hooks(claude_dir, source_dir)

        assert "Hook source not found" in str(exc_info.value)
        assert str(source_dir / "hooks" / "send-to-telegram.sh") in str(exc_info.value)

    def test_setup_hooks_overwrites_existing(self, tmp_path):
        """Test that existing hook is overwritten."""
        # Create source directory with hook
        source_dir = tmp_path / "source"
        hooks_src_dir = source_dir / "hooks"
        hooks_src_dir.mkdir(parents=True)
        hook_src = hooks_src_dir / "send-to-telegram.sh"
        hook_src.write_text("#!/bin/bash\necho 'new content'")

        # Create claude directory with old hook
        claude_dir = tmp_path / "claude"
        hooks_dest_dir = claude_dir / "hooks"
        hooks_dest_dir.mkdir(parents=True)
        hook_dest = hooks_dest_dir / "send-to-telegram.sh"
        hook_dest.write_text("#!/bin/bash\necho 'old content'")

        # Run setup_hooks
        setup_hooks(claude_dir, source_dir)

        # Verify hook was overwritten
        assert hook_dest.read_text() == "#!/bin/bash\necho 'new content'"

    @patch('shutil.copy2')
    def test_setup_hooks_permission_error(self, mock_copy, tmp_path):
        """Test handling of permission errors during hook installation."""
        # Create source directory with hook
        source_dir = tmp_path / "source"
        hooks_src_dir = source_dir / "hooks"
        hooks_src_dir.mkdir(parents=True)
        hook_src = hooks_src_dir / "send-to-telegram.sh"
        hook_src.write_text("#!/bin/bash\necho 'test'")

        # Create claude directory
        claude_dir = tmp_path / "claude"

        # Mock copy2 to raise PermissionError
        mock_copy.side_effect = PermissionError("Permission denied")

        # Verify PermissionError is raised
        with pytest.raises(PermissionError):
            setup_hooks(claude_dir, source_dir)


class TestCreateServer:
    """Tests for create_server function."""

    @pytest.fixture
    def valid_config(self, tmp_path):
        """Create a valid configuration for testing."""
        config = BridgeConfig(
            tmux_session="test-session",
            claude_dir=tmp_path / "claude",
            tmux_socket_path="",
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            telegram_webhook_secret="test_secret",
            reaction_emoji="👍",
            port=8080,
            host="127.0.0.1",
            webhook_path="test_webhook_path",
            deployment_mode="production",
            webhook_domain="example.com",
            webhook_auto_setup=True,
            webhook_startup_delay=5,
            allowed_user_ids={123456},
            dm_allowed_user_id=999999
        )
        # Create claude directory
        config.claude_dir.mkdir(parents=True, exist_ok=True)
        return config

    @patch('claudecode_telegram.server.TelegramClient')
    @patch('claudecode_telegram.server.StateManager')
    @patch('claudecode_telegram.server.TmuxController')
    @patch('claudecode_telegram.server.WebhookManager')
    @patch('claudecode_telegram.server.create_handler_class')
    @patch('claudecode_telegram.server.HTTPServer')
    def test_create_server_success(
        self,
        mock_http_server,
        mock_create_handler,
        mock_webhook_manager,
        mock_tmux_controller,
        mock_state_manager,
        mock_telegram_client,
        valid_config
    ):
        """Test successful server creation."""
        # Setup mocks
        mock_telegram = MagicMock()
        mock_telegram_client.return_value = mock_telegram

        mock_state = MagicMock()
        mock_state_manager.return_value = mock_state

        mock_tmux = MagicMock()
        mock_tmux_controller.return_value = mock_tmux

        mock_webhook = MagicMock()
        mock_webhook_manager.return_value = mock_webhook

        mock_handler_class = MagicMock()
        mock_create_handler.return_value = mock_handler_class

        mock_server = MagicMock()
        mock_http_server.return_value = mock_server

        # Create server
        server, webhook_mgr, registry = create_server(valid_config)

        # Verify all components were initialized
        mock_telegram_client.assert_called_once_with(valid_config.bot_token)
        mock_state_manager.assert_called_once_with(valid_config.claude_dir)
        mock_tmux_controller.assert_called_once_with(
            session=valid_config.tmux_session,
            socket_path=""
        )
        mock_webhook_manager.assert_called_once_with(mock_telegram, mock_state, valid_config)

        # Verify bot commands were set
        mock_telegram.set_commands.assert_called_once()

        # Verify handler class was created
        mock_create_handler.assert_called_once()
        call_kwargs = mock_create_handler.call_args[1]
        assert call_kwargs['config'] == valid_config
        assert call_kwargs['telegram'] == mock_telegram
        assert call_kwargs['tmux'] == mock_tmux
        assert call_kwargs['state'] == mock_state
        assert call_kwargs['webhook'] == mock_webhook
        assert isinstance(call_kwargs['registry'], CommandRegistry)

        # Verify HTTP server was created
        mock_http_server.assert_called_once_with(
            (valid_config.host, valid_config.port),
            mock_handler_class
        )

        # Verify return values
        assert server == mock_server
        assert webhook_mgr == mock_webhook
        assert isinstance(registry, CommandRegistry)

    def test_create_server_invalid_config(self, tmp_path):
        """Test that ValueError is raised for invalid configuration."""
        # Create invalid config (missing bot token)
        invalid_config = BridgeConfig(
            tmux_session="test",
            claude_dir=tmp_path,
            tmux_socket_path="",
            bot_token="",  # Invalid: empty token
            telegram_webhook_secret="",
            reaction_emoji=None,
            port=8080,
            host="127.0.0.1",
            webhook_path="test",
            deployment_mode="",
            webhook_domain="",
            webhook_auto_setup=False,
            webhook_startup_delay=5
        )

        with pytest.raises(ValueError) as exc_info:
            create_server(invalid_config)

        assert "Configuration validation failed" in str(exc_info.value)
        assert "TELEGRAM_BOT_TOKEN is required" in str(exc_info.value)

    @patch('claudecode_telegram.server.TelegramClient')
    @patch('claudecode_telegram.server.StateManager')
    @patch('claudecode_telegram.server.TmuxController')
    @patch('claudecode_telegram.server.WebhookManager')
    @patch('claudecode_telegram.server.create_handler_class')
    @patch('claudecode_telegram.server.HTTPServer')
    def test_create_server_registers_builtin_commands(
        self,
        mock_http_server,
        mock_create_handler,
        mock_webhook_manager,
        mock_tmux_controller,
        mock_state_manager,
        mock_telegram_client,
        valid_config
    ):
        """Test that builtin commands are registered."""
        # Setup mocks
        mock_telegram = MagicMock()
        mock_telegram_client.return_value = mock_telegram
        mock_state_manager.return_value = MagicMock()
        mock_tmux_controller.return_value = MagicMock()
        mock_webhook_manager.return_value = MagicMock()
        mock_create_handler.return_value = MagicMock()
        mock_http_server.return_value = MagicMock()

        # Create server
        server, webhook_mgr, registry = create_server(valid_config)

        # Verify commands were registered
        commands = registry.list_commands()
        assert len(commands) > 0

        # Verify specific commands exist
        command_names = [name for name, desc in commands]
        assert "/status" in command_names
        assert "/stop" in command_names
        assert "/clear" in command_names

    @patch('claudecode_telegram.server.TelegramClient')
    @patch('claudecode_telegram.server.StateManager')
    @patch('claudecode_telegram.server.TmuxController')
    @patch('claudecode_telegram.server.WebhookManager')
    @patch('claudecode_telegram.server.create_handler_class')
    @patch('claudecode_telegram.server.HTTPServer')
    def test_create_server_blocks_interactive_commands(
        self,
        mock_http_server,
        mock_create_handler,
        mock_webhook_manager,
        mock_tmux_controller,
        mock_state_manager,
        mock_telegram_client,
        valid_config
    ):
        """Test that interactive-only commands are blocked."""
        # Setup mocks
        mock_telegram_client.return_value = MagicMock()
        mock_state_manager.return_value = MagicMock()
        mock_tmux_controller.return_value = MagicMock()
        mock_webhook_manager.return_value = MagicMock()
        mock_create_handler.return_value = MagicMock()
        mock_http_server.return_value = MagicMock()

        # Create server
        server, webhook_mgr, registry = create_server(valid_config)

        # Verify blocked commands
        assert registry.is_blocked("/mcp")
        assert registry.is_blocked("/help")
        assert registry.is_blocked("/settings")
        assert registry.is_blocked("/terminal")


class TestRunServer:
    """Tests for run_server function."""

    @pytest.fixture
    def valid_config(self, tmp_path):
        """Create a valid configuration for testing."""
        # Create source directory with hook
        source_dir = tmp_path / "source"
        hooks_src_dir = source_dir / "hooks"
        hooks_src_dir.mkdir(parents=True)
        hook_src = hooks_src_dir / "send-to-telegram.sh"
        hook_src.write_text("#!/bin/bash\necho 'test'")

        config = BridgeConfig(
            tmux_session="test",
            claude_dir=tmp_path / "claude",
            tmux_socket_path="",
            bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            telegram_webhook_secret="",
            reaction_emoji=None,
            port=8080,
            host="127.0.0.1",
            webhook_path="test",
            deployment_mode="production",
            webhook_domain="example.com",
            webhook_auto_setup=True,
            webhook_startup_delay=0  # No delay for tests
        )
        return config

    @patch('claudecode_telegram.server.setup_hooks')
    @patch('claudecode_telegram.server.create_server')
    def test_run_server_success(self, mock_create_server, mock_setup_hooks, valid_config):
        """Test successful server run with KeyboardInterrupt."""
        # Setup mocks
        mock_server = MagicMock()
        mock_server.serve_forever.side_effect = KeyboardInterrupt()

        mock_webhook = MagicMock()
        mock_registry = MagicMock()

        mock_create_server.return_value = (mock_server, mock_webhook, mock_registry)

        # Run server
        exit_code = run_server(valid_config)

        # Verify hooks were set up
        mock_setup_hooks.assert_called_once()

        # Verify server was created
        mock_create_server.assert_called_once_with(valid_config)

        # Verify recovery loop was started
        mock_webhook.start_recovery_loop.assert_called_once_with(
            startup_delay=valid_config.webhook_startup_delay
        )

        # Verify server was started
        mock_server.serve_forever.assert_called_once()

        # Verify server was shut down
        mock_server.shutdown.assert_called_once()

        # Verify success exit code
        assert exit_code == 0

    @patch('claudecode_telegram.server.setup_hooks')
    @patch('claudecode_telegram.server.create_server')
    def test_run_server_hook_setup_failure_continues(
        self,
        mock_create_server,
        mock_setup_hooks,
        valid_config
    ):
        """Test that server continues even if hook setup fails."""
        # Setup mocks
        mock_setup_hooks.side_effect = FileNotFoundError("Hook not found")

        mock_server = MagicMock()
        mock_server.serve_forever.side_effect = KeyboardInterrupt()
        mock_webhook = MagicMock()
        mock_registry = MagicMock()
        mock_create_server.return_value = (mock_server, mock_webhook, mock_registry)

        # Run server (should not raise exception)
        exit_code = run_server(valid_config)

        # Verify server was still created and started
        mock_create_server.assert_called_once()
        mock_server.serve_forever.assert_called_once()

        # Verify success exit code
        assert exit_code == 0

    @patch('claudecode_telegram.server.setup_hooks')
    @patch('claudecode_telegram.server.create_server')
    def test_run_server_config_validation_error(
        self,
        mock_create_server,
        mock_setup_hooks,
        valid_config
    ):
        """Test handling of configuration validation errors."""
        # Setup mock to raise ValueError
        mock_create_server.side_effect = ValueError("Invalid config")

        # Run server
        exit_code = run_server(valid_config)

        # Verify error exit code
        assert exit_code == 1

    @patch('claudecode_telegram.server.setup_hooks')
    @patch('claudecode_telegram.server.create_server')
    def test_run_server_os_error(
        self,
        mock_create_server,
        mock_setup_hooks,
        valid_config
    ):
        """Test handling of OSError (e.g., port in use)."""
        # Setup mock to raise OSError
        mock_create_server.side_effect = OSError("Address already in use")

        # Run server
        exit_code = run_server(valid_config)

        # Verify error exit code
        assert exit_code == 1

    @patch('claudecode_telegram.server.setup_hooks')
    @patch('claudecode_telegram.server.create_server')
    def test_run_server_unexpected_error(
        self,
        mock_create_server,
        mock_setup_hooks,
        valid_config
    ):
        """Test handling of unexpected errors."""
        # Setup mock to raise unexpected error
        mock_create_server.side_effect = RuntimeError("Unexpected error")

        # Run server
        exit_code = run_server(valid_config)

        # Verify error exit code
        assert exit_code == 1

    @patch('claudecode_telegram.server.setup_hooks')
    @patch('claudecode_telegram.server.create_server')
    def test_run_server_graceful_shutdown(
        self,
        mock_create_server,
        mock_setup_hooks,
        valid_config
    ):
        """Test graceful shutdown on KeyboardInterrupt."""
        # Setup mocks
        mock_server = MagicMock()
        mock_server.serve_forever.side_effect = KeyboardInterrupt()
        mock_webhook = MagicMock()
        mock_registry = MagicMock()
        mock_create_server.return_value = (mock_server, mock_webhook, mock_registry)

        # Run server
        exit_code = run_server(valid_config)

        # Verify shutdown was called
        mock_server.shutdown.assert_called_once()

        # Verify clean exit
        assert exit_code == 0
