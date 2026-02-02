"""
Tests for builtin commands.

Tests all built-in Telegram bot commands including /status, /stop,
/clear, /continue_, /loop, and /resume.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claudecode_telegram.commands.base import CommandContext
from claudecode_telegram.commands.builtin import (
    ClearCommand,
    ContinueCommand,
    LoopCommand,
    ResumeCommand,
    StatusCommand,
    StopCommand,
    set_registry,
)
from claudecode_telegram.commands.registry import CommandRegistry
from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.state import StateManager
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.tmux import TmuxController


@pytest.fixture
def tmp_context(tmp_path):
    """Create a CommandContext for testing."""
    config = BridgeConfig(
        tmux_session="test",
        claude_dir=tmp_path,
        tmux_socket_path="",
        bot_token="test_token",
        telegram_webhook_secret="secret",
        reaction_emoji="👍",
        port=8080,
        host="127.0.0.1",
        webhook_path="/webhook",
        deployment_mode="tunnel",
        webhook_domain="",
        webhook_auto_setup=False,
        webhook_startup_delay=0,
    )

    # Mock tmux controller
    tmux = MagicMock(spec=TmuxController)
    tmux.exists = MagicMock(return_value=True)

    # Mock telegram client
    telegram = MagicMock(spec=TelegramClient)

    # Real state manager with tmp directory
    state = StateManager(claude_dir=tmp_path)

    return CommandContext(
        chat_id=123456,
        message_id=789,
        user_id=111,
        text="test message",
        tmux=tmux,
        telegram=telegram,
        state=state,
        config=config,
    )


class TestStatusCommand:
    """Tests for /status command."""

    def test_status_running(self, tmp_context):
        """Test status when tmux session is running."""
        tmp_context.tmux.exists.return_value = True

        cmd = StatusCommand()
        result = cmd.execute(tmp_context)

        assert result == "tmux 'test': running"
        tmp_context.tmux.exists.assert_called_once()

    def test_status_not_found(self, tmp_context):
        """Test status when tmux session is not found."""
        tmp_context.tmux.exists.return_value = False

        cmd = StatusCommand()
        result = cmd.execute(tmp_context)

        assert result == "tmux 'test': not found"
        tmp_context.tmux.exists.assert_called_once()

    def test_command_metadata(self):
        """Test command has correct name and description."""
        cmd = StatusCommand()
        assert cmd.name == "status"
        assert cmd.description == "Check tmux status"


class TestStopCommand:
    """Tests for /stop command."""

    def test_stop_with_tmux_running(self, tmp_context):
        """Test stop when tmux session exists."""
        tmp_context.tmux.exists.return_value = True

        cmd = StopCommand()
        result = cmd.execute(tmp_context)

        assert result == "Interrupted"
        tmp_context.tmux.exists.assert_called_once()
        tmp_context.tmux.send_escape.assert_called_once()

        # Verify pending was cleared
        assert not tmp_context.state.is_pending()

    def test_stop_without_tmux_running(self, tmp_context):
        """Test stop when tmux session doesn't exist."""
        tmp_context.tmux.exists.return_value = False

        cmd = StopCommand()
        result = cmd.execute(tmp_context)

        assert result == "Interrupted"
        tmp_context.tmux.exists.assert_called_once()
        tmp_context.tmux.send_escape.assert_not_called()

        # Pending should still be cleared
        assert not tmp_context.state.is_pending()

    def test_stop_clears_pending_state(self, tmp_context):
        """Test stop clears pending state."""
        # Set pending state
        tmp_context.state.set_pending()
        assert tmp_context.state.is_pending()

        cmd = StopCommand()
        cmd.execute(tmp_context)

        # Pending should be cleared
        assert not tmp_context.state.is_pending()

    def test_command_metadata(self):
        """Test command has correct name and description."""
        cmd = StopCommand()
        assert cmd.name == "stop"
        assert cmd.description == "Interrupt Claude (Escape)"


class TestClearCommand:
    """Tests for /clear command."""

    def test_clear_with_tmux_running(self, tmp_context):
        """Test clear when tmux session exists."""
        tmp_context.tmux.exists.return_value = True

        cmd = ClearCommand()
        result = cmd.execute(tmp_context)

        assert result == "Cleared"
        tmp_context.tmux.exists.assert_called_once()
        tmp_context.tmux.send_escape.assert_called_once()
        tmp_context.tmux.send_text.assert_called_once_with("/clear", press_enter=True)

    def test_clear_without_tmux_running(self, tmp_context):
        """Test clear when tmux session doesn't exist."""
        tmp_context.tmux.exists.return_value = False

        cmd = ClearCommand()
        result = cmd.execute(tmp_context)

        assert result == "tmux not found"
        tmp_context.tmux.exists.assert_called_once()
        tmp_context.tmux.send_escape.assert_not_called()
        tmp_context.tmux.send_text.assert_not_called()

    @patch("time.sleep")
    def test_clear_timing(self, mock_sleep, tmp_context):
        """Test clear includes proper timing delay."""
        tmp_context.tmux.exists.return_value = True

        cmd = ClearCommand()
        cmd.execute(tmp_context)

        # Should sleep 0.2 seconds after escape
        mock_sleep.assert_called_once_with(0.2)

    def test_command_metadata(self):
        """Test command has correct name and description."""
        cmd = ClearCommand()
        assert cmd.name == "clear"
        assert cmd.description == "Clear conversation"


class TestContinueCommand:
    """Tests for /continue_ command."""

    def test_continue_with_tmux_running(self, tmp_context):
        """Test continue when tmux session exists."""
        tmp_context.tmux.exists.return_value = True

        cmd = ContinueCommand()
        result = cmd.execute(tmp_context)

        assert result == "Continuing..."
        tmp_context.tmux.exists.assert_called_once()
        tmp_context.tmux.exit_and_run.assert_called_once_with(
            "claude --continue --dangerously-skip-permissions"
        )

    def test_continue_without_tmux_running(self, tmp_context):
        """Test continue when tmux session doesn't exist."""
        tmp_context.tmux.exists.return_value = False

        cmd = ContinueCommand()
        result = cmd.execute(tmp_context)

        assert result == "tmux not found"
        tmp_context.tmux.exists.assert_called_once()
        tmp_context.tmux.exit_and_run.assert_not_called()

    def test_command_metadata(self):
        """Test command has correct name and description."""
        cmd = ContinueCommand()
        assert cmd.name == "continue_"
        assert cmd.description == "Continue most recent session"


class TestLoopCommand:
    """Tests for /loop command."""

    def test_loop_with_valid_prompt(self, tmp_context):
        """Test loop with a valid prompt."""
        tmp_context.tmux.exists.return_value = True
        tmp_context.text = "/loop fix all bugs"

        cmd = LoopCommand()
        result = cmd.execute(tmp_context)

        assert result == "Ralph Loop started (max 5 iterations)"
        tmp_context.tmux.exists.assert_called_once()

        # Verify pending state was set
        assert tmp_context.state.is_pending()

        # Verify correct command was sent
        expected_cmd = '/ralph-loop:ralph-loop "fix all bugs Output <promise>DONE</promise> when complete." --max-iterations 5 --completion-promise "DONE"'
        tmp_context.tmux.send_text.assert_called_once_with(expected_cmd, press_enter=False)
        tmp_context.tmux.send_enter.assert_called_once()

    def test_loop_with_quotes_in_prompt(self, tmp_context):
        """Test loop escapes quotes in prompt."""
        tmp_context.tmux.exists.return_value = True
        tmp_context.text = '/loop say "hello world"'

        cmd = LoopCommand()
        result = cmd.execute(tmp_context)

        assert result == "Ralph Loop started (max 5 iterations)"

        # Verify quotes were escaped
        call_args = tmp_context.tmux.send_text.call_args[0][0]
        assert r'say \"hello world\"' in call_args

    def test_loop_without_prompt(self, tmp_context):
        """Test loop without a prompt shows usage."""
        tmp_context.tmux.exists.return_value = True
        tmp_context.text = "/loop"

        cmd = LoopCommand()
        result = cmd.execute(tmp_context)

        assert result == "Usage: /loop <prompt>"
        tmp_context.tmux.send_text.assert_not_called()

    def test_loop_without_tmux_running(self, tmp_context):
        """Test loop when tmux session doesn't exist."""
        tmp_context.tmux.exists.return_value = False
        tmp_context.text = "/loop test"

        cmd = LoopCommand()
        result = cmd.execute(tmp_context)

        assert result == "tmux not found"
        tmp_context.tmux.send_text.assert_not_called()

    @patch("time.sleep")
    def test_loop_timing(self, mock_sleep, tmp_context):
        """Test loop includes proper timing delay."""
        tmp_context.tmux.exists.return_value = True
        tmp_context.text = "/loop test"

        cmd = LoopCommand()
        cmd.execute(tmp_context)

        # Should sleep 0.3 seconds before pressing enter
        mock_sleep.assert_called_once_with(0.3)

    def test_command_metadata(self):
        """Test command has correct name and description."""
        cmd = LoopCommand()
        assert cmd.name == "loop"
        assert cmd.description == "Ralph Loop: /loop <prompt>"


class TestResumeCommand:
    """Tests for /resume command."""

    def test_resume_with_no_sessions(self, tmp_context):
        """Test resume when there are no sessions."""
        cmd = ResumeCommand()
        result = cmd.execute(tmp_context)

        assert result == "No sessions"
        tmp_context.telegram.send_message.assert_not_called()

    def test_resume_with_sessions(self, tmp_context):
        """Test resume with available sessions."""
        # Create mock session history
        sessions = [
            {
                "timestamp": int(time.time()),
                "project": "/home/user/project1",
                "display": "Project 1 - Main Branch",
            },
            {
                "timestamp": int(time.time()) - 3600,
                "project": "/home/user/project2",
                "display": "Project 2 - Feature Work",
            },
        ]

        # Write sessions to history file
        history_file = tmp_context.state.history_file
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(history_file, "w") as f:
            for session in sessions:
                f.write(json.dumps(session) + "\n")

        # Mock get_session_id to return session IDs
        tmp_context.state.get_session_id = MagicMock(side_effect=["session1", "session2"])

        cmd = ResumeCommand()
        result = cmd.execute(tmp_context)

        # Should return None (message sent via telegram client)
        assert result is None

        # Verify telegram client was called with keyboard
        tmp_context.telegram.send_message.assert_called_once()
        call_args = tmp_context.telegram.send_message.call_args

        # Check parameters
        assert call_args[1]["chat_id"] == 123456
        assert call_args[1]["text"] == "Select session:"

        # Check keyboard structure
        keyboard = call_args[1]["reply_markup"]["inline_keyboard"]
        assert len(keyboard) == 3  # Continue + 2 sessions

        # First button should be "Continue most recent"
        assert keyboard[0][0]["text"] == "Continue most recent"
        assert keyboard[0][0]["callback_data"] == "continue_recent"

        # Check session buttons
        assert "session1" in keyboard[1][0]["callback_data"]
        assert "session2" in keyboard[2][0]["callback_data"]

    def test_resume_truncates_long_display_text(self, tmp_context):
        """Test resume truncates long session display names."""
        # Create session with long display name
        long_display = "A" * 100  # 100 characters
        sessions = [
            {
                "timestamp": int(time.time()),
                "project": "/home/user/project1",
                "display": long_display,
            }
        ]

        # Write session to history file
        history_file = tmp_context.state.history_file
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(history_file, "w") as f:
            for session in sessions:
                f.write(json.dumps(session) + "\n")

        # Mock get_session_id
        tmp_context.state.get_session_id = MagicMock(return_value="session1")

        cmd = ResumeCommand()
        cmd.execute(tmp_context)

        # Get keyboard from call
        keyboard = tmp_context.telegram.send_message.call_args[1]["reply_markup"]["inline_keyboard"]

        # Check that display text was truncated to 40 chars + "..."
        button_text = keyboard[1][0]["text"]
        assert len(button_text) == 43  # 40 chars + "..."
        assert button_text.endswith("...")

    def test_resume_skips_sessions_without_id(self, tmp_context):
        """Test resume skips sessions where session ID can't be found."""
        sessions = [
            {
                "timestamp": int(time.time()),
                "project": "/home/user/project1",
                "display": "Project 1",
            },
            {
                "timestamp": int(time.time()) - 3600,
                "project": "/home/user/project2",
                "display": "Project 2",
            },
        ]

        # Write sessions to history file
        history_file = tmp_context.state.history_file
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(history_file, "w") as f:
            for session in sessions:
                f.write(json.dumps(session) + "\n")

        # Mock get_session_id to return None for first session, ID for second
        tmp_context.state.get_session_id = MagicMock(side_effect=[None, "session2"])

        cmd = ResumeCommand()
        cmd.execute(tmp_context)

        # Get keyboard from call
        keyboard = tmp_context.telegram.send_message.call_args[1]["reply_markup"]["inline_keyboard"]

        # Should only have Continue button + 1 session (not 2)
        assert len(keyboard) == 2

    def test_command_metadata(self):
        """Test command has correct name and description."""
        cmd = ResumeCommand()
        assert cmd.name == "resume"
        assert cmd.description == "Resume session (shows picker)"


class TestBuiltinCommandsIntegration:
    """Integration tests for builtin commands."""

    def test_all_commands_can_be_registered(self):
        """Test all builtin command classes can be manually registered."""
        registry = CommandRegistry()

        # Manually register all builtin commands
        registry.register(StatusCommand)
        registry.register(StopCommand)
        registry.register(ClearCommand)
        registry.register(ContinueCommand)
        registry.register(LoopCommand)
        registry.register(ResumeCommand)

        # Verify all commands are registered
        expected_commands = [
            "/status",
            "/stop",
            "/clear",
            "/continue_",
            "/loop",
            "/resume",
        ]

        for cmd_name in expected_commands:
            assert cmd_name in registry._commands, f"Command {cmd_name} not registered"

    def test_commands_have_descriptions(self):
        """Test all commands have descriptions for bot menu."""
        registry = CommandRegistry()

        # Manually register all builtin commands
        registry.register(StatusCommand)
        registry.register(StopCommand)
        registry.register(ClearCommand)
        registry.register(ContinueCommand)
        registry.register(LoopCommand)
        registry.register(ResumeCommand)

        commands = registry.list_commands()

        # All commands should have descriptions
        for name, description in commands:
            assert description, f"Command {name} missing description"
            assert len(description) > 0

    def test_full_workflow(self, tmp_context):
        """Test complete workflow with multiple commands."""
        # Status check
        status_cmd = StatusCommand()
        assert "running" in status_cmd.execute(tmp_context)

        # Clear conversation
        clear_cmd = ClearCommand()
        result = clear_cmd.execute(tmp_context)
        assert result == "Cleared"

        # Stop Claude
        stop_cmd = StopCommand()
        result = stop_cmd.execute(tmp_context)
        assert result == "Interrupted"
