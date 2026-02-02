"""
Command registry and dispatcher.

Maintains the registry of available commands and provides dispatch
logic for routing incoming Telegram commands to their handlers.
"""

from typing import Callable

from claudecode_telegram.commands.base import Command, CommandContext


class CommandRegistry:
    """Registry for managing command lookup and execution.

    Provides a centralized registry for command registration, lookup,
    and execution. Includes support for blocking certain commands
    (e.g., interactive-only Claude commands).
    """

    def __init__(self, blocked_commands: list[str] | None = None):
        """Initialize the registry.

        Args:
            blocked_commands: List of command names that should be blocked
                            (e.g., ["/mcp", "/help", "/settings"])
        """
        self._commands: dict[str, Command] = {}
        self._blocked_commands: set[str] = set(blocked_commands or [])

    def register(self, command_class: type[Command]) -> None:
        """Register a command class.

        Args:
            command_class: Command class to register (must have 'name' attribute)

        Raises:
            ValueError: If command_class doesn't have required 'name' attribute
        """
        if not hasattr(command_class, "name"):
            raise ValueError(f"Command class {command_class.__name__} must have a 'name' attribute")

        # Instantiate the command
        command_instance = command_class()
        command_name = command_instance.name

        # Normalize command name (ensure leading slash)
        if not command_name.startswith("/"):
            command_name = f"/{command_name}"

        self._commands[command_name] = command_instance

    def get(self, name: str) -> Command | None:
        """Get a command by name.

        Args:
            name: Command name (with or without leading slash)

        Returns:
            Command instance if found, None otherwise
        """
        # Normalize command name (ensure leading slash)
        if not name.startswith("/"):
            name = f"/{name}"

        return self._commands.get(name)

    def execute(self, name: str, ctx: CommandContext) -> str | None:
        """Execute a command by name.

        Args:
            name: Command name (with or without leading slash)
            ctx: Command execution context

        Returns:
            Reply text from command, or None if command not found

        Raises:
            ValueError: If command is blocked
        """
        # Normalize command name (ensure leading slash)
        if not name.startswith("/"):
            name = f"/{name}"

        # Check if command is blocked
        if self.is_blocked(name):
            raise ValueError(f"Command '{name}' is blocked (interactive only)")

        # Get and execute command
        command = self.get(name)
        if command is None:
            return None

        return command.execute(ctx)

    def list_commands(self) -> list[tuple[str, str]]:
        """List all registered commands.

        Returns:
            List of (name, description) tuples for all registered commands
        """
        return [(name, cmd.description) for name, cmd in self._commands.items()]

    def is_blocked(self, name: str) -> bool:
        """Check if a command is blocked.

        Args:
            name: Command name (with or without leading slash)

        Returns:
            True if command is blocked, False otherwise
        """
        # Normalize command name (ensure leading slash)
        if not name.startswith("/"):
            name = f"/{name}"

        return name in self._blocked_commands


def register(registry: CommandRegistry) -> Callable[[type[Command]], type[Command]]:
    """Decorator for easy command registration.

    Usage:
        registry = CommandRegistry()

        @register(registry)
        class MyCommand(Command):
            name = "mycommand"
            description = "My command"

            def execute(self, ctx):
                return "Hello!"

    Args:
        registry: CommandRegistry instance to register with

    Returns:
        Decorator function that registers command classes
    """

    def decorator(command_class: type[Command]) -> type[Command]:
        registry.register(command_class)
        return command_class

    return decorator
