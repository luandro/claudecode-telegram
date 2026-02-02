"""
Base command interface and implementations.

Defines the abstract base class for Telegram commands and provides
concrete implementations for built-in commands like /start and /help.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from claudecode_telegram.config import BridgeConfig
from claudecode_telegram.state import StateManager
from claudecode_telegram.telegram import TelegramClient
from claudecode_telegram.tmux import TmuxController


@dataclass
class CommandContext:
    """Context object passed to command execute methods.

    Contains all necessary information and clients for command execution
    including message metadata, Telegram API client, tmux controller,
    and state management.
    """

    chat_id: int
    message_id: int | None
    user_id: int | None
    text: str
    tmux: TmuxController
    telegram: TelegramClient
    state: StateManager
    config: BridgeConfig


class Command(ABC):
    """Abstract base class for Telegram bot commands.

    Subclasses must implement:
    - name: str class attribute defining the command name (e.g., "start")
    - description: str class attribute for the command description
    - execute(ctx): method that processes the command and returns reply text
    """

    name: str
    description: str

    @abstractmethod
    def execute(self, ctx: CommandContext) -> str | None:
        """Execute the command and return optional reply text.

        Args:
            ctx: CommandContext with message data and API clients

        Returns:
            Reply text to send back to user, or None for no reply
        """
        pass
