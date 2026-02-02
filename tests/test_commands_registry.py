"""
Tests for the command registry.

Tests CommandRegistry class including command registration, lookup,
execution, blocking, and the decorator pattern.
"""

from pathlib import Path

import pytest

from claudecode_telegram.commands.base import Command, CommandContext
from claudecode_telegram.commands.registry import CommandRegistry, register
from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.state import StateManager
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.tmux import TmuxController


# Test commands for use in tests
class TestCommand(Command):
    """Simple test command."""

    name = "test"
    description = "A test command"

    def execute(self, ctx: CommandContext) -> str | None:
        return "Test executed"


class AnotherCommand(Command):
    """Another test command."""

    name = "another"
    description = "Another command"

    def execute(self, ctx: CommandContext) -> str | None:
        return f"Another: {ctx.text}"


class NoSlashCommand(Command):
    """Command without leading slash in name."""

    name = "noslash"
    description = "No slash command"

    def execute(self, ctx: CommandContext) -> str | None:
        return "No slash"


class InvalidCommand:
    """Invalid command without name attribute."""

    description = "Invalid"

    def execute(self, ctx: CommandContext) -> str | None:
        return "Invalid"


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

    tmux = TmuxController(session="test")
    telegram = TelegramClient(bot_token="test_token")
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


class TestCommandRegistry:
    """Tests for CommandRegistry class."""

    def test_init_empty(self):
        """Test creating an empty registry."""
        registry = CommandRegistry()
        assert registry._commands == {}
        assert registry._blocked_commands == set()

    def test_init_with_blocked_commands(self):
        """Test creating a registry with blocked commands."""
        blocked = ["/mcp", "/help", "/settings"]
        registry = CommandRegistry(blocked_commands=blocked)
        assert registry._blocked_commands == {"/mcp", "/help", "/settings"}

    def test_register_command(self):
        """Test registering a command."""
        registry = CommandRegistry()
        registry.register(TestCommand)

        # Check command is registered
        assert "/test" in registry._commands
        assert isinstance(registry._commands["/test"], TestCommand)

    def test_register_command_without_slash(self):
        """Test registering a command without leading slash normalizes it."""
        registry = CommandRegistry()
        registry.register(NoSlashCommand)

        # Should be registered with leading slash
        assert "/noslash" in registry._commands
        assert isinstance(registry._commands["/noslash"], NoSlashCommand)

    def test_register_invalid_command(self):
        """Test registering an invalid command raises ValueError."""
        registry = CommandRegistry()

        with pytest.raises(ValueError, match="must have a 'name' attribute"):
            registry.register(InvalidCommand)

    def test_register_multiple_commands(self):
        """Test registering multiple commands."""
        registry = CommandRegistry()
        registry.register(TestCommand)
        registry.register(AnotherCommand)

        assert len(registry._commands) == 2
        assert "/test" in registry._commands
        assert "/another" in registry._commands

    def test_get_command(self):
        """Test getting a registered command."""
        registry = CommandRegistry()
        registry.register(TestCommand)

        command = registry.get("/test")
        assert command is not None
        assert isinstance(command, TestCommand)

    def test_get_command_without_slash(self):
        """Test getting a command without leading slash normalizes it."""
        registry = CommandRegistry()
        registry.register(TestCommand)

        command = registry.get("test")
        assert command is not None
        assert isinstance(command, TestCommand)

    def test_get_nonexistent_command(self):
        """Test getting a command that doesn't exist returns None."""
        registry = CommandRegistry()
        command = registry.get("/nonexistent")
        assert command is None

    def test_execute_command(self, tmp_context):
        """Test executing a registered command."""
        registry = CommandRegistry()
        registry.register(TestCommand)

        result = registry.execute("/test", tmp_context)
        assert result == "Test executed"

    def test_execute_command_without_slash(self, tmp_context):
        """Test executing a command without leading slash normalizes it."""
        registry = CommandRegistry()
        registry.register(TestCommand)

        result = registry.execute("test", tmp_context)
        assert result == "Test executed"

    def test_execute_command_with_context(self, tmp_context):
        """Test executing a command that uses context."""
        registry = CommandRegistry()
        registry.register(AnotherCommand)

        tmp_context.text = "hello world"
        result = registry.execute("/another", tmp_context)
        assert result == "Another: hello world"

    def test_execute_nonexistent_command(self, tmp_context):
        """Test executing a nonexistent command returns None."""
        registry = CommandRegistry()
        result = registry.execute("/nonexistent", tmp_context)
        assert result is None

    def test_execute_blocked_command(self, tmp_context):
        """Test executing a blocked command raises ValueError."""
        registry = CommandRegistry(blocked_commands=["/test"])
        registry.register(TestCommand)

        with pytest.raises(ValueError, match="is blocked"):
            registry.execute("/test", tmp_context)

    def test_execute_blocked_command_without_slash(self, tmp_context):
        """Test executing a blocked command without slash raises ValueError."""
        registry = CommandRegistry(blocked_commands=["/test"])
        registry.register(TestCommand)

        with pytest.raises(ValueError, match="is blocked"):
            registry.execute("test", tmp_context)

    def test_list_commands_empty(self):
        """Test listing commands in an empty registry."""
        registry = CommandRegistry()
        commands = registry.list_commands()
        assert commands == []

    def test_list_commands_single(self):
        """Test listing a single command."""
        registry = CommandRegistry()
        registry.register(TestCommand)

        commands = registry.list_commands()
        assert len(commands) == 1
        assert ("/test", "A test command") in commands

    def test_list_commands_multiple(self):
        """Test listing multiple commands."""
        registry = CommandRegistry()
        registry.register(TestCommand)
        registry.register(AnotherCommand)

        commands = registry.list_commands()
        assert len(commands) == 2
        assert ("/test", "A test command") in commands
        assert ("/another", "Another command") in commands

    def test_is_blocked_true(self):
        """Test is_blocked returns True for blocked commands."""
        registry = CommandRegistry(blocked_commands=["/mcp", "/help"])
        assert registry.is_blocked("/mcp") is True
        assert registry.is_blocked("/help") is True

    def test_is_blocked_false(self):
        """Test is_blocked returns False for non-blocked commands."""
        registry = CommandRegistry(blocked_commands=["/mcp"])
        assert registry.is_blocked("/test") is False
        assert registry.is_blocked("/help") is False

    def test_is_blocked_without_slash(self):
        """Test is_blocked normalizes command names without slashes."""
        registry = CommandRegistry(blocked_commands=["/mcp"])
        assert registry.is_blocked("mcp") is True

    def test_is_blocked_with_slash_in_blocklist(self):
        """Test is_blocked works when blocklist has slashes."""
        registry = CommandRegistry(blocked_commands=["/mcp", "/help"])
        assert registry.is_blocked("/mcp") is True
        assert registry.is_blocked("mcp") is True

    def test_blocked_commands_from_bridge(self):
        """Test using the actual blocked commands list from bridge.py."""
        blocked = [
            "/mcp",
            "/help",
            "/settings",
            "/config",
            "/model",
            "/compact",
            "/cost",
            "/doctor",
            "/init",
            "/login",
            "/logout",
            "/memory",
            "/permissions",
            "/pr",
            "/review",
            "/terminal",
            "/vim",
            "/approved-tools",
            "/listen",
        ]
        registry = CommandRegistry(blocked_commands=blocked)

        # All should be blocked
        for cmd in blocked:
            assert registry.is_blocked(cmd) is True

        # Others should not be blocked
        assert registry.is_blocked("/test") is False
        assert registry.is_blocked("/start") is False


class TestRegisterDecorator:
    """Tests for the @register decorator."""

    def test_register_decorator(self):
        """Test using the @register decorator."""
        registry = CommandRegistry()

        @register(registry)
        class DecoratedCommand(Command):
            name = "decorated"
            description = "Decorated command"

            def execute(self, ctx: CommandContext) -> str | None:
                return "Decorated"

        # Command should be registered
        assert "/decorated" in registry._commands
        assert isinstance(registry._commands["/decorated"], DecoratedCommand)

    def test_register_decorator_returns_class(self):
        """Test that @register decorator returns the class unchanged."""
        registry = CommandRegistry()

        @register(registry)
        class DecoratedCommand(Command):
            name = "decorated"
            description = "Decorated command"

            def execute(self, ctx: CommandContext) -> str | None:
                return "Decorated"

        # Should still be the same class
        assert DecoratedCommand.name == "decorated"
        assert DecoratedCommand.description == "Decorated command"

    def test_register_decorator_multiple_commands(self):
        """Test registering multiple commands with decorator."""
        registry = CommandRegistry()

        @register(registry)
        class FirstCommand(Command):
            name = "first"
            description = "First"

            def execute(self, ctx: CommandContext) -> str | None:
                return "First"

        @register(registry)
        class SecondCommand(Command):
            name = "second"
            description = "Second"

            def execute(self, ctx: CommandContext) -> str | None:
                return "Second"

        # Both should be registered
        assert len(registry._commands) == 2
        assert "/first" in registry._commands
        assert "/second" in registry._commands

    def test_register_decorator_with_blocked_commands(self, tmp_context):
        """Test decorator works with blocked commands."""
        registry = CommandRegistry(blocked_commands=["/blocked"])

        @register(registry)
        class BlockedCommand(Command):
            name = "blocked"
            description = "Blocked"

            def execute(self, ctx: CommandContext) -> str | None:
                return "Blocked"

        # Command should be registered
        assert "/blocked" in registry._commands

        # But execution should be blocked
        with pytest.raises(ValueError, match="is blocked"):
            registry.execute("/blocked", tmp_context)


class TestCommandRegistryIntegration:
    """Integration tests for CommandRegistry."""

    def test_full_workflow(self, tmp_context):
        """Test complete workflow: register, get, execute."""
        # Create registry with some blocked commands
        blocked = ["/mcp", "/help"]
        registry = CommandRegistry(blocked_commands=blocked)

        # Register commands
        registry.register(TestCommand)
        registry.register(AnotherCommand)

        # Get and verify commands
        test_cmd = registry.get("/test")
        another_cmd = registry.get("/another")
        assert test_cmd is not None
        assert another_cmd is not None

        # Execute commands
        result1 = registry.execute("/test", tmp_context)
        assert result1 == "Test executed"

        tmp_context.text = "integration test"
        result2 = registry.execute("/another", tmp_context)
        assert result2 == "Another: integration test"

        # Verify blocked commands
        assert registry.is_blocked("/mcp") is True
        assert registry.is_blocked("/test") is False

        # List all commands
        commands = registry.list_commands()
        assert len(commands) == 2

    def test_decorator_and_manual_registration(self, tmp_context):
        """Test mixing decorator and manual registration."""
        registry = CommandRegistry()

        # Manual registration
        registry.register(TestCommand)

        # Decorator registration
        @register(registry)
        class DecoratedCommand(Command):
            name = "decorated"
            description = "Decorated"

            def execute(self, ctx: CommandContext) -> str | None:
                return "Decorated"

        # Both should work
        assert len(registry._commands) == 2
        assert registry.execute("/test", tmp_context) == "Test executed"
        assert registry.execute("/decorated", tmp_context) == "Decorated"
