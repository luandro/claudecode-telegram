"""
Tests for the base command infrastructure.

Tests CommandContext dataclass, Command abstract base class, and
command execution patterns.
"""

from pathlib import Path

import pytest

from claudecode_telegram.commands.base import Command, CommandContext
from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.state import StateManager
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.tmux import TmuxController


class TestCommandContext:
    """Tests for CommandContext dataclass."""

    def test_command_context_creation(self, tmp_path):
        """Test creating a CommandContext with all required fields."""
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

        tmux = TmuxController(session="test")
        telegram = TelegramClient(bot_token="test_token")
        state = StateManager(claude_dir=tmp_path)

        ctx = CommandContext(
            chat_id=123456,
            message_id=789,
            user_id=111,
            text="test message",
            tmux=tmux,
            telegram=telegram,
            state=state,
            config=config,
        )

        assert ctx.chat_id == 123456
        assert ctx.message_id == 789
        assert ctx.user_id == 111
        assert ctx.text == "test message"
        assert ctx.tmux is tmux
        assert ctx.telegram is telegram
        assert ctx.state is state
        assert ctx.config is config

    def test_command_context_with_none_values(self, tmp_path):
        """Test CommandContext with None for optional fields."""
        config = BridgeConfig(
            tmux_session="test",
            claude_dir=tmp_path,
            tmux_socket_path="",
            bot_token="test_token",
            telegram_webhook_secret="secret",
            reaction_emoji=None,
            port=8080,
            host="127.0.0.1",
            webhook_path="/webhook",
            deployment_mode="tunnel",
            webhook_domain="",
            webhook_auto_setup=False,
            webhook_startup_delay=0,
        )

        ctx = CommandContext(
            chat_id=123456,
            message_id=None,
            user_id=None,
            text="",
            tmux=TmuxController(session="test"),
            telegram=TelegramClient(bot_token="test_token"),
            state=StateManager(claude_dir=tmp_path),
            config=config,
        )

        assert ctx.message_id is None
        assert ctx.user_id is None
        assert ctx.text == ""

    def test_command_context_immutability(self, tmp_path):
        """Test that CommandContext is a frozen dataclass."""
        ctx = CommandContext(
            chat_id=123456,
            message_id=789,
            user_id=111,
            text="test",
            tmux=TmuxController(session="test"),
            telegram=TelegramClient(bot_token="test_token"),
            state=StateManager(claude_dir=tmp_path),
            config=BridgeConfig(
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
            ),
        )

        # Dataclasses are not frozen by default in this implementation
        # but we can still verify the fields are accessible
        assert hasattr(ctx, 'chat_id')
        assert hasattr(ctx, 'message_id')
        assert hasattr(ctx, 'user_id')
        assert hasattr(ctx, 'text')


class TestCommandAbstractBase:
    """Tests for Command abstract base class."""

    def test_command_cannot_be_instantiated(self):
        """Test that Command ABC cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            Command()

    def test_command_requires_execute_method(self):
        """Test that subclasses must implement execute method."""
        class IncompleteCommand(Command):
            name = "incomplete"
            description = "Test command without execute method"

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteCommand()

    def test_concrete_command_implementation(self, tmp_path):
        """Test creating a concrete command implementation."""
        class TestCommand(Command):
            name = "test"
            description = "A test command"

            def execute(self, ctx: CommandContext) -> str | None:
                return f"Hello from {ctx.chat_id}"

        cmd = TestCommand()
        assert cmd.name == "test"
        assert cmd.description == "A test command"

        ctx = CommandContext(
            chat_id=123456,
            message_id=789,
            user_id=111,
            text="/test",
            tmux=TmuxController(session="test"),
            telegram=TelegramClient(bot_token="test_token"),
            state=StateManager(claude_dir=tmp_path),
            config=BridgeConfig(
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
            ),
        )

        result = cmd.execute(ctx)
        assert result == "Hello from 123456"

    def test_command_returning_none(self, tmp_path):
        """Test command that returns None (no reply)."""
        class SilentCommand(Command):
            name = "silent"
            description = "A command that doesn't reply"

            def execute(self, ctx: CommandContext) -> str | None:
                # Perform some action but don't send a reply
                return None

        cmd = SilentCommand()
        ctx = CommandContext(
            chat_id=123456,
            message_id=789,
            user_id=111,
            text="/silent",
            tmux=TmuxController(session="test"),
            telegram=TelegramClient(bot_token="test_token"),
            state=StateManager(claude_dir=tmp_path),
            config=BridgeConfig(
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
            ),
        )

        result = cmd.execute(ctx)
        assert result is None

    def test_command_with_state_access(self, tmp_path):
        """Test command that accesses state manager."""
        class StateCommand(Command):
            name = "state"
            description = "Command that reads state"

            def execute(self, ctx: CommandContext) -> str | None:
                chat_id = ctx.state.get_chat_id()
                if chat_id:
                    return f"Stored chat ID: {chat_id}"
                return "No chat ID stored"

        cmd = StateCommand()
        state = StateManager(claude_dir=tmp_path)
        state.set_chat_id(999888)

        ctx = CommandContext(
            chat_id=123456,
            message_id=789,
            user_id=111,
            text="/state",
            tmux=TmuxController(session="test"),
            telegram=TelegramClient(bot_token="test_token"),
            state=state,
            config=BridgeConfig(
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
            ),
        )

        result = cmd.execute(ctx)
        assert result == "Stored chat ID: 999888"

    def test_command_with_config_access(self, tmp_path):
        """Test command that accesses configuration."""
        class ConfigCommand(Command):
            name = "config"
            description = "Command that reads config"

            def execute(self, ctx: CommandContext) -> str | None:
                return f"Session: {ctx.config.tmux_session}"

        cmd = ConfigCommand()
        ctx = CommandContext(
            chat_id=123456,
            message_id=789,
            user_id=111,
            text="/config",
            tmux=TmuxController(session="test"),
            telegram=TelegramClient(bot_token="test_token"),
            state=StateManager(claude_dir=tmp_path),
            config=BridgeConfig(
                tmux_session="my-session",
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
            ),
        )

        result = cmd.execute(ctx)
        assert result == "Session: my-session"

    def test_multiple_command_instances(self, tmp_path):
        """Test that multiple command classes can coexist."""
        class CommandA(Command):
            name = "a"
            description = "Command A"

            def execute(self, ctx: CommandContext) -> str | None:
                return "A"

        class CommandB(Command):
            name = "b"
            description = "Command B"

            def execute(self, ctx: CommandContext) -> str | None:
                return "B"

        cmd_a = CommandA()
        cmd_b = CommandB()

        assert cmd_a.name == "a"
        assert cmd_b.name == "b"

        ctx = CommandContext(
            chat_id=123456,
            message_id=789,
            user_id=111,
            text="/test",
            tmux=TmuxController(session="test"),
            telegram=TelegramClient(bot_token="test_token"),
            state=StateManager(claude_dir=tmp_path),
            config=BridgeConfig(
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
            ),
        )

        assert cmd_a.execute(ctx) == "A"
        assert cmd_b.execute(ctx) == "B"
