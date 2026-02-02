"""
Command system for Telegram bot.

This subpackage provides a flexible command registration, dispatch, and execution
framework for handling special Telegram commands like /status, /resume, /clear, etc.

Architecture:
    The command system uses an abstract base class pattern with a centralized registry:
    - Command: Abstract base class that all commands inherit from
    - CommandContext: Data class containing execution context (chat, user, clients)
    - CommandRegistry: Central registry for command lookup and dispatch

Modules:
    base: Abstract Command class and CommandContext data class
    registry: CommandRegistry for command management and execution
    builtin: Built-in commands (StatusCommand, ResumeCommand, ClearCommand, etc.)

Usage Example:
    >>> from claudecode_telegram.commands import Command, CommandContext, CommandRegistry
    >>>
    >>> # Create registry
    >>> registry = CommandRegistry(blocked_commands=["/mcp", "/help"])
    >>>
    >>> # Define custom command
    >>> class MyCommand(Command):
    ...     name = "mycommand"
    ...     description = "My custom command"
    ...
    ...     def execute(self, ctx: CommandContext) -> str:
    ...         return "Hello from my command!"
    >>>
    >>> # Register command
    >>> registry.register(MyCommand)
    >>>
    >>> # Execute command
    >>> ctx = CommandContext(chat_id=123, message_id=456, user_id=789, ...)
    >>> reply = registry.execute("/mycommand", ctx)

Built-in Commands:
    /status - Check tmux session status
    /stop - Interrupt Claude (send Escape)
    /clear - Clear conversation
    /continue_ - Continue most recent session
    /loop - Run Ralph Loop with custom prompt
    /resume - Show session picker and resume a session

Features:
    - Abstract base class for easy command creation
    - Centralized registry with command blocking
    - Context object with all necessary clients and data
    - Built-in commands for common operations
    - Decorator-based registration (optional)
"""
