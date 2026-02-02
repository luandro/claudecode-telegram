"""
Built-in Telegram bot commands.

Implements all the core commands for controlling Claude Code via Telegram:
- /status: Check tmux session status
- /stop: Interrupt Claude (send Escape)
- /clear: Clear conversation
- /continue_: Continue most recent session
- /loop: Run Ralph Loop with a prompt
- /resume: Show session picker and resume a session
"""

import time
from typing import Any, Optional

from claudecode_telegram.commands.base import Command, CommandContext
from claudecode_telegram.commands.registry import CommandRegistry


# Create a global registry instance that will be used by the @register decorator
_builtin_registry: Optional[CommandRegistry] = None


def register(command_class: Any) -> Any:
    """Decorator for registering builtin commands.

    This is a module-level decorator that uses a global registry instance.
    The registry must be set via set_registry() before commands are registered.

    Args:
        command_class: Command class to register

    Returns:
        The same command class (for decorator chaining)
    """
    if _builtin_registry is not None:
        _builtin_registry.register(command_class)
    return command_class


def set_registry(registry: CommandRegistry) -> None:
    """Set the registry instance for builtin command registration.

    This must be called before importing this module to ensure commands
    are registered with the correct registry.

    Args:
        registry: CommandRegistry instance to use for registration
    """
    global _builtin_registry
    _builtin_registry = registry


@register
class StatusCommand(Command):
    """Check if the tmux session exists and is running."""

    name = "status"
    description = "Check tmux status"

    def execute(self, ctx: CommandContext) -> str:
        """Check tmux session status and return result.

        Args:
            ctx: Command execution context

        Returns:
            Status message indicating whether tmux session is running
        """
        session_name = ctx.config.tmux_session
        status = "running" if ctx.tmux.exists() else "not found"
        return f"tmux '{session_name}': {status}"


@register
class StopCommand(Command):
    """Interrupt Claude by sending Escape and clear pending flag."""

    name = "stop"
    description = "Interrupt Claude (Escape)"

    def execute(self, ctx: CommandContext) -> str:
        """Send Escape to interrupt Claude and clear pending state.

        Args:
            ctx: Command execution context

        Returns:
            Confirmation message
        """
        if ctx.tmux.exists():
            ctx.tmux.send_escape()
        ctx.state.clear_pending()
        return "Interrupted"


@register
class ClearCommand(Command):
    """Clear the conversation by sending /clear to Claude."""

    name = "clear"
    description = "Clear conversation"

    def execute(self, ctx: CommandContext) -> str:
        """Clear conversation by sending Escape, /clear, Enter sequence.

        Args:
            ctx: Command execution context

        Returns:
            Confirmation message, or error if tmux not found
        """
        if not ctx.tmux.exists():
            return "tmux not found"

        ctx.tmux.send_escape()
        time.sleep(0.2)
        ctx.tmux.send_text("/clear", press_enter=True)
        return "Cleared"


@register
class ContinueCommand(Command):
    """Exit current session and continue most recent session."""

    name = "continue_"
    description = "Continue most recent session"

    def execute(self, ctx: CommandContext) -> str:
        """Exit and run 'claude --continue --dangerously-skip-permissions'.

        Args:
            ctx: Command execution context

        Returns:
            Confirmation message, or error if tmux not found
        """
        if not ctx.tmux.exists():
            return "tmux not found"

        ctx.tmux.exit_and_run("claude --continue --dangerously-skip-permissions")
        return "Continuing..."


@register
class LoopCommand(Command):
    """Run Ralph Loop with a custom prompt."""

    name = "loop"
    description = "Ralph Loop: /loop <prompt>"

    def execute(self, ctx: CommandContext) -> str:
        """Parse prompt and send Ralph Loop command to tmux.

        Args:
            ctx: Command execution context

        Returns:
            Confirmation message, or error/usage message
        """
        if not ctx.tmux.exists():
            return "tmux not found"

        # Parse prompt from message text
        parts = ctx.text.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: /loop <prompt>"

        # Escape double quotes in prompt
        prompt = parts[1].replace('"', '\\"')

        # Build full prompt with completion marker
        full_prompt = f'{prompt} Output <promise>DONE</promise> when complete.'

        # Set pending state and start typing indicator
        ctx.state.set_pending()

        # Send Ralph Loop command
        loop_command = f'/ralph-loop:ralph-loop "{full_prompt}" --max-iterations 5 --completion-promise "DONE"'
        ctx.tmux.send_text(loop_command, press_enter=False)
        time.sleep(0.3)
        ctx.tmux.send_enter()

        return "Ralph Loop started (max 5 iterations)"


@register
class ResumeCommand(Command):
    """Show session picker or resume specific session."""

    name = "resume"
    description = "Resume session (shows picker)"

    def execute(self, ctx: CommandContext) -> str | None:
        """Get recent sessions and show inline keyboard picker.

        Args:
            ctx: Command execution context

        Returns:
            Error message if no sessions, None if keyboard was sent
        """
        sessions = ctx.state.get_recent_sessions()
        if not sessions:
            return "No sessions"

        # Build inline keyboard
        keyboard = [[{"text": "Continue most recent", "callback_data": "continue_recent"}]]

        # Add button for each session
        for session in sessions:
            project_path = session.get("project", "")
            session_id = ctx.state.get_session_id(project_path)

            if session_id:
                # Truncate display text to 40 chars
                display = session.get("display", "?")[:40] + "..."
                keyboard.append([{
                    "text": display,
                    "callback_data": f"resume:{session_id}"
                }])

        # Send message with inline keyboard
        ctx.telegram.send_message(
            chat_id=ctx.chat_id,
            text="Select session:",
            reply_markup={"inline_keyboard": keyboard}
        )

        # Return None to indicate we handled the reply ourselves
        return None
