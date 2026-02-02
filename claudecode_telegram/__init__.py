"""
claudecode_telegram - Telegram bridge for Claude Code.

This package provides a webhook server that connects Telegram messages
to a running Claude Code instance via tmux, enabling remote AI assistance
through Telegram chat.

Architecture:
    The bridge consists of several key components:
    - HTTP webhook server that receives Telegram updates
    - Tmux integration for message injection into Claude Code
    - State management for session tracking and webhook configuration
    - Command system for special bot commands (/status, /resume, etc.)
    - Automatic webhook setup with tunnel or production deployment modes

Main Modules:
    server: HTTP server setup and lifecycle management
    handler: Webhook request handler and dispatcher
    telegram: Telegram Bot API client with error handling
    tmux: Tmux session management and message injection
    config: Configuration loading and validation
    state: File-based state management
    webhook: Webhook setup and monitoring
    sessions: Claude Code session history utilities
    commands: Command registry and built-in commands

Quick Start:
    >>> from claudecode_telegram.config import BridgeConfig
    >>> from claudecode_telegram.server import run_server
    >>>
    >>> config = BridgeConfig.from_env()
    >>> exit_code = run_server(config)

Environment Variables:
    TELEGRAM_BOT_TOKEN: Required Telegram bot token
    DEPLOYMENT_MODE: 'tunnel' or 'production'
    WEBHOOK_DOMAIN: Domain for production mode
    TMUX_SESSION: Tmux session name (default: 'claude')
    CLAUDE_DIR: Claude config directory (default: '~/.claude')
    PORT: Server port (default: 8080)
    HOST: Server host (default: '127.0.0.1')

See README.md for complete setup instructions.
"""

__version__ = "0.1.0"

# Public API
__all__ = [
    # Configuration
    "BridgeConfig",
    "ConfigError",
    # Core components
    "TelegramClient",
    "TypingIndicator",
    "TmuxController",
    "StateManager",
    "WebhookManager",
    # Server
    "create_server",
    "run_server",
    "setup_hooks",
    # Command system
    "Command",
    "CommandContext",
    "CommandRegistry",
    # Session utilities
    "get_recent_sessions",
    "get_session_id",
    "build_session_keyboard",
]

from claudecode_telegram.config import BridgeConfig, ConfigError
from claudecode_telegram.telegram import TelegramClient, TypingIndicator
from claudecode_telegram.tmux import TmuxController
from claudecode_telegram.state import StateManager
from claudecode_telegram.webhook import WebhookManager
from claudecode_telegram.server import create_server, run_server, setup_hooks
from claudecode_telegram.commands.base import Command, CommandContext
from claudecode_telegram.commands.registry import CommandRegistry
from claudecode_telegram.sessions import get_recent_sessions, get_session_id, build_session_keyboard
